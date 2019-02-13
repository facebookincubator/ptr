#!/usr/bin/env python3
# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
# coding=utf8

"""
ptr CI run script - Will either run unittests via 'python setup.py test'
OR run ptr itself to enfore coverage, black, and mypy type results 🐓🥚
"""

import json
from os import environ
from pathlib import Path
from subprocess import PIPE, run
from sys import exit, stderr
from tempfile import gettempdir


def check_ptr_stats_json(stats_file: Path) -> int:
    stats_errors = 0
    try:
        with stats_file.open("r") as sfp:
            stats_json = json.load(sfp)
    except json.JSONDecodeError as jde:
        print("Stats JSON Error: {}".format(jde))
        return 69

    any_fail = int(stats_json["total.fails"]) + int(stats_json["total.timeouts"])
    if any_fail:
        print("Stats report {} fails/timeouts".format(any_fail), file=stderr)
        return any_fail

    if int(stats_json["total.setup_pys"]) > 1:
        print("Somehow we had more than 1 setup.py - What?", file=stderr)
        stats_errors += 1

    if int(stats_json["pct.setup_py_ptr_enabled"]) != 100:
        print("We didn't test all setup.py files ...", file=stderr)
        stats_errors += 1

    if "suite.ptr_coverage.file.ptr.py" not in stats_json:
        print("We didn't get any coverage stats for ptr.py", file=stderr)
        stats_errors += 1

    print("Stats check found {} errors".format(stats_errors))
    return stats_errors


def integration_test() -> int:
    # TODO: Plumb up to a coverage system - e.g. codecov (Issue #6)
    print("Running `ptr` integration tests (aka run itself)", file=stderr)

    stats_file = Path(gettempdir()) / "ptr_ci_stats"
    cp = run(
        (
            "python",
            "ptr.py",
            "-d",
            "--print-cov",
            "--stats-file",
            str(stats_file),
            "--venv",
            environ["VIRTUAL_ENV"],
        )
    )
    return cp.returncode + check_ptr_stats_json(stats_file)


def ci() -> int:
    # Output exact python version
    cp = run(("python", "-V"), stdout=PIPE, universal_newlines=True)
    print("Using {}".format(cp.stdout), file=stderr)

    if "PTR_INTEGRATION" in environ:
        return integration_test()

    print("Running `ptr` unit tests", file=stderr)
    return run(("python", "setup.py", "test")).returncode


if __name__ == "__main__":
    exit(ci())
