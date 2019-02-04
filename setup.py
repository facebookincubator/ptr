#!/usr/bin/env python3
# Copyright (c) 2014-present, Facebook, Inc.

from setuptools import setup


# Specific Python Test Runner (ptr) params for Unit Testing Enforcement
ptr_params = {
    # Where mypy will run to type check your program
    "entry_point_module": "ptr",
    # Base Unittest File
    "test_suite": "ptr_tests",
    "test_suite_timeout": 120,
    # Relative path from setup.py to module (e.g. ptr == ptr.py)
    "required_coverage": {"ptr.py": 84, "TOTAL": 90},
    # Run mypy or not
    "run_mypy": True,
}


setup(
    name="ptr",
    version="19.1.1",
    description="Parallel asyncio Python setup.py Test Runner",
    py_modules=["ptr", "ptr_tests", "ptr_tests_fixtures"],
    url="http://github.com/facebook/terragraph",
    author="Cooper Lees",
    author_email="cooper@fb.com",
    classifiers=(
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Development Status :: 3 - Alpha",
    ),
    python_requires=">=3.5",
    install_requires=None,
    entry_points={"console_scripts": ["ptr = ptr:main"]},
    test_suite=ptr_params["test_suite"],
)
