#!/usr/bin/env python3
# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
# coding=utf8

import asyncio
import unittest
from collections import defaultdict
from copy import deepcopy
from os import environ
from pathlib import Path
from shutil import rmtree
from subprocess import CalledProcessError
from tempfile import TemporaryDirectory, gettempdir
from typing import (  # noqa: F401 # pylint: disable=unused-import
    Any,
    Dict,
    List,
    Optional,
    Sequence,
    Tuple,
)
from unittest.mock import Mock, patch

import ptr
import ptr_tests_fixtures


# Turn off logging for unit tests - Comment out to enable
ptr.LOG = Mock()
# Hacky global for a monkey patch of asyncio.qsize()
TOTAL_REPORTER_TESTS = 4


async def async_none(*args: Any, **kwargs: Any) -> None:
    return None


async def check_site_package_config(cmd: Sequence, *args: Any, **kwargs: Any) -> None:
    assert "--system-site-packages" in cmd, f"--system-site-packages not found in {cmd}"


def fake_get_event_loop(*args: Any, **kwargs: Any) -> ptr_tests_fixtures.FakeEventLoop:
    return ptr_tests_fixtures.FakeEventLoop()


async def fake_test_steps_runner(
    *args: Any, **kwargs: Any
) -> Tuple[Optional[ptr.test_result], int]:
    return (None, TOTAL_REPORTER_TESTS)


async def return_bytes_output(*args: Any, **kwargs: Any) -> Tuple[bytes, bytes]:
    return (b"Unitest stdout", b"Unittest stderr")


def return_specific_pid(*args: Any, **kwargs: Any) -> int:
    return 2580217


def return_zero(*args: Any, **kwargs: Any) -> int:
    return 0


def touch_files(*paths: Path) -> None:
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)


class TestPtr(unittest.TestCase):
    maxDiff = 2000

    def setUp(self) -> None:
        self.loop = asyncio.get_event_loop()

    @patch("ptr._get_site_packages_path")
    def test_analyze_coverage_errors(self, mock_path: Mock) -> None:
        mock_path.return_value = None
        fake_path = Path(gettempdir())
        self.assertIsNone(ptr._analyze_coverage(fake_path, fake_path, {}, "", {}, 0))
        mock_path.return_value = fake_path
        self.assertIsNone(
            ptr._analyze_coverage(fake_path, fake_path, {}, "Fake Cov Report", {}, 0)
        )

    @patch("ptr.time")
    @patch("ptr.LOG.error")
    @patch("ptr.getpid", return_specific_pid)
    def test_analyze_coverage(self, mock_log: Mock, mock_time: Mock) -> None:
        mock_time.return_value = 0
        fake_setup_py = Path("unittest/setup.py")
        if "VIRTUAL_ENV" in environ:
            fake_venv_path = Path(environ["VIRTUAL_ENV"])
        else:
            fake_venv_path = self.loop.run_until_complete(
                ptr.create_venv("https://pypi.com/s", install_pkgs=False)
            )
        self.assertIsNone(
            ptr._analyze_coverage(fake_venv_path, fake_setup_py, {}, "", {}, 0)
        )
        self.assertIsNone(
            ptr._analyze_coverage(fake_venv_path, fake_setup_py, {"bla": 69}, "", {}, 0)
        )

        # Test with simple py_modules
        self.assertEqual(
            ptr._analyze_coverage(
                fake_venv_path,
                fake_setup_py,
                ptr_tests_fixtures.FAKE_REQ_COVERAGE,
                ptr_tests_fixtures.SAMPLE_REPORT_OUTPUT,
                {},
                0,
            ),
            ptr_tests_fixtures.EXPECTED_COVERAGE_FAIL_RESULT,
        )

        # Test with float coverage
        self.assertEqual(
            ptr._analyze_coverage(
                fake_venv_path,
                fake_setup_py,
                ptr_tests_fixtures.FAKE_REQ_COVERAGE,
                ptr_tests_fixtures.SAMPLE_FLOAT_REPORT_OUTPUT,
                {},
                0,
            ),
            ptr_tests_fixtures.EXPECTED_COVERAGE_FAIL_RESULT,
        )

        # Test with venv installed modules
        cov_report = (
            ptr_tests_fixtures.SAMPLE_WIN_TG_REPORT_OUTPUT
            if ptr.WINDOWS
            else ptr_tests_fixtures.SAMPLE_NIX_TG_REPORT_OUTPUT
        )
        self.assertEqual(
            ptr._analyze_coverage(
                fake_venv_path,
                fake_setup_py,
                ptr_tests_fixtures.FAKE_TG_REQ_COVERAGE,
                cov_report,
                {},
                0,
            ),
            ptr_tests_fixtures.EXPECTED_PTR_COVERAGE_FAIL_RESULT,
        )
        # Test we error on non existent files with coverage requirements
        self.assertEqual(
            ptr._analyze_coverage(
                fake_venv_path, fake_setup_py, {"fake_file.py": 48}, cov_report, {}, 0
            ),
            ptr_tests_fixtures.EXPECTED_PTR_COVERAGE_MISSING_FILE_RESULT,
        )
        self.assertTrue(mock_log.called)
        # Dont delete the VIRTUAL_ENV carrying the test if we didn't make it
        if "VIRTUAL_ENV" not in environ:
            rmtree(fake_venv_path)

    def test_mac_osx_slash_private(self) -> None:
        macosx = ptr.MACOSX
        non_private_path_str = "/var/tmp"
        private_path_str = f"/private{non_private_path_str}"
        site_packages_path = Path("/var/tmp/venv/lib/site-packages/")
        try:
            ptr.MACOSX = False
            self.assertEqual(
                Path(private_path_str),
                ptr._max_osx_private_handle(private_path_str, site_packages_path),
            )

            ptr.MACOSX = True
            self.assertEqual(
                Path(non_private_path_str),
                ptr._max_osx_private_handle(private_path_str, site_packages_path),
            )

            site_packages_path = Path("/private/var/tmp/venv/lib/site-packages/")
            self.assertEqual(
                Path(private_path_str),
                ptr._max_osx_private_handle(private_path_str, site_packages_path),
            )
        finally:
            # Ensure we also restore if we're MACOSX or not
            ptr.MACOSX = macosx

    @patch("ptr.run_tests", async_none)
    @patch("ptr._get_test_modules")
    def test_async_main(self, mock_gtm: Mock) -> None:
        args = [
            1,
            Path("/"),
            "mirror",
            1,
            "venv",
            True,
            True,
            False,
            True,
            "stats",
            30,
            True,
            False,
        ]
        mock_gtm.return_value = False
        self.assertEqual(
            self.loop.run_until_complete(ptr.async_main(*args)), 1  # pyre-ignore
        )
        mock_gtm.return_value = True
        self.assertEqual(
            self.loop.run_until_complete(ptr.async_main(*args)), 2  # pyre-ignore
        )
        # Make Path() throw a TypeError on purpose so need to ignore type error
        args[4] = 0.69  # pyre-ignore
        self.assertIsNone(
            self.loop.run_until_complete(ptr.async_main(*args))  # pyre-ignore
        )

    def test_config(self) -> None:
        expected_pypi_url = "https://pypi.org/simple/"
        dc = ptr._config_default()
        self.assertEqual(dc["ptr"]["pypi_url"], expected_pypi_url)
        dc["ptr"]["cpu_count"] = "10"

        td = Path(__file__).parent
        sc = ptr._config_read(str(td), "ptrconfig.sample")
        self.assertEqual(sc["ptr"].get("pypi_url", ""), expected_pypi_url)
        self.assertEqual(len(sc["ptr"].get("venv_pkgs", "").split()), 8)

    @patch("ptr._gen_check_output", async_none)
    @patch("ptr._set_pip_mirror")
    def test_create_venv(self, mock_pip_mirror: Mock) -> None:
        self.assertTrue(
            isinstance(
                self.loop.run_until_complete(ptr.create_venv("https://pip.com/")), Path
            )
        )

    @patch("ptr._gen_check_output", check_site_package_config)
    @patch("ptr._set_pip_mirror")
    def test_create_venv_site_packages(self, mock_pip_mirror: Mock) -> None:
        self.loop.run_until_complete(
            ptr.create_venv(
                "https://pip.com/", install_pkgs=False, system_site_packages=True
            )
        )

    def test_find_setup_py(self) -> None:
        base_path = Path(__file__).parent
        found_setup_py = ptr.find_setup_pys(base_path, set()).pop()
        self.assertEqual(str(found_setup_py.relative_to(base_path)), "setup.py")

    def test_find_setup_py_exclude_default(self) -> None:
        with TemporaryDirectory() as td:
            td_path = Path(td)
            build_path = td_path / "build-arm"
            cooper_path = td_path / "cooper"

            touch_files(*(adir / "setup.py" for adir in {build_path, cooper_path}))

            setup_pys = ptr.find_setup_pys(td_path, {"build*"})
            self.assertEqual(len(setup_pys), 1)
            self.assertEqual(
                setup_pys.pop().relative_to(td_path), Path("cooper/setup.py")
            )

    def test_generate_black_command(self) -> None:
        black_exe = Path("/bin/black")
        with TemporaryDirectory() as td:
            module_dir = Path(td)

            self.assertEqual(
                ptr._generate_black_cmd(module_dir, black_exe),
                (str(black_exe), "--check", "."),
            )

    def test_generate_install_cmd(self) -> None:
        python_exe = "python3"
        module_dir = "/tmp/awesome"
        config = {"tests_require": ["peerme"]}
        self.assertEqual(
            ptr._generate_install_cmd(python_exe, module_dir, config),
            (python_exe, "-v", "install", module_dir, "peerme"),
        )

    def test_generate_test_suite_cmd(self) -> None:
        coverage_exe = Path("/bin/coverage")
        config = {"test_suite": "dummy_test.base"}
        self.assertEqual(
            ptr._generate_test_suite_cmd(coverage_exe, config),
            (str(coverage_exe), "run", "-m", config["test_suite"]),
        )
        config = {}
        self.assertEqual(ptr._generate_test_suite_cmd(coverage_exe, config), ())

    def test_generate_mypy_cmd(self) -> None:
        with TemporaryDirectory() as td:
            td_path = Path(td)
            mypy_exe = Path("mypy")
            mypy_ini_path = td_path / "mypy.ini"
            entry_py_path = td_path / "cooper_is_awesome.py"
            touch_files(mypy_ini_path, entry_py_path)

            conf = {
                "run_mypy": True,
                "entry_point_module": entry_py_path.name.replace(".py", ""),
            }
            self.assertEqual(
                ptr._generate_mypy_cmd(td_path, mypy_exe, conf),
                (str(mypy_exe), "--config", str(mypy_ini_path), str(entry_py_path)),
            )

    def test_generate_flake8_command(self) -> None:
        flake8_exe = Path("/bin/flake8")
        with TemporaryDirectory() as td:
            module_dir = Path(td)
            cf = module_dir / ".flake8"
            touch_files(cf)

            conf = {"run_flake8": True}

            self.assertEqual(
                ptr._generate_flake8_cmd(module_dir, flake8_exe, conf),
                (str(flake8_exe), "--config", str(cf)),
            )

    def test_generate_pylint_command(self) -> None:
        pylint_exe = Path("/bin/pylint")
        with TemporaryDirectory() as td:
            module_dir = Path(td)
            subdir = module_dir / "awlib"
            cf = module_dir / ".pylint"
            py2 = subdir / "awesome2.py"
            py1 = module_dir / "awesome.py"
            touch_files(cf, py1, py2)

            conf = {"run_pylint": True}

            self.assertEqual(
                ptr._generate_pylint_cmd(module_dir, pylint_exe, conf),
                (str(pylint_exe), "--rcfile", str(cf), str(py1), str(py2)),
            )

    def test_generate_pyre_cmd(self) -> None:
        with TemporaryDirectory() as td:
            td_path = Path(td)
            pyre_exe = Path("pyre")

            conf = {"run_pyre": True}
            expected = (str(pyre_exe), "--source-directory", str(td_path), "check")
            if ptr.WINDOWS:
                expected = ()
            self.assertEqual(ptr._generate_pyre_cmd(td_path, pyre_exe, conf), expected)

    def test_get_site_packages_path_error(self) -> None:
        with TemporaryDirectory() as td:
            lib_path = Path(td) / "lib"
            lib_path.mkdir()
            self.assertIsNone(ptr._get_site_packages_path(lib_path.parent))

    @patch("ptr.print")  # noqa
    def test_get_test_modules(self, mock_print: Mock) -> None:
        base_path = Path(__file__).parent
        stats = defaultdict(int)  # type: Dict[str, int]
        test_modules = ptr._get_test_modules(base_path, stats, True, True)
        self.assertEqual(
            test_modules[base_path / "setup.py"],
            ptr_tests_fixtures.EXPECTED_TEST_PARAMS,
        )
        self.assertEqual(stats["total.non_ptr_setup_pys"], 0)
        self.assertEqual(stats["total.ptr_setup_pys"], 1)
        self.assertEqual(stats["total.setup_pys"], 1)
        # Make sure we don't run print even tho we set the option to True
        self.assertFalse(mock_print.called)

    def test_gen_output(self) -> None:
        test_cmd = ("echo.exe", "''") if ptr.WINDOWS else ("/bin/echo",)

        stdout, stderr = self.loop.run_until_complete(ptr._gen_check_output(test_cmd))
        self.assertTrue(b"\n" in stdout)
        self.assertEqual(stderr, None)

        if ptr.WINDOWS:
            return

        # TODO: Test this on Windows and ensure we capture failures corerctly
        with self.assertRaises(CalledProcessError):
            if ptr.MACOSX:
                false = "/usr/bin/false"
            else:
                false = "/bin/false"

            self.loop.run_until_complete(ptr._gen_check_output((false,)))

    def test_handle_debug(self) -> None:
        self.assertEqual(ptr._handle_debug(True), True)

    @patch("ptr.asyncio.get_event_loop", fake_get_event_loop)
    @patch("ptr.async_main", return_zero)
    @patch("ptr._validate_base_dir")
    @patch("ptr.argparse.ArgumentParser.parse_args")
    def test_main(self, mock_args: Mock, mock_validate: Mock) -> None:
        with self.assertRaises(SystemExit):
            ptr.main()

    def test_parse_setup_cfg(self) -> None:
        tmp_dir = Path(gettempdir())
        setup_cfg = tmp_dir / "setup.cfg"
        setup_py = tmp_dir / "setup.py"

        with setup_cfg.open("w") as scp:
            scp.write(ptr_tests_fixtures.SAMPLE_SETUP_CFG)

        self.assertEqual(
            ptr.parse_setup_cfg(setup_py), ptr_tests_fixtures.EXPECTED_TEST_PARAMS
        )

    @patch("ptr.print")  # noqa
    def test_print_non_configured_modules(self, mock_print: Mock) -> None:
        modules = [Path("/tmp/foo/setup.py"), Path("/tmp/bla/setup.py")]
        # TODO: Workout why pylint things this function does not exist
        ptr.print_non_configured_modules(modules)  # pylint: disable=E1101
        self.assertEqual(3, mock_print.call_count)

    @patch("ptr.print")  # noqa
    def test_print_test_results(self, mock_print: Mock) -> None:
        stats = ptr.print_test_results(ptr_tests_fixtures.EXPECTED_COVERAGE_RESULTS)
        self.assertEqual(stats["total.test_suites"], 3)
        self.assertEqual(stats["total.fails"], 1)
        self.assertEqual(stats["total.passes"], 1)
        self.assertEqual(stats["total.timeouts"], 1)

    @patch("ptr.LOG.info")  # noqa
    def test_process_reporter(self, mock_log: Mock) -> None:
        def qsize(*args: Any, **kwargs: Any) -> int:
            global TOTAL_REPORTER_TESTS
            TOTAL_REPORTER_TESTS -= 1
            return TOTAL_REPORTER_TESTS

        with patch("asyncio.Queue.qsize", qsize):
            queue: asyncio.Queue = asyncio.Queue()
            self.loop.run_until_complete(
                ptr._progress_reporter(0.1, queue, int(TOTAL_REPORTER_TESTS / 2))
            )
        self.assertEqual(mock_log.call_count, 2)

    def test_set_build_env(self) -> None:
        local_build_path = Path(gettempdir())
        build_env = ptr._set_build_env(local_build_path)
        self.assertTrue(
            str(local_build_path / "include") in build_env["C_INCLUDE_PATH"]
        )
        self.assertTrue(
            str(local_build_path / "include") in build_env["CPLUS_INCLUDE_PATH"]
        )

    def test_set_pip_mirror(self) -> None:
        with TemporaryDirectory() as td:
            fake_venv_path = Path(td)
            pip_conf_path = fake_venv_path / "pip.conf"
            ptr._set_pip_mirror(fake_venv_path)
            with pip_conf_path.open("r") as pcfp:
                conf_file = pcfp.read()
            self.assertTrue("[global]" in conf_file)
            self.assertTrue("/simple" in conf_file)

    @patch("ptr._test_steps_runner", fake_test_steps_runner)
    def test_test_runner(self) -> None:
        queue: asyncio.Queue = asyncio.Queue()
        with TemporaryDirectory() as td:
            td_path = Path(td)
            setup_py_path = td_path / "setup.py"
            with setup_py_path.open("w") as spfp:
                print(ptr_tests_fixtures.SAMPLE_SETUP_PY, file=spfp)

            queue.put_nowait(setup_py_path)
            tests_to_run = {}  # type: Dict[Path, Dict]
            tests_to_run[setup_py_path] = ptr_tests_fixtures.SAMPLE_SETUP_PY_PTR
            test_results = []  # type: List[ptr.test_result]
            stats = defaultdict(int)  # type: Dict[str, int]
            self.loop.run_until_complete(
                ptr._test_runner(
                    queue, tests_to_run, test_results, td_path, False, stats, True, 69
                )
            )
            self.assertEqual(len(test_results), 1)
            self.assertTrue("has passed all configured tests" in test_results[0].output)

    @patch("ptr._gen_check_output", return_bytes_output)
    @patch("ptr.print")
    def test_test_steps_runner(self, mock_print: Mock) -> None:
        with TemporaryDirectory() as td:
            td_path = Path(td)
            fake_setup_py = td_path / "setup.py"
            fake_venv_path = td_path / "unittest_venv"
            fake_venv_lib_path = fake_venv_path / "lib"
            fake_venv_lib_path.mkdir(parents=True)
            # Windows can not run pyre
            no_pyre = ptr.WINDOWS
            tsr_params = [
                69,  # test_start_time
                {fake_setup_py: {}},  # tests_to_run
                fake_setup_py,
                fake_venv_path,
                {},  # env
                {},  # stats
                True,  # error_on_warnings
                False,  # print_cov
            ]

            # Run everything + with print_cov
            tsr_params[1] = {fake_setup_py: ptr_tests_fixtures.EXPECTED_TEST_PARAMS}
            tsr_params[7] = True
            self.assertEqual(
                self.loop.run_until_complete(
                    ptr._test_steps_runner(*tsr_params)  # pyre-ignore
                ),
                (None, 7) if no_pyre else (None, 8),
            )

            # Test we run coverage when required_coverage does not exist
            # but we have print_cov True
            etp = deepcopy(ptr_tests_fixtures.EXPECTED_TEST_PARAMS)
            del etp["required_coverage"]
            tsr_params[1] = {fake_setup_py: etp}
            tsr_params[7] = True
            self.assertEqual(
                self.loop.run_until_complete(
                    ptr._test_steps_runner(*tsr_params)  # pyre-ignore
                ),
                (None, 7) if no_pyre else (None, 8),
            )

            # Run everything but black + no print cov
            etp = deepcopy(ptr_tests_fixtures.EXPECTED_TEST_PARAMS)
            del etp["run_black"]
            tsr_params[1] = {fake_setup_py: etp}
            tsr_params[7] = False
            self.assertEqual(
                # pyre-ignore[6]: Tests ...
                self.loop.run_until_complete(ptr._test_steps_runner(*tsr_params)),
                (None, 6) if no_pyre else (None, 7),
            )

            # Run everything but test_suite with print_cov
            expected_no_pyre_tests = (None, 6) if no_pyre else (None, 7)
            etp = deepcopy(ptr_tests_fixtures.EXPECTED_TEST_PARAMS)
            del etp["test_suite"]
            del etp["required_coverage"]
            tsr_params[1] = {fake_setup_py: etp}
            tsr_params[7] = True
            self.assertEqual(
                # pyre-ignore[6]: Tests ...
                self.loop.run_until_complete(ptr._test_steps_runner(*tsr_params)),
                expected_no_pyre_tests,
            )

            # Ensure we've "printed coverage" the 3 times we expect
            self.assertEqual(mock_print.call_count, 3)

    def test_validate_base_dir(self) -> None:
        path_str = gettempdir()
        expected_path = Path(path_str)
        self.assertEqual(ptr._validate_base_dir(path_str), expected_path)

    @patch("ptr.sys.exit")
    def test_validate_base_dir_fail(self, mock_exit: Mock) -> None:
        ptr._validate_base_dir(gettempdir() + "6969")
        mock_exit.assert_called_once()

    def test_write_stats_file(self) -> None:
        with TemporaryDirectory() as td:
            td_path = Path(td)
            jf_path = td_path / "unittest.json"
            stats = {"total": 69, "half": 35}
            ptr._write_stats_file(str(jf_path), stats)
            self.assertTrue(jf_path.exists())

    @patch("ptr.LOG.exception")
    def test_write_stats_file_raise(self, mock_log: Mock) -> None:
        ptr._write_stats_file("/root/cooper69", {})
        self.assertTrue(mock_log.called)


if __name__ == "__main__":
    unittest.main()
