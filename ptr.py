#!/usr/bin/env python3
# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
# coding=utf8

import argparse
import ast
import asyncio
import logging
import sys
from collections import defaultdict, namedtuple
from configparser import ConfigParser
from enum import Enum
from json import dump
from os import chdir, cpu_count, environ, getcwd, getpid
from os.path import sep as path_separator
from pathlib import Path
from shutil import rmtree
from subprocess import CalledProcessError
from tempfile import gettempdir
from time import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union


LOG = logging.getLogger(__name__)


def _config_default() -> ConfigParser:
    LOG.info("Using default config settings")
    cp = ConfigParser()
    cp["ptr"] = {}
    cp["ptr"]["atonce"] = str(int((cpu_count() or 20) / 2))
    cp["ptr"]["exclude_patterns"] = "build* yocto"
    cp["ptr"]["pypi_url"] = "https://pypi.org/simple/"
    cp["ptr"]["venv_pkgs"] = "black coverage mypy pip setuptools"
    return cp


def _config_read(cwd: str, conf_name: str = ".ptrconfig") -> Optional[ConfigParser]:
    """ Look from cwd to / for a "conf_name" file - If so read it in """
    cp = None
    cwd_path = Path(cwd)  # type: Optional[Path]
    root_path = Path("/")

    while cwd_path:
        ptrconfig_path = cwd_path / conf_name
        if ptrconfig_path.exists():
            cp = ConfigParser()
            cp.read(str(ptrconfig_path))

            LOG.info("Loading found config @ {}".format(ptrconfig_path))
            break

        cwd_path = None if cwd_path == root_path else cwd_path.parent

    return cp


CWD = getcwd()
CONFIG = _config_read(CWD) or _config_default()
PIP_CONF_TEMPLATE = """\
[global]
index-url = {}
timeout = {}"""


class StepName(Enum):
    pip_install = 1
    tests_run = 2
    analyze_coverage = 3
    mypy_run = 4
    black_run = 5


coverage_line = namedtuple("coverage_line", ["stmts", "miss", "cover", "missing"])
step = namedtuple(
    "step", ["step_name", "run_condition", "cmds", "log_message", "timeout"]
)
test_result = namedtuple(
    "test_result", ["setup_py_path", "returncode", "output", "runtime", "timeout"]
)


def _get_site_packages_path(venv_path: Path) -> Optional[Path]:
    lib_path = venv_path / "lib"
    py_dir = None
    for apath in lib_path.iterdir():
        if apath.is_dir() and apath.match("python*"):
            py_dir = apath
            break
    if not py_dir:
        LOG.error("Unable to find a python lib dir in {}".format(lib_path))
        return None

    return py_dir / "site-packages"


def _analyze_coverage(
    venv_path: Path,
    setup_py_path: Path,
    required_cov: Dict[str, int],
    coverage_report: str,
) -> Optional[test_result]:
    module_path = setup_py_path.parent
    site_packages_path = _get_site_packages_path(venv_path)
    if not site_packages_path:
        return None
    relative_site_packages = str(site_packages_path.relative_to(venv_path)) + "/"

    if not coverage_report:
        LOG.error(
            "No coverage report for {} - Unable to enforce coverage requirements".format(
                setup_py_path
            )
        )
        return None
    if not required_cov:
        LOG.error("No required coverage to enforce for {}".format(setup_py_path))
        return None

    coverage_lines = {}
    for line in coverage_report.split("\n"):
        if not line or line.startswith("-") or line.startswith("Name"):
            continue

        sl = line.split(maxsplit=4)

        module_path_str = None
        sl_path = None
        if sl[0] != "TOTAL":
            sl_path = Path(sl[0])
        if sl_path and sl_path.is_absolute() and site_packages_path:
            for possible_abs_path in (module_path, site_packages_path):
                try:
                    module_path_str = str(sl_path.relative_to(possible_abs_path))
                except ValueError:
                    pass
        elif sl_path:
            module_path_str = str(sl_path).replace(relative_site_packages, "")
        else:
            module_path_str = sl[0]

        if not module_path_str:
            LOG.error("Unable to find path relative path for {}".format(sl[0]))
            continue

        if len(sl) == 4:
            coverage_lines[module_path_str] = coverage_line(
                int(sl[1]), int(sl[2]), int(sl[3][:-1]), ""
            )
        else:
            coverage_lines[module_path_str] = coverage_line(
                int(sl[1]), int(sl[2]), int(sl[3][:-1]), sl[4]
            )

    failed_output = "The following files did not meet coverage requirements:\n"
    failed_coverage = False
    for afile, cov_req in required_cov.items():
        if coverage_lines[afile].cover < cov_req:
            failed_coverage = True
            failed_output += "  {}: {} < {} - Missing: {}\n".format(
                afile,
                coverage_lines[afile].cover,
                cov_req,
                coverage_lines[afile].missing,
            )

    # TODO: Fix runtime everywhere when I add the stats output
    if failed_coverage:
        return test_result(
            setup_py_path, StepName.analyze_coverage.value, failed_output, 0, False
        )
    return None


def _write_stats_file(stats_file: str, stats: Dict[str, int]) -> None:
    try:
        with open(stats_file, "w") as sfp:
            dump(stats, sfp, indent=2, sort_keys=True)
    except OSError as ose:
        LOG.exception(
            "Unable to write out JSON statistics file to {} ({})".format(
                stats_file, ose
            )
        )


def _generate_black_cmd(module_dir: Path, black_exe: Path) -> Tuple[str, ...]:
    py_files = set()  # type: Set[str]
    find_py_files(py_files, module_dir)
    return (str(black_exe), "--check", *sorted(py_files))


def _generate_install_cmd(
    pip_exe: str, module_dir: str, config: Dict[str, Any]
) -> Tuple[str, ...]:
    cmds = [pip_exe, "-v", "install", module_dir]
    if "tests_require" in config and config["tests_require"]:
        for dep in config["tests_require"]:
            cmds.append(dep)

    return tuple(cmds)


def _generate_mypy_cmd(
    module_dir: Path, mypy_exe: Path, config: Dict
) -> Tuple[str, ...]:
    if config["run_mypy"]:
        mypy_entry_point = module_dir / "{}.py".format(config["entry_point_module"])
    else:
        return ()

    cmds = [str(mypy_exe)]
    mypy_ini_path = module_dir / "mypy.ini"
    if mypy_ini_path.exists():
        cmds.extend(["--config", str(mypy_ini_path)])
    cmds.append(str(mypy_entry_point))
    return tuple(cmds)


def _get_test_modules(base_path: Path, stats: Dict[str, int]) -> Dict[Path, Dict]:
    get_tests_start_time = time()
    all_setup_pys = find_setup_pys(
        base_path,
        set(CONFIG["ptr"]["exclude_patterns"].split())
        if CONFIG["ptr"]["exclude_patterns"]
        else set(),
    )
    stats["total.setup_pys"] = len(all_setup_pys)

    test_modules = {}  # type: Dict[Path, Dict]
    for setup_py in all_setup_pys:
        # If a setup.cfg exists lets prefer it, if there is a [ptr] section
        ptr_params = parse_setup_cfg(setup_py)
        if ptr_params:
            test_modules[setup_py] = ptr_params
            continue

        with setup_py.open("r") as sp:
            setup_tree = ast.parse(sp.read())

        LOG.debug("AST visiting {}".format(setup_py))
        for node in ast.walk(setup_tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    # mypy error: "expr" has no attribute "id"
                    if target.id == "ptr_params":  # type: ignore
                        LOG.debug("Found ptr_params in {}".format(setup_py))
                        ptr_params = ast.literal_eval(node.value)
                        if "test_suite" in ptr_params:
                            test_modules[setup_py] = ptr_params
                        else:
                            LOG.info(
                                "{} does not have a suite. Nothing to run".format(
                                    setup_py
                                )
                            )

    stats["total.ptr_setup_pys"] = len(test_modules)
    stats["runtime.parse_setup_pys"] = int(time() - get_tests_start_time)
    return test_modules


def _handle_debug(debug: bool) -> bool:
    """Turn on debugging if asked otherwise INFO default"""
    log_level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        format="[%(asctime)s] %(levelname)s: %(message)s (%(filename)s:%(lineno)d)",
        level=log_level,
    )
    return debug


def _validate_base_dir(base_dir: str) -> Path:
    base_dir_path = Path(base_dir)
    if not base_dir_path.is_absolute():
        base_dir_path = Path(CWD) / base_dir_path

    if not base_dir_path.exists():
        LOG.error("{} does not exit. Not running tests".format(base_dir))
        sys.exit(69)

    return base_dir_path


async def _gen_check_output(
    cmd: Iterable[str],
    timeout: Union[int, float] = 30,
    env: Optional[Dict[str, str]] = None,
) -> Tuple[bytes, bytes]:
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env
    )
    try:
        (stdout, stderr) = await asyncio.wait_for(process.communicate(), timeout)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise

    if process.returncode != 0:
        cmd_str = " ".join(cmd)
        raise CalledProcessError(
            process.returncode, cmd_str, output=stdout, stderr=stderr
        )

    return (stdout, stderr)


async def _progress_reporter(
    progress_interval: Union[float, int], queue: asyncio.Queue, total_tests: int
) -> None:
    while queue.qsize() > 0:
        done_count = total_tests - queue.qsize()
        LOG.info(
            "{} / {} test suites ran ({}%)".format(
                done_count, total_tests, int((done_count / total_tests) * 100)
            )
        )
        await asyncio.sleep(progress_interval)

    LOG.debug("progress_reporter finished")


def _set_build_env(build_base_path: Optional[Path]) -> Dict[str, str]:
    build_environ = environ.copy()
    if not build_base_path:
        return build_environ

    if build_base_path.exists():
        build_env_vars = (
            ("PATH", build_base_path / "sbin"),
            ("PATH", build_base_path / "bin"),
            ("C_INCLUDE_PATH", build_base_path / "include"),
            ("CPLUS_INCLUDE_PATH", build_base_path / "include"),
        )

        for var_name, value in build_env_vars:
            if var_name in build_environ:
                build_environ[var_name] = "{}:{}".format(value, build_environ[var_name])
            else:
                build_environ[var_name] = str(value)
    else:
        LOG.error(
            "{} does not exist. Not add int PATH + INCLUDE Env variables".format(
                build_base_path
            )
        )

    return build_environ


def _set_pip_mirror(
    venv_path: Path, mirror: str = CONFIG["ptr"]["pypi_url"], timeout: int = 2
) -> None:
    pip_conf_path = venv_path / "pip.conf"
    with pip_conf_path.open("w") as pcfp:
        print(PIP_CONF_TEMPLATE.format(mirror, timeout), file=pcfp)


async def _test_steps_runner(
    test_run_start_time: int,
    tests_to_run: Dict[Path, Dict],
    setup_py_path: Path,
    venv_path: Path,
    env: Dict,
    print_cov: bool = False,
) -> Tuple[Optional[test_result], int]:
    black_exe = venv_path / "bin" / "black"
    coverage_exe = venv_path / "bin" / "coverage"
    mypy_exe = venv_path / "bin" / "mypy"
    pip_exe = venv_path / "bin" / "pip"
    config = tests_to_run[setup_py_path]
    setup_py_parent_path = setup_py_path.parent
    # For running unit tests via coverage in the venv
    test_entry_point = setup_py_parent_path / "{}.py".format(
        config["test_suite"].replace(".", path_separator)
    )

    steps = (
        step(
            StepName.pip_install,
            True,
            _generate_install_cmd(str(pip_exe), str(setup_py_path.parent), config),
            "Installing {} + deps".format(setup_py_path),
            config["test_suite_timeout"],
        ),
        step(
            StepName.tests_run,
            True,
            (str(coverage_exe), "run", str(test_entry_point)),
            "Running {} tests via coverage".format(test_entry_point),
            config["test_suite_timeout"],
        ),
        step(
            StepName.analyze_coverage,
            bool(
                "required_coverage" in config
                and config["required_coverage"]
                and len(config["required_coverage"]) > 0
            ),
            (str(coverage_exe), "report", "-m"),
            "Analyzing coverage report for {}".format(setup_py_path),
            config["test_suite_timeout"],
        ),
        step(
            StepName.mypy_run,
            bool("run_mypy" in config and config["run_mypy"]),
            _generate_mypy_cmd(setup_py_path.parent, mypy_exe, config),
            "Running mypy for {}".format(setup_py_path),
            config["test_suite_timeout"],
        ),
        step(
            StepName.black_run,
            bool("run_black" in config and config["run_black"]),
            _generate_black_cmd(setup_py_path.parent, black_exe),
            "Running black for {}".format(setup_py_path),
            config["test_suite_timeout"],
        ),
    )

    steps_ran = 0
    for a_step in steps:
        a_test_result = None
        # Skip test if disabled & not asked for print coverage on analyze_coverage
        if not a_step.run_condition:
            if (
                a_step.step_name is not StepName.analyze_coverage
                or not print_cov
                and a_step.step_name is StepName.analyze_coverage
            ):
                LOG.info("Not running {} step".format(a_step.log_message))
                continue

        LOG.info(a_step.log_message)
        steps_ran += 1
        try:
            if a_step.cmds:
                LOG.debug("CMD: {}".format(" ".join(a_step.cmds)))
                stdout, stderr = await _gen_check_output(
                    a_step.cmds, a_step.timeout, env=env
                )
            else:
                LOG.debug("Skipping running a cmd for {} step".format(a_step))
        except CalledProcessError as cpe:
            if a_step.step_name in {StepName.mypy_run}:
                err_output = cpe.stdout.decode("utf-8")
            else:
                err_output = cpe.stderr.decode("utf-8")

            LOG.debug("{} FAILED for {}".format(a_step.log_message, setup_py_path))
            a_test_result = test_result(
                setup_py_path,
                a_step.step_name.value,
                err_output,
                int(time() - test_run_start_time),
                False,
            )
        except asyncio.TimeoutError as toe:
            LOG.debug(
                "{} timed out running {} ({})".format(
                    setup_py_path, a_step.log_message, toe
                )
            )
            a_test_result = test_result(
                setup_py_path,
                a_step.step_name.value,
                "Timeout during {}".format(a_step.log_message),
                a_step.timeout,
                True,
            )

        if a_step.step_name is StepName.analyze_coverage:
            cov_report = stdout.decode("utf-8")
            if print_cov:
                print("{}:\n{}".format(setup_py_path, cov_report))

            if a_step.run_condition:
                a_test_result = _analyze_coverage(
                    venv_path, setup_py_path, config["required_coverage"], cov_report
                )

        # If we've had a failure return
        if a_test_result:
            return a_test_result, steps_ran

    return None, steps_ran


async def _test_runner(
    queue: asyncio.Queue,
    tests_to_run: Dict[Path, Dict],
    test_results: List[test_result],
    venv_path: Path,
    print_cov: bool,
    stats: Dict[str, int],
    idx: int,
) -> None:

    # Set a unique location for coverage to write its data file per coroutine
    cov_data_path = Path(gettempdir()) / "ptr.{}.{}.coverage".format(getpid(), idx)
    extra_build_env_path = (
        Path(CONFIG["ptr"]["extra_build_env_prefix"])
        if "extra_build_env_prefix" in CONFIG["ptr"]
        else None
    )
    env = _set_build_env(extra_build_env_path)
    env["COVERAGE_FILE"] = str(cov_data_path)

    while True:
        try:
            setup_py_path = queue.get_nowait()
        except asyncio.QueueEmpty:
            LOG.debug("test_runner {} exiting".format(idx))
            if cov_data_path.exists():
                cov_data_path.unlink()
            return

        test_run_start_time = int(time())
        test_fail_result, steps_ran = await _test_steps_runner(
            test_run_start_time, tests_to_run, setup_py_path, venv_path, env, print_cov
        )
        total_success_runtime = int(time() - test_run_start_time)
        if test_fail_result:
            test_results.append(test_fail_result)
        else:
            success_output = "{} has passed all configured tests".format(setup_py_path)
            LOG.info(success_output)
            test_results.append(
                test_result(
                    setup_py_path, 0, success_output, total_success_runtime, False
                )
            )

        stats_name = setup_py_path.parent.name
        stats["suite.{}_runtime".format(stats_name)] = total_success_runtime
        stats["suite.{}_completed_steps".format(stats_name)] = steps_ran

        queue.task_done()


async def create_venv(
    mirror: str, py_exe: str = sys.executable, install_pkgs: bool = True
) -> Optional[Path]:
    start_time = time()
    venv_path = Path(gettempdir()) / "ptr_venv_{}".format(getpid())
    pip_exe = venv_path / "bin" / "pip"
    try:
        await _gen_check_output((py_exe, "-m", "venv", str(venv_path)))
        _set_pip_mirror(venv_path, mirror)
        if install_pkgs:
            await _gen_check_output(
                (
                    str(pip_exe),
                    "install",
                    "--upgrade",
                    *CONFIG["ptr"]["venv_pkgs"].split(),
                )
            )
    except CalledProcessError as cpe:
        LOG.exception("Failed to setup venv @ {} ({})".format(venv_path, cpe))
        return None

    runtime = int(time() - start_time)
    LOG.info(
        "Successfully created venv @ {} to run tests ({}s)".format(venv_path, runtime)
    )
    return venv_path


def find_py_files(py_files: Set[str], base_dir: Path) -> None:
    dirs = [d for d in base_dir.iterdir() if d.is_dir()]
    py_files.update(
        {str(x) for x in base_dir.iterdir() if x.is_file() and x.suffix == ".py"}
    )
    for directory in dirs:
        find_py_files(py_files, directory)


def find_setup_pys(
    base_path: Path, exclude_patterns: Set[str], follow_symlinks: bool = False
) -> Set[Path]:
    def _recursive_find_files(files: Set[Path], base_dir: Path) -> None:
        dirs = [d for d in base_dir.iterdir() if d.is_dir()]
        files.update(
            {x for x in base_dir.iterdir() if x.is_file() and x.name == "setup.py"}
        )
        for directory in dirs:
            if not follow_symlinks and directory.is_symlink():
                continue

            skip_dir = False
            for exclude_pattern in exclude_patterns:
                if directory.match(exclude_pattern):
                    skip_dir = True
                    LOG.debug(
                        "Skipping {} due to exclude pattern {}".format(
                            directory, exclude_pattern
                        )
                    )
            if not skip_dir:
                _recursive_find_files(files, directory)

    setup_pys = set()  # type: Set[Path]
    _recursive_find_files(setup_pys, base_path)
    return setup_pys


def parse_setup_cfg(setup_py: Path) -> Dict[str, Any]:
    req_cov_key_strip = "required_coverage_"
    ptr_params = {}  # type: Dict[str, Any]
    setup_cfg = setup_py.parent / "setup.cfg"
    if not setup_cfg.exists():
        return ptr_params

    cp = ConfigParser()
    # Have configparser maintain key case - T484 error = callable
    cp.optionxform = str  # type: ignore
    cp.read(setup_cfg)
    if "ptr" not in cp:
        LOG.info("{} does not have a ptr section")
        return ptr_params

    # Create a setup.py like ptr_params to return
    ptr_params["required_coverage"] = {}
    for key, value in cp["ptr"].items():
        if key.startswith(req_cov_key_strip):
            key = key.strip(req_cov_key_strip)
            ptr_params["required_coverage"][key] = int(value)
        elif key.startswith("run_"):
            ptr_params[key] = cp.getboolean("ptr", key)
        elif key == "test_suite_timeout":
            ptr_params[key] = cp.getint("ptr", key)
        else:
            ptr_params[key] = value

    return ptr_params


def print_test_results(
    test_results: Sequence[test_result], stats: Optional[Dict[str, int]] = None
) -> Dict[str, int]:
    if not stats:
        stats = defaultdict(int)

    stats["total.test_suites"] = len(test_results)

    fail_output = ""
    for result in sorted(test_results):
        if result.returncode:
            if result.timeout:
                stats["total.timeouts"] += 1
            else:
                stats["total.fails"] += 1
            fail_output += "{}:\n{}\n".format(result.setup_py_path, result.output)
        else:
            stats["total.passes"] += 1

    total_time = -1 if "runtime.all_tests" not in stats else stats["runtime.all_tests"]
    print("-- Summary (total time {}s):\n".format(total_time))
    print(
        "✅ PASS: {}\n❌ FAIL: {}\n⌛️ TIMEOUT: {}\n💩 TOTAL: {}\n".format(
            stats["total.passes"],
            stats["total.fails"],
            stats["total.timeouts"],
            stats["total.test_suites"],
        )
    )
    if "total.setup_pys" in stats:
        stats["pct.setup_py_ptr_enabled"] = int(
            (stats["total.test_suites"] / stats["total.setup_pys"]) * 100
        )
        print(
            "-- {} / {} ({}%) `setup.py`'s have `ptr` tests running\n".format(
                stats["total.test_suites"],
                stats["total.setup_pys"],
                stats["pct.setup_py_ptr_enabled"],
            )
        )
    if fail_output:
        print("-- Failure Output --\n")
        print(fail_output)

    return stats


async def run_tests(
    atonce: int,
    mirror: str,
    tests_to_run: Dict[Path, Dict],
    progress_interval: Union[float, int],
    venv_path: Optional[Path],
    venv_keep: bool,
    print_cov: bool,
    stats: Dict[str, int],
    stats_file: str,
) -> int:
    tests_start_time = time()

    if not venv_path or not venv_path.exists():
        venv_create_start_time = time()
        venv_path = await create_venv(mirror=mirror)
        stats["venv_create_time"] = int(time() - venv_create_start_time)
    else:
        venv_keep = True
    if not venv_path or not venv_path.exists():
        LOG.error("Unable to make a venv to run tests in. Exiting")
        return 3

    # Be at the base of the venv to ensure we have a known neutral cwd
    chdir(str(venv_path))

    # Create Awaitables and run all sorted tests in parallel to be more predictable
    # Python 3.5 does not have queue type
    queue = asyncio.Queue()  # type: asyncio.Queue
    for test_setup_py in sorted(tests_to_run.keys()):
        await queue.put(test_setup_py)

    test_results = []  # type: List[test_result]
    consumers = [
        _test_runner(
            queue, tests_to_run, test_results, venv_path, print_cov, stats, i + 1
        )
        for i in range(atonce)
    ]
    if progress_interval:
        LOG.debug(
            "Adding progress reporter to report every {}s".format(progress_interval)
        )
        consumers.append(
            _progress_reporter(progress_interval, queue, len(tests_to_run))
        )

    LOG.debug("Starting to run tests")
    await asyncio.gather(*consumers)

    stats["runtime.all_tests"] = int(time() - tests_start_time)
    stats = print_test_results(test_results, stats)
    _write_stats_file(stats_file, stats)

    if not venv_keep:
        chdir(gettempdir())
        rmtree(str(venv_path))
    else:
        LOG.info("Not removing venv @ {} due to CLI arguments".format(venv_path))

    return stats["total.fails"] + stats["total.timeouts"]


async def async_main(
    atonce: int,
    base_path: Path,
    mirror: str,
    progress_interval: Union[float, int],
    venv: str,
    venv_keep: bool,
    print_cov: bool,
    stats_file: str,
) -> int:
    stats = defaultdict(int)  # type: Dict[str, int]
    tests_to_run = _get_test_modules(base_path, stats)
    if not tests_to_run:
        LOG.error(
            "{} has no setup.py files with unit tests defined. Exiting".format(
                str(base_path)
            )
        )
        return 1

    try:
        venv_path = Path(venv)  # type: Optional[Path]
        if venv_path and not venv_path.exists():
            LOG.error("{} venv does not exist. Please correct!".format(venv_path))
            return 2
    except TypeError:
        venv_path = None

    return await run_tests(
        atonce,
        mirror,
        tests_to_run,
        progress_interval,
        venv_path,
        venv_keep,
        print_cov,
        stats,
        stats_file,
    )


def main() -> None:
    default_stats_file = Path(gettempdir()) / "ptr_stats_{}".format(getpid())
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-a",
        "--atonce",
        default=int(CONFIG["ptr"]["atonce"]),
        type=int,
        help="How many tests to run at once [Default: {}]".format(
            int(CONFIG["ptr"]["atonce"])
        ),
    )
    parser.add_argument(
        "-b",
        "--base-dir",
        default=CWD,
        help="Path to recursively look for setup.py files [Default: {}]".format(CWD),
    )
    parser.add_argument(
        "-d", "--debug", action="store_true", help="Verbose debug output"
    )
    parser.add_argument(
        "-k", "--keep-venv", action="store_true", help="Do not remove created venv"
    )
    parser.add_argument(
        "-m",
        "--mirror",
        default=CONFIG["ptr"]["pypi_url"],
        help="URL for pip to use for Simple API [Default: {}]".format(
            CONFIG["ptr"]["pypi_url"]
        ),
    )
    parser.add_argument(
        "--print-cov", action="store_true", help="Print modules coverage report"
    )
    parser.add_argument(
        "--progress-interval",
        default=0,
        type=float,
        help="Seconds between status update on test running [Default: Disabled]",
    )
    parser.add_argument(
        "--stats-file",
        default=str(default_stats_file),
        help="JSON statistics file [Default: {}]".format(default_stats_file),
    )
    parser.add_argument("--venv", help="Path to venv to reuse")
    args = parser.parse_args()
    _handle_debug(args.debug)

    LOG.info("Starting {}".format(sys.argv[0]))
    loop = asyncio.get_event_loop()
    try:
        sys.exit(
            loop.run_until_complete(
                async_main(
                    args.atonce,
                    _validate_base_dir(args.base_dir),
                    args.mirror,
                    args.progress_interval,
                    args.venv,
                    args.keep_venv,
                    args.print_cov,
                    args.stats_file,
                )
            )
        )
    finally:
        loop.close()


if __name__ == "__main__":
    main()  # pragma: no cover
