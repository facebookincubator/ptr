#!/usr/bin/env python3
# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from pathlib import Path
from setuptools import setup


# Specific Python Test Runner (ptr) params for Unit Testing Enforcement
ptr_params = {
    # Where mypy will run to type check your program
    "entry_point_module": "ptr",
    # Base Unittest File
    "test_suite": "ptr_tests",
    "test_suite_timeout": 120,
    # Relative path from setup.py to module (e.g. ptr == ptr.py)
    "required_coverage": {"ptr.py": 85, "TOTAL": 91},
    # Run black or not
    "run_black": True,
    # Run mypy or not
    "run_mypy": True,
}


def get_long_desc() -> str:
    repo_base = Path(__file__).parent
    long_desc = ""
    for info_file in (repo_base / "README.md", repo_base / "CHANGES.md"):
        with info_file.open("r") as ifp:
            long_desc += ifp.read()
        long_desc += "\n\n"

    return long_desc


setup(
    name="ptr",
    version="19.2.8.post2",
    description="Parallel asyncio Python setup.(cfg|py) Test Runner",
    long_description=get_long_desc(),
    long_description_content_type="text/markdown",
    py_modules=["ptr", "ptr_tests", "ptr_tests_fixtures"],
    url="http://github.com/facebookincubator/ptr",
    author="Cooper Lees",
    author_email="me@cooperlees.com",
    license="MIT",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
    ],
    python_requires=">=3.6",
    install_requires=None,
    entry_points={"console_scripts": ["ptr = ptr:main"]},
    test_suite=ptr_params["test_suite"],
)
