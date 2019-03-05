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
from sys import version_info
from tempfile import TemporaryDirectory, gettempdir
from typing import (  # noqa: F401 # pylint: disable=unused-import
    Any,
    Dict,
    List,
    Optional,
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
    return


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


def touch_files(*paths: Path) -> None:
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)


class TestPtr(unittest.TestCase):
    maxDiff = 2000

    def setUp(self) -> None:
        self.loop = asyncio.get_event_loop()

    @patch("ptr._get_site_packages_path")  # noqa
    def test_analyze_coverage_errors(self, mock_path: Mock) -> None:
        mock_path.return_value = None
        fake_path = Path(gettempdir())
        self.assertIsNone(ptr._analyze_coverage(fake_path, fake_path, {}, "", {}))
        mock_path.return_value = fake_path
        self.assertIsNone(
            ptr._analyze_coverage(fake_path, fake_path, {}, "Fake Cov Report", {})
        )

    @patch("ptr.getpid", return_specific_pid)  # noqa
    def test_analyze_coverage(self) -> None:
        fake_setup_py = Path("unittest/setup.py")
        if "VIRTUAL_ENV" in environ:
            fake_venv_path = Path(environ["VIRTUAL_ENV"])
        else:
            fake_venv_path = self.loop.run_until_complete(
                ptr.create_venv("https://pypi.com/s", install_pkgs=False)
            )
        self.assertIsNone(
            ptr._analyze_coverage(fake_venv_path, fake_setup_py, {}, "", {})
        )
        self.assertIsNone(
            ptr._analyze_coverage(fake_venv_path, fake_setup_py, {"bla": 69}, "", {})
        )

        # Test with simple py_modules
        self.assertEqual(
            ptr._analyze_coverage(
                fake_venv_path,
                fake_setup_py,
                ptr_tests_fixtures.FAKE_REQ_COVERAGE,
                ptr_tests_fixtures.SAMPLE_REPORT_OUTPUT,
                {},
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
            ),
            ptr_tests_fixtures.EXPECTED_PTR_COVERAGE_FAIL_RESULT,
        )

        # Dont delete the VIRTUAL_ENV carrying the test if we didn't make it
        if "VIRTUAL_ENV" not in environ:
            rmtree(fake_venv_path)

    @patch("ptr.run_tests", async_none)
    @patch("ptr._get_test_modules")
    def test_async_main(self, mock_gtm: Mock) -> None:
        args = [1, Path("/"), "mirror", 1, "venv", True, True, False, "stats", 30]
        mock_gtm.return_value = False
        self.assertEqual(self.loop.run_until_complete(ptr.async_main(*args)), 1)
        mock_gtm.return_value = True
        self.assertEqual(self.loop.run_until_complete(ptr.async_main(*args)), 2)
        # Make Path() throw a TypeError
        args[4] = 0.69
        self.assertIsNone(self.loop.run_until_complete(ptr.async_main(*args)))

    def test_config(self) -> None:
        expected_pypi_url = "https://pypi.org/simple/"
        dc = ptr._config_default()
        self.assertEqual(dc["ptr"]["pypi_url"], expected_pypi_url)
        dc["ptr"]["cpu_count"] = "10"

        td = Path(__file__).parent
        sc = ptr._config_read(str(td), "ptrconfig.sample")
        self.assertEqual(sc["ptr"]["pypi_url"], expected_pypi_url)
        self.assertEqual(len(sc["ptr"]["venv_pkgs"].split()), 7)

    @patch("ptr._gen_check_output", async_none)  # noqa
    @patch("ptr._set_pip_mirror")  # noqa
    def test_create_venv(self, mock_pip_mirror: Mock) -> None:
        self.assertTrue(
            isinstance(
                self.loop.run_until_complete(ptr.create_venv("https://pip.com/")), Path
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
            subdir = module_dir / "awlib"
            py2 = subdir / "awesome2.py"
            py1 = module_dir / "awesome.py"
            touch_files(py1, py2)

            self.assertEqual(
                ptr._generate_black_cmd(module_dir, black_exe),
                (str(black_exe), "--check", str(py1), str(py2)),
            )

    def test_generate_install_cmd(self) -> None:
        python_exe = "python3"
        module_dir = "/tmp/awesome"
        config = {"tests_require": ["peerme"]}
        self.assertEqual(
            ptr._generate_install_cmd(python_exe, module_dir, config),
            (python_exe, "-v", "install", module_dir, "peerme"),
        )

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
            subdir = module_dir / "awlib"
            cf = module_dir / ".flake8"
            py2 = subdir / "awesome2.py"
            py1 = module_dir / "awesome.py"
            touch_files(cf, py1, py2)

            conf = {"run_flake8": True}

            self.assertEqual(
                ptr._generate_flake8_cmd(module_dir, flake8_exe, conf),
                (str(flake8_exe), "--config", str(cf), str(py1), str(py2)),
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

    def test_get_site_packages_path_error(self) -> None:
        with TemporaryDirectory() as td:
            lib_path = Path(td) / "lib"
            lib_path.mkdir()
            self.assertIsNone(ptr._get_site_packages_path(lib_path.parent))

    def test_get_test_modules(self) -> None:
        base_path = Path(__file__).parent
        stats = defaultdict(int)  # type: Dict[str, int]
        test_modules = ptr._get_test_modules(base_path, stats)
        self.assertEqual(
            test_modules[base_path / "setup.py"],
            ptr_tests_fixtures.EXPECTED_TEST_PARAMS,
        )
        self.assertEqual(stats["total.setup_pys"], 1)
        self.assertEqual(stats["total.ptr_setup_pys"], 1)

    def test_gen_output(self) -> None:
        test_cmd = ("echo.exe", "''") if ptr.WINDOWS else ("/bin/echo",)

        stdout, stderr = self.loop.run_until_complete(ptr._gen_check_output(test_cmd))
        self.assertTrue(b"\n" in stdout)
        self.assertEqual(stderr, None)

        if ptr.WINDOWS:
            return

        # TODO: Test this on Windows and ensure we capture failures corerctly
        with self.assertRaises(CalledProcessError):
            if ptr.MAC:
                false = "/usr/bin/false"
            else:
                false = "/bin/false"

            self.loop.run_until_complete(ptr._gen_check_output((false,)))

    def test_handle_debug(self) -> None:
        self.assertEqual(ptr._handle_debug(True), True)

    @patch("ptr.asyncio.get_event_loop", fake_get_event_loop)
    @patch("ptr.async_main")
    @patch("ptr._validate_base_dir")
    @patch("ptr.argparse.ArgumentParser.parse_args")
    def test_main(
        self, mock_args: Mock, mock_validate: Mock, mock_async_main: Mock
    ) -> None:
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

        queue = asyncio.Queue()  # type: asyncio.Queue
        queue.qsize = qsize  # noqa

        self.loop.run_until_complete(
            ptr._progress_reporter(0.1, queue, TOTAL_REPORTER_TESTS / 2)
        )
        self.assertEqual(mock_log.call_count, 2)

    def test_run_black(self) -> None:
        config = {}  # type: Dict[str, Any]
        self.assertFalse(ptr._run_black(config, False))
        self.assertFalse(ptr._run_black(config, True))
        config["run_black"] = True
        if ptr.WINDOWS and version_info >= (3, 7):
            # Ensure even if in config we don't run it
            self.assertFalse(ptr._run_black(config, False))
        else:
            self.assertTrue(ptr._run_black(config, False))

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
        queue = asyncio.Queue()  # type: asyncio.Queue
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
                    queue, tests_to_run, test_results, td_path, False, False, stats, 69
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

            # Run everything but black
            etp = deepcopy(ptr_tests_fixtures.EXPECTED_TEST_PARAMS)
            del etp["run_black"]
            fake_no_black_tests_to_run = {fake_setup_py: etp}
            self.assertEqual(
                self.loop.run_until_complete(
                    ptr._test_steps_runner(
                        69,
                        fake_no_black_tests_to_run,
                        fake_setup_py,
                        fake_venv_path,
                        {},
                        True,
                    )
                ),
                (None, 6),
            )

            # Run everything including black except on Windows + Python 3.7
            expected = (
                (None, 6) if ptr.WINDOWS and version_info >= (3, 7) else (None, 7)
            )
            fake_tests_to_run = {fake_setup_py: ptr_tests_fixtures.EXPECTED_TEST_PARAMS}
            self.assertEqual(
                self.loop.run_until_complete(
                    ptr._test_steps_runner(
                        69,
                        fake_tests_to_run,
                        fake_setup_py,
                        fake_venv_path,
                        {},
                        {},
                        True,
                    )
                ),
                expected,
            )
            # Ensure we've "printed coverage"
            self.assertTrue(mock_print.called)

    def test_validate_base_dir(self) -> None:
        path_str = gettempdir()
        expected_path = Path(path_str)
        self.assertEqual(ptr._validate_base_dir(path_str), expected_path)

    @patch("ptr.sys.exit")  # noqa
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
