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
import sys
from os import environ
from pathlib import Path
from subprocess import PIPE, run
from tempfile import gettempdir


def check_ptr_stats_json(stats_file: Path) -> int:
    stats_errors = 0

    if not stats_file.exists():
        print("{} stats file does not exist".format(stats_file))
        return 68

    try:
        with stats_file.open("r") as sfp:
            stats_json = json.load(sfp)
    except json.JSONDecodeError as jde:
        print("Stats JSON Error: {}".format(jde))
        return 69

    # Lets always print JSON to help debug any failures and have JSON history
    print(json.dumps(stats_json, indent=2, sort_keys=True))

    any_fail = int(stats_json["total.fails"]) + int(stats_json["total.timeouts"])
    if any_fail:
        print("Stats report {} fails/timeouts".format(any_fail), file=sys.stderr)
        return any_fail

    if int(stats_json["total.setup_pys"]) > 1:
        print("Somehow we had more than 1 setup.py - What?", file=sys.stderr)
        stats_errors += 1

    if int(stats_json["pct.setup_py_ptr_enabled"]) != 100:
        print("We didn't test all setup.py files ...", file=sys.stderr)
        stats_errors += 1

    # TODO: Make getting project name better - For now quick CI hack
    coverage_key_count = 0
    for key in stats_json.keys():
        if "_coverage." in key:
            coverage_key_count += 1
    if coverage_key_count != 4:
        print("We didn't get coverage stats for all ptr files + total", file=sys.stderr)
        stats_errors += 1

    print("Stats check found {} error(s)".format(stats_errors))

    return stats_errors


def integration_test() -> int:
    # TODO: Plumb up to a coverage system - e.g. codecov (Issue #6)
    print("Running `ptr` integration tests (aka run itself)", file=sys.stderr)

    stats_file = Path(gettempdir()) / "ptr_ci_stats"
    ci_cmd = [
        "python",
        "ptr.py",
        "-d",
        "--print-cov",
        "--run-disabled",
        "--error-on-warnings",
        "--stats-file",
        str(stats_file),
    ]
    if "VIRTUAL_ENV" in environ:
        ci_cmd.extend(["--venv", environ["VIRTUAL_ENV"]])

    cp = run(ci_cmd, check=True)
    return cp.returncode + check_ptr_stats_json(stats_file)


def ci(show_env: bool = False) -> int:
    # Output exact python version
    cp = run(("python", "-V"), check=True, stdout=PIPE, universal_newlines=True)
    print("Using {}".format(cp.stdout), file=sys.stderr)

    if show_env:
        print("- Environment:", file=sys.stderr)
        for key in sorted(environ.keys()):
            print("{}: {}".format(key, environ[key]), file=sys.stderr)

    # Azure sets CI_ENV=PTR_INTEGRATION
    # Travis sets PTR_INTEGRATION=1
    if "PTR_INTEGRATION" in environ or (
        "CI_ENV" in environ and environ["CI_ENV"] == "PTR_INTEGRATION"
    ):
        return integration_test()

    print("Running `ptr` unit tests", file=sys.stderr)
    return run(("python", "setup.py", "test"), check=True).returncode


if __name__ == "__main__":
    sys.exit(ci())
