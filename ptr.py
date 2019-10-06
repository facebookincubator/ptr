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
from os.path import sep
from pathlib import Path
from platform import system
from shutil import rmtree
from subprocess import CalledProcessError
from tempfile import gettempdir
from time import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union


LOG = logging.getLogger(__name__)
MACOSX = system() == "Darwin"
WINDOWS = system() == "Windows"
# Windows needs to use a ProactorEventLoop for subprocesses
# Need to use sys.platform for mypy to understand
# https://mypy.readthedocs.io/en/latest/common_issues.html#python-version-and-system-platform-checks  # noqa: B950 # pylint: disable=C0301
if sys.platform == "win32":
    asyncio.set_event_loop(asyncio.ProactorEventLoop())


def _config_default() -> ConfigParser:
    if WINDOWS:
        venv_pkgs = "black coverage flake8 mypy pip pylint setuptools"
    else:
        venv_pkgs = "black coverage flake8 mypy pip pylint pyre-check setuptools"

    LOG.info("Using default config settings")
    cp = ConfigParser()
    cp["ptr"] = {}
    cp["ptr"]["atonce"] = str(int((cpu_count() or 20) / 2))
    cp["ptr"]["exclude_patterns"] = "build* yocto"
    cp["ptr"]["pypi_url"] = "https://pypi.org/simple/"
    cp["ptr"]["venv_pkgs"] = venv_pkgs
    return cp


def _config_read(cwd: str, conf_name: str = ".ptrconfig") -> Optional[ConfigParser]:
    """ Look from cwd to / for a "conf_name" file - If so read it in """
    cp = None
    cwd_path = Path(cwd)  # type: Path
    root_path = Path("{}\\".format(cwd_path.drive)) if WINDOWS else Path("/")

    while cwd_path:
        ptrconfig_path = cwd_path / conf_name
        if ptrconfig_path.exists():
            cp = ConfigParser()
            cp.read(str(ptrconfig_path))

            LOG.info("Loading found config @ {}".format(ptrconfig_path))
            break

        if cwd_path == root_path:
            break

        cwd_path = cwd_path.parent

    return cp


CWD = getcwd()
CONFIG = _config_read(CWD) or _config_default()
PIP_CONF_TEMPLATE = """\
[global]
index-url = {}
timeout = {}"""
# Windows venv + pip are super slow
VENV_TIMEOUT = 120 if WINDOWS or MACOSX else 30


class StepName(Enum):
    pip_install = 1
    tests_run = 2
    analyze_coverage = 3
    mypy_run = 4
    black_run = 5
    pylint_run = 6
    flake8_run = 7
    pyre_run = 8


coverage_line = namedtuple("coverage_line", ["stmts", "miss", "cover", "missing"])
step = namedtuple(
    "step", ["step_name", "run_condition", "cmds", "log_message", "timeout"]
)
test_result = namedtuple(
    "test_result", ["setup_py_path", "returncode", "output", "runtime", "timeout"]
)


def _get_site_packages_path(venv_path: Path) -> Optional[Path]:
    lib_path = venv_path / ("Lib" if WINDOWS else "lib")
    for apath in lib_path.iterdir():
        if apath.is_dir() and apath.match("python*"):
            return apath / "site-packages"
        if apath.is_dir() and apath.name == "site-packages":
            return apath

    LOG.error("Unable to find a python lib dir in {}".format(lib_path))
    return None


def _analyze_coverage(
    venv_path: Path,
    setup_py_path: Path,
    required_cov: Dict[str, int],
    coverage_report: str,
    stats: Dict[str, int],
) -> Optional[test_result]:
    module_path = setup_py_path.parent
    site_packages_path = _get_site_packages_path(venv_path)
    if not site_packages_path:
        LOG.error("Analyze coverage is unable to find site-packages path")
        return None
    relative_site_packages = str(site_packages_path.relative_to(venv_path)) + sep

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
    for line in coverage_report.splitlines():
        if not line or line.startswith("-") or line.startswith("Name"):
            continue

        module_path_str = None
        sl_path = None

        sl = line.split(maxsplit=4)
        if sl[0] != "TOTAL":
            sl_path = _max_osx_private_handle(sl[0], site_packages_path)

        if sl_path and sl_path.is_absolute() and site_packages_path:
            for possible_abs_path in (module_path, site_packages_path):
                try:
                    module_path_str = str(sl_path.relative_to(possible_abs_path))
                except ValueError as ve:
                    LOG.debug(ve)
        elif sl_path:
            module_path_str = str(sl_path).replace(relative_site_packages, "")
        else:
            module_path_str = sl[0]

        if not module_path_str:
            LOG.error(
                "[{}] Unable to find path relative path for {}".format(
                    setup_py_path, sl[0]
                )
            )
            continue

        if len(sl) == 4:
            coverage_lines[module_path_str] = coverage_line(
                int(sl[1]), int(sl[2]), int(sl[3][:-1]), ""
            )
        else:
            coverage_lines[module_path_str] = coverage_line(
                int(sl[1]), int(sl[2]), int(sl[3][:-1]), sl[4]
            )

        if sl[0] != "TOTAL":
            stats[
                "suite.{}_coverage.file.{}".format(module_path.name, module_path_str)
            ] = coverage_lines[module_path_str].cover
        else:
            stats["suite.{}_coverage.total".format(module_path.name)] = coverage_lines[
                module_path_str
            ].cover

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


def _max_osx_private_handle(
    potenital_path: str, site_packages_path: Path
) -> Optional[Path]:
    """ On Mac OS X `coverage` seems to always resolve /private for anything stored in /var.
        ptr's usage of gettempdir() seems to result in using dirs within there
        This function strips /private if it exists on the path supplied from coverage
        ONLY IF site_packages_path is not based in /private"""
    if not MACOSX:
        return Path(potenital_path)

    private_path = Path("/private")
    try:
        site_packages_path.relative_to(private_path)
        return Path(potenital_path)
    except ValueError:
        pass

    return Path(potenital_path.replace("/private", ""))


def _write_stats_file(stats_file: str, stats: Dict[str, int]) -> None:
    stats_file_path = Path(stats_file)
    if not stats_file_path.is_absolute():
        stats_file_path = Path(CWD) / stats_file_path
    try:
        with stats_file_path.open("w", encoding="utf8") as sfp:
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
    if config.get("run_mypy", False):
        mypy_entry_point = module_dir / "{}.py".format(config["entry_point_module"])
    else:
        return ()

    cmds = [str(mypy_exe)]
    mypy_ini_path = module_dir / "mypy.ini"
    if mypy_ini_path.exists():
        cmds.extend(["--config", str(mypy_ini_path)])
    cmds.append(str(mypy_entry_point))
    return tuple(cmds)


def _generate_flake8_cmd(
    module_dir: Path, flake8_exe: Path, config: Dict
) -> Tuple[str, ...]:
    if not config.get("run_flake8", False):
        return ()

    py_files = set()  # type: Set[str]
    find_py_files(py_files, module_dir)

    cmds = [str(flake8_exe)]
    flake8_config = module_dir / ".flake8"
    if flake8_config.exists():
        cmds.extend(["--config", str(flake8_config)])
    return (*cmds, *sorted(py_files))


def _generate_pylint_cmd(
    module_dir: Path, pylint_exe: Path, config: Dict
) -> Tuple[str, ...]:
    if not config.get("run_pylint", False):
        return ()

    py_files = set()  # type: Set[str]
    find_py_files(py_files, module_dir)

    cmds = [str(pylint_exe)]
    pylint_config = module_dir / ".pylint"
    if pylint_config.exists():
        cmds.extend(["--rcfile", str(pylint_config)])
    return (*cmds, *sorted(py_files))


def _generate_pyre_cmd(
    module_dir: Path, pyre_exe: Path, config: Dict
) -> Tuple[str, ...]:
    if not config.get("run_pyre", False) or WINDOWS:
        return ()

    return (str(pyre_exe), "--source-directory", str(module_dir), "check")


def _parse_setup_params(setup_py: Path) -> Dict[str, Any]:
    with setup_py.open("r", encoding="utf8") as sp:
        setup_tree = ast.parse(sp.read())

    LOG.debug("AST visiting {}".format(setup_py))
    for node in ast.walk(setup_tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                target_id = getattr(target, "id", None)
                if not target_id:
                    continue

                if target_id == "ptr_params":
                    LOG.debug("Found ptr_params in {}".format(setup_py))
                    ptr_params = dict(ast.literal_eval(node.value))
                    if "test_suite" in ptr_params:
                        return ptr_params
                    LOG.info(
                        "{} does not have a suite. Nothing to run".format(setup_py)
                    )
                    break
    return {}


def _get_test_modules(
    base_path: Path,
    stats: Dict[str, int],
    run_disabled: bool,
    print_non_configured: bool,
) -> Dict[Path, Dict]:
    get_tests_start_time = time()
    all_setup_pys = find_setup_pys(
        base_path,
        set(CONFIG["ptr"]["exclude_patterns"].split())
        if CONFIG["ptr"]["exclude_patterns"]
        else set(),
    )
    stats["total.setup_pys"] = len(all_setup_pys)

    non_configured_modules = []  # type: List[Path]
    test_modules = {}  # type: Dict[Path, Dict]
    for setup_py in all_setup_pys:
        disabled_err_msg = "Not running {} as ptr is disabled via config".format(
            setup_py
        )
        # If a setup.cfg exists lets prefer it, if there is a [ptr] section
        ptr_params = parse_setup_cfg(setup_py)
        if not ptr_params:
            ptr_params = _parse_setup_params(setup_py)

        if ptr_params:
            if ptr_params.get("disabled", False) and not run_disabled:
                LOG.info(disabled_err_msg)
                stats["total.disabled"] += 1
            else:
                test_modules[setup_py] = ptr_params

        if setup_py not in test_modules:
            non_configured_modules.append(setup_py)

    if print_non_configured and non_configured_modules:
        print_non_configured_modules(non_configured_modules)

    stats["total.non_ptr_setup_pys"] = len(non_configured_modules)
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
    cwd: Optional[Path] = None,
) -> Tuple[bytes, bytes]:
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
        cwd=cwd,
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
    progress_interval: float, queue: asyncio.Queue, total_tests: int
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

    if not build_base_path or not build_base_path.exists():
        if build_base_path:
            LOG.error(
                "Configured local build env path {} does not exist".format(
                    build_base_path
                )
            )
        return build_environ

    if build_base_path.exists():
        build_env_vars = [
            (
                ("PATH", build_base_path / "Scripts")
                if WINDOWS
                else ("PATH", build_base_path / "sbin")
            ),
            ("C_INCLUDE_PATH", build_base_path / "include"),
            ("CPLUS_INCLUDE_PATH", build_base_path / "include"),
        ]
        if not WINDOWS:
            build_env_vars.append(("PATH", build_base_path / "bin"))

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
    with pip_conf_path.open("w", encoding="utf8") as pcfp:
        print(PIP_CONF_TEMPLATE.format(mirror, timeout), file=pcfp)


async def _test_steps_runner(  # pylint: disable=R0914
    test_run_start_time: int,
    tests_to_run: Dict[Path, Dict],
    setup_py_path: Path,
    venv_path: Path,
    env: Dict,
    stats: Dict[str, int],
    error_on_warnings: bool,
    print_cov: bool = False,
) -> Tuple[Optional[test_result], int]:
    bin_dir = "Scripts" if WINDOWS else "bin"
    exe = ".exe" if WINDOWS else ""
    black_exe = venv_path / bin_dir / "black{}".format(exe)
    coverage_exe = venv_path / bin_dir / "coverage{}".format(exe)
    flake8_exe = venv_path / bin_dir / "flake8{}".format(exe)
    mypy_exe = venv_path / bin_dir / "mypy{}".format(exe)
    pip_exe = venv_path / bin_dir / "pip{}".format(exe)
    pylint_exe = venv_path / bin_dir / "pylint{}".format(exe)
    pyre_exe = venv_path / bin_dir / "pyre{}".format(exe)
    config = tests_to_run[setup_py_path]

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
            (str(coverage_exe), "run", "-m", config["test_suite"]),
            "Running {} tests via coverage".format(config["test_suite"]),
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
        step(
            StepName.flake8_run,
            bool("run_flake8" in config and config["run_flake8"]),
            _generate_flake8_cmd(setup_py_path.parent, flake8_exe, config),
            "Running flake8 for {}".format(setup_py_path),
            config["test_suite_timeout"],
        ),
        step(
            StepName.pylint_run,
            bool("run_pylint" in config and config["run_pylint"]),
            _generate_pylint_cmd(setup_py_path.parent, pylint_exe, config),
            "Running pylint for {}".format(setup_py_path),
            config["test_suite_timeout"],
        ),
        step(
            StepName.pyre_run,
            bool("run_pyre" in config and config["run_pyre"] and not WINDOWS),
            _generate_pyre_cmd(setup_py_path.parent, pyre_exe, config),
            "Running pyre for {}".format(setup_py_path),
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
        stdout = b""
        steps_ran += 1
        try:
            if a_step.cmds:
                LOG.debug("CMD: {}".format(" ".join(a_step.cmds)))

                # If we're running tests and we want warnings to be errors
                step_env = env
                if a_step.step_name == StepName.tests_run and error_on_warnings:
                    step_env = env.copy()
                    step_env["PYTHONWARNINGS"] = "error"
                    LOG.debug("Setting PYTHONWARNINGS to error: {}".format(step_env))

                stdout, _stderr = await _gen_check_output(
                    a_step.cmds, a_step.timeout, env=step_env, cwd=setup_py_path.parent
                )
            else:
                LOG.debug("Skipping running a cmd for {} step".format(a_step))
        except CalledProcessError as cpe:
            err_output = cpe.stdout.decode("utf8")

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
            cov_report = stdout.decode("utf8") if stdout else ""
            if print_cov:
                print("{}:\n{}".format(setup_py_path, cov_report))

            if a_step.run_condition:
                a_test_result = _analyze_coverage(
                    venv_path,
                    setup_py_path,
                    config["required_coverage"],
                    cov_report,
                    stats,
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
    error_on_warnings: bool,
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
            test_run_start_time,
            tests_to_run,
            setup_py_path,
            venv_path,
            env,
            stats,
            error_on_warnings,
            print_cov,
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
    mirror: str,
    py_exe: str = sys.executable,
    install_pkgs: bool = True,
    timeout: float = VENV_TIMEOUT,
) -> Optional[Path]:
    start_time = time()
    venv_path = Path(gettempdir()) / "ptr_venv_{}".format(getpid())
    if WINDOWS:
        pip_exe = venv_path / "Scripts" / "pip.exe"
    else:
        pip_exe = venv_path / "bin" / "pip"

    install_cmd: List[str] = []
    try:
        await _gen_check_output((py_exe, "-m", "venv", str(venv_path)), timeout=timeout)
        _set_pip_mirror(venv_path, mirror)
        if install_pkgs:
            install_cmd = [str(pip_exe), "install"]
            # TODO: Workout why Windows can't uninstall / upgrade pip on Azure
            # https://github.com/facebookincubator/ptr/issues/33
            if not WINDOWS:
                install_cmd.append("--upgrade")
            install_cmd.extend(CONFIG["ptr"]["venv_pkgs"].split())
            await _gen_check_output(install_cmd, timeout=timeout)
    except CalledProcessError as cpe:
        LOG.exception(
            "Failed to setup venv @ {} - '{}'' ({})".format(venv_path, install_cmd, cpe)
        )
        if cpe.stderr:
            LOG.debug("venv stderr:\n{}".format(cpe.stderr.decode("utf8")))
        if cpe.output:
            LOG.debug("venv stdout:\n{}".format(cpe.output.decode("utf8")))
        return None

    runtime = int(time() - start_time)
    LOG.info(
        "Successfully created venv @ {} to run tests ({}s)".format(venv_path, runtime)
    )
    return venv_path


def find_py_files(py_files: Set[str], base_dir: Path) -> None:
    dirs = [d for d in base_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
    py_files.update(
        {str(x) for x in base_dir.iterdir() if x.is_file() and x.suffix == ".py"}
    )
    for directory in dirs:
        find_py_files(py_files, directory)


def _recursive_find_files(
    files: Set[Path], base_dir: Path, exclude_patterns: Set[str], follow_symlinks: bool
) -> None:
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
            _recursive_find_files(files, directory, exclude_patterns, follow_symlinks)


def find_setup_pys(
    base_path: Path, exclude_patterns: Set[str], follow_symlinks: bool = False
) -> Set[Path]:
    setup_pys = set()  # type: Set[Path]
    _recursive_find_files(setup_pys, base_path, exclude_patterns, follow_symlinks)
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
        elif key.startswith("run_") or key == "disabled":
            ptr_params[key] = cp.getboolean("ptr", key)
        elif key == "test_suite_timeout":
            ptr_params[key] = cp.getint("ptr", key)
        else:
            ptr_params[key] = value

    return ptr_params


def print_non_configured_modules(modules: List[Path]) -> None:
    print("== {} non ptr configured modules ==".format(len(modules)))
    for module in sorted(modules):
        print(" - {}".format(str(module)))


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
            fail_output += "{} (failed '{}' step):\n{}\n".format(
                result.setup_py_path, StepName(result.returncode).name, result.output
            )
        else:
            stats["total.passes"] += 1

    total_time = -1 if "runtime.all_tests" not in stats else stats["runtime.all_tests"]
    print("-- Summary (total time {}s):\n".format(total_time))
    # TODO: Hardcode some workaround to ensure Windows always prints UTF8
    # https://github.com/facebookincubator/ptr/issues/34
    print(
        "✅ PASS: {}\n❌ FAIL: {}\n️⌛ TIMEOUT: {}\n🔒 DISABLED: {}\n💩 TOTAL: {}\n".format(
            stats["total.passes"],
            stats["total.fails"],
            stats["total.timeouts"],
            stats["total.disabled"],
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
    venv_timeout: float,
    error_on_warnings: bool,
) -> int:
    tests_start_time = time()

    if not venv_path or not venv_path.exists():
        venv_create_start_time = time()
        venv_path = await create_venv(mirror=mirror, timeout=venv_timeout)
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
            queue,
            tests_to_run,
            test_results,
            venv_path,
            print_cov,
            stats,
            error_on_warnings,
            i + 1,
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
    progress_interval: float,
    venv: str,
    venv_keep: bool,
    print_cov: bool,
    print_non_configured: bool,
    run_disabled: bool,
    stats_file: str,
    venv_timeout: float,
    error_on_warnings: bool,
) -> int:
    stats = defaultdict(int)  # type: Dict[str, int]
    tests_to_run = _get_test_modules(
        base_path, stats, run_disabled, print_non_configured
    )
    if not tests_to_run:
        LOG.error(
            "{} has no setup.py files with unit tests defined. Exiting".format(
                str(base_path)
            )
        )
        return 1

    if print_non_configured:
        return 0

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
        venv_timeout,
        error_on_warnings,
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
        "-e",
        "--error-on-warnings",
        action="store_true",
        help="Have Python warnings raise DeprecationWarning",
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
        "--print-non-configured",
        action="store_true",
        help="Print modules not configured to run ptr",
    )
    parser.add_argument(
        "--progress-interval",
        default=0,
        type=float,
        help="Seconds between status update on test running [Default: Disabled]",
    )
    parser.add_argument(
        "--run-disabled",
        action="store_true",
        help="Force any disabled tests suites to run",
    )
    parser.add_argument(
        "--stats-file",
        default=str(default_stats_file),
        help="JSON statistics file [Default: {}]".format(default_stats_file),
    )
    parser.add_argument("--venv", help="Path to venv to reuse")
    parser.add_argument(
        "--venv-timeout",
        type=int,
        default=VENV_TIMEOUT,
        help="Timeout in seconds for venv creation + deps install [Default: {}]".format(
            VENV_TIMEOUT
        ),
    )
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
                    args.print_non_configured,
                    args.run_disabled,
                    args.stats_file,
                    args.venv_timeout,
                    args.error_on_warnings,
                )
            )
        )
    finally:
        loop.close()


if __name__ == "__main__":
    main()  # pragma: no cover
