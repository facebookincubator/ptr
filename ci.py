#!/usr/bin/env python3
# coding=utf8

"""
ptr CI run script - Will either run unittests via 'python setup.py test'
OR run ptr itself to enfore coverage, black, and mypy type results 🐓🥚
"""

from os import environ
from subprocess import PIPE, run
from sys import exit, stderr


def integration_test() -> int:
    # TODO: Check stats file for expectations (Issue #7)
    # TODO: Plumb up to a coverage system - e.g. codecov (Issue #6)
    print("Running `ptr` integration tests (aka run itself)", file=stderr)
    return run(
        ("python", "ptr.py", "-d", "--print-cov", "--venv", environ["VIRTUAL_ENV"])
    ).returncode


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
