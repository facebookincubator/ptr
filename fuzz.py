#!/usr/bin/env python3
# Copyright © Meta Platforms, Inc. and affiliates

# This test code was written by the `hypothesis.extra.ghostwriter` module
# and is provided under the Creative Commons Zero public domain dedication.
# Has since bee hacked then by humans

import asyncio
import typing
import unittest
from collections import defaultdict
from pathlib import Path
from tempfile import gettempdir
from unittest.mock import MagicMock, patch

import ptr

# pyre-fixme[21]: Import not found
from hypothesis import given, strategies as st


# Suppress logging
ptr.LOG = MagicMock()


class TestNamedTuples(unittest.TestCase):
    @given(stmts=st.floats(), miss=st.floats(), cover=st.floats(), missing=st.text())
    def test_fuzz_coverage_line(self, stmts, miss, cover, missing):
        ptr.coverage_line(stmts=stmts, miss=miss, cover=cover, missing=missing)

    @given(py_files=st.sets(st.text()), base_dir=st.builds(Path))
    def test_fuzz_find_py_files(self, py_files, base_dir):
        ptr.find_py_files(py_files=py_files, base_dir=base_dir)

    @given(
        step_name=st.sampled_from(ptr.StepName),
        run_condition=st.booleans(),
        cmds=st.lists(st.text()).map(tuple),
        log_message=st.text(),
        timeout=st.floats(),
    )
    def test_fuzz_step(self, step_name, run_condition, cmds, log_message, timeout):
        ptr.step(
            step_name=step_name,
            run_condition=run_condition,
            cmds=cmds,
            log_message=log_message,
            timeout=timeout,
        )

    @given(
        setup_py_path=st.builds(Path),
        returncode=st.integers(),
        output=st.text(),
        runtime=st.floats(),
        timeout=st.booleans(),
    )
    def test_fuzz_test_result(
        self, setup_py_path, returncode, output, runtime, timeout
    ):
        ptr.test_result(
            setup_py_path=setup_py_path,
            returncode=returncode,
            output=output,
            runtime=runtime,
            timeout=timeout,
        )


class TestPtrUtilities(unittest.TestCase):
    @given(
        base_path=st.builds(Path),
        exclude_patterns=st.sets(st.text()),
        follow_symlinks=st.booleans(),
    )
    def test_fuzz_find_setup_pys(self, base_path, exclude_patterns, follow_symlinks):
        ptr.find_setup_pys(
            base_path=base_path,
            exclude_patterns=exclude_patterns,
            follow_symlinks=follow_symlinks,
        )

    @given(setup_py=st.builds(Path))
    def test_fuzz_parse_setup_cfg(self, setup_py):
        ptr.parse_setup_cfg(setup_py=setup_py)

    @given(modules=st.lists(st.builds(Path)))
    @patch("builtins.print")
    def test_fuzz_print_non_configured_modules(self, mock_print, modules):
        ptr.print_non_configured_modules(modules=modules)
        self.assertTrue(mock_print.called)


class TestPtrRunners(unittest.TestCase):
    @given(
        atonce=st.integers(min_value=1, max_value=64),
        base_path=st.builds(Path),
        mirror=st.text(),
        progress_interval=st.floats(),
        venv=st.text(),
        venv_keep=st.booleans(),
        print_cov=st.booleans(),
        print_non_configured=st.booleans(),
        run_disabled=st.booleans(),
        stats_file=st.text(),
        venv_timeout=st.floats(),
        error_on_warnings=st.booleans(),
        system_site_packages=st.booleans(),
    )
    def test_fuzz_async_main(
        self,
        atonce,
        base_path,
        mirror,
        progress_interval,
        venv,
        venv_keep,
        print_cov,
        print_non_configured,
        run_disabled,
        stats_file,
        venv_timeout,
        error_on_warnings,
        system_site_packages,
    ):
        with patch("builtins.print"), patch("ptr.run_tests"):
            asyncio.run(
                ptr.async_main(
                    atonce=atonce,
                    base_path=base_path,
                    mirror=mirror,
                    progress_interval=progress_interval,
                    venv=venv,
                    venv_keep=venv_keep,
                    print_cov=print_cov,
                    print_non_configured=print_non_configured,
                    run_disabled=run_disabled,
                    stats_file=stats_file,
                    venv_timeout=venv_timeout,
                    error_on_warnings=error_on_warnings,
                    system_site_packages=system_site_packages,
                )
            )

    @given(
        mirror=st.text(),
        py_exe=st.text(),
        install_pkgs=st.booleans(),
        timeout=st.floats(),
        system_site_packages=st.booleans(),
    )
    def test_fuzz_create_venv(
        self, mirror, py_exe, install_pkgs, timeout, system_site_packages
    ):
        with patch("ptr._gen_check_output"):
            asyncio.run(
                ptr.create_venv(
                    mirror=mirror,
                    py_exe=py_exe,
                    install_pkgs=install_pkgs,
                    timeout=timeout,
                    system_site_packages=system_site_packages,
                )
            )

    @given(
        atonce=st.integers(min_value=1, max_value=64),
        mirror=st.text(),
        tests_to_run=st.from_type(typing.Dict[Path, typing.Dict]),
        progress_interval=st.one_of(st.floats(), st.integers()),
        venv_path=st.one_of(st.none(), st.builds(Path)),
        venv_keep=st.booleans(),
        print_cov=st.booleans(),
        stats=st.dictionaries(keys=st.text(), values=st.integers(min_value=0)).map(
            lambda x: defaultdict(int, x)
        ),
        stats_file=st.text(),
        venv_timeout=st.floats(),
        error_on_warnings=st.booleans(),
        system_site_packages=st.booleans(),
    )
    def test_fuzz_run_tests(
        self,
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
        system_site_packages,
    ):
        created_venv_path = Path(gettempdir()) / "ptr_venv"
        test_results = (0, 69)
        with patch("builtins.print"), patch(
            "ptr._test_steps_runner", return_value=test_results
        ), patch("ptr.chdir"), patch(
            "ptr.create_venv",
            return_value=created_venv_path,
        ), patch(
            "ptr._write_stats_file"
        ), patch(
            "ptr.rmtree"
        ):
            asyncio.run(
                ptr.run_tests(
                    atonce=atonce,
                    mirror=mirror,
                    tests_to_run=tests_to_run,
                    progress_interval=progress_interval,
                    venv_path=venv_path,
                    venv_keep=venv_keep,
                    print_cov=print_cov,
                    stats=stats,
                    stats_file=stats_file,
                    venv_timeout=venv_timeout,
                    error_on_warnings=error_on_warnings,
                    system_site_packages=system_site_packages,
                )
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
