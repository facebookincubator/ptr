# 🏃‍♀️ `ptr` - Python Test Runner 🏃‍♂️

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/ambv/black)
[![Build Status](https://travis-ci.com/facebookincubator/ptr.svg?token=mNAyoiwbJFtpeEWXdo5z&branch=master)](https://travis-ci.com/facebookincubator/ptr)

Python Test Runner (ptr) was born to run tests in an opinionated way, within arbitrary code repositories.
`ptr` supports many Python projects with unit tests defined in their `setup.(cfg|py)` files per repository.
`ptr` allows developers to test multiple projects/modules in one Python environment through the use of a single test virtual environment.

- `ptr` requires `>=` **python 3.6**
- `ptr` itself uses `ptr` to run its tests 👌🏼

By adding `ptr` configuration to your `setup.cfg` or `setup.py` you can have `ptr` perform the following, per test suite, in parallel:
- run your test suite
- check and enforce coverage requirements (via [coverage](https://pypi.org/project/coverage/)),
- format code (via [black](https://pypi.org/project/black/))
- perform static type analysis (via [mypy](http://mypy-lang.org/))


## Quickstart
- Install `ptr` into you virtualenv
  - `pip install ptr`
- Ensure your tests have a base file that can be executed directly
  - i.e. `python3 test.py` (possibly using `unittest.main()`)
- After adding `ptr_params` to setup.py (see example below), run:
```
cd repo
ptr
```

## How does `ptr` perform this magic? 🎩

I'm glad you ask. Under the covers `ptr` performs:
- Recursively searches for `setup.(cfg|py)` files from `BASE_DIR` (defaults to your "current working directory" (CWD))
   - [AST](https://docs.python.org/3/library/ast.html) parses out the config for each `setup.py` test requirements
   - If a `setup.cfg` exists, load via configparser and prefer if a `[ptr]` section exists
- Creates a [Python Virtual Environment](https://docs.python.org/3/tutorial/venv.html) (*OPTIONALLY* pointed at an internal PyPI mirror)
- Runs `ATONCE` tests suites in parallel (i.e. per setup.(cfg|ptr))
- All steps will be run for each suite and ONLY *FAILED* runs will have output written to stdout

## Usage 🤓

To use `ptr` all you need to do is cd to your project or set the base dir via `-b` and execute:

    $ ptr [-dk] [-b some/path] [--venv /tmp/existing_venv]

For **faster runs** when testing, it is recommended to reuse a Virtual Environment:
- `-k` - To keep the virtualenv created by `ptr`.
- Use `--venv VENV_PATH` to reuse to an existing virtualenv created by the user.

### Help Output 🙋‍♀️ 🙋‍♂️

```
usage: ptr.py [-h] [-a ATONCE] [-b BASE_DIR] [-d] [-k] [-m MIRROR]
              [--progress-interval PROGRESS_INTERVAL] [--venv VENV]
optional arguments:
  -h, --help            show this help message and exit
  -a ATONCE, --atonce ATONCE
                        How many tests to run at once [Default: 24]
  -b BASE_DIR, --base-dir BASE_DIR
                        Path to recursively look for setup.py files [Default:
                        /home/cooper/repos/l33t]
  -d, --debug           Verbose debug output
  -k, --keep-venv       Do not remove created venv
  -m MIRROR, --mirror MIRROR
                        URL for pip to use for Simple API [Default:
                        https://pypi.org/simple/]
  --progress-interval PROGRESS_INTERVAL
                        Seconds between status update on test running
                        [Default: Disabled]
  --venv VENV           Path to venv to reuse
```

## Configuration 🧰

`ptr` is configured by placing directives in one or more of the following files.  `.ptrconfig` provides
base configuration and default values for all projects in the repository, while each `setup.(cfg|py)`
overrides the base configuration for the respective packages they define.

### `.ptrconfig`

`ptr` supports a general config in `ini` ([ConfigParser](https://docs.python.org/3/library/configparser.html)) format.
A `.ptrconfig` file can be placed at the root of any repository or in any directory within your repository.
The first `.ptrconfig` file found via a recursive walk to the root ("/" in POSIX systems) will be used.

Please refer to [`ptrconfig.sample`](http://github.com/facebookincubator/ptr/blob/master/ptrconfig.sample) for the options available.

### `setup.py`

This is per project in your repository. A simple example, based on `ptr` itself:

```python
# Specific Python Test Runner (ptr) params for Unit Testing Enforcement
ptr_params = {
    # Where mypy will run to type check your program
    "entry_point_module": "ptr",
    # Base Unittest file
    "test_suite": "ptr_tests",
    "test_suite_timeout": 300,
    # Relative path from setup.py to module (e.g. ptr == ptr.py)
    "required_coverage": {"ptr.py": 99, "TOTAL": 99},
    # Run `black --check` or not
    "run_black": False,
    # Run mypy or not
    "run_mypy": True,
}
```

### `setup.cfg`

This is per project in your repository and if exists is preferred over `setup.py`.

Please refer to [`setup.cfg.sample`](http://github.com/facebookincubator/ptr/blob/master/ptrconfig.sample) for the options available + format.

### mypy Specifics

When enabled, (in `setup.(cfg|py)`) **mypy** can support using a custom `mypy.ini` for each setup.py (module) defined.

To have `ptr` run mypy using you config:
- create a `mypy.ini` in the same directory as your `setup.py`
- OR add **[mypy]** section to your `setup.cfg`

`mypy` Configuration Documentation can be found [here](https://mypy.readthedocs.io/en/stable/config_file.html)

```
[mypy]
python_version = 3.5
check_untyped_defs = True
disallow_incomplete_defs = True
disallow_untyped_decorators = True
disallow_untyped_defs = True
no_implicit_optional = True
show_error_context = True
warn_unused_ignores = True
warn_return_any = True
```

# Example Output 📝

Here are some example runs.

## Successful `ptr` Run:

Here is what you want to see in your CI logs!
```
[2019-02-06 21:51:45,442] INFO: Starting ptr.py (ptr.py:782)
[2019-02-06 21:51:59,471] INFO: Successfully created venv @ /var/folders/tc/hbwxh76j1hn6gqjd2n2sjn4j9k1glp/T/ptr_venv_24397 to run tests (14s) (ptr.py:547)
[2019-02-06 21:51:59,472] INFO: Installing /Users/cooper/repos/ptr/setup.py + deps (ptr.py:417)
[2019-02-06 21:52:00,726] INFO: Running /Users/cooper/repos/ptr/ptr_tests.py tests via coverage (ptr.py:417)
[2019-02-06 21:52:04,153] INFO: Analyzing coverage report for /Users/cooper/repos/ptr/setup.py (ptr.py:417)
[2019-02-06 21:52:04,368] INFO: Running mypy for /Users/cooper/repos/ptr/setup.py (ptr.py:417)
[2019-02-06 21:52:07,733] INFO: /Users/cooper/repos/ptr/setup.py has passed all configured tests (ptr.py:509)
-- Summary (total time 22s):

✅ PASS: 1
❌ FAIL: 0
⌛️ TIMEOUT: 0
💩 TOTAL: 1

-- 1 / 1 (100%) `setup.py`'s have `ptr` tests running
```
## Unsuccessful `ptr` Run Examples:

Here are some examples of runs failing. Any "step" can fail. All output is predominately the underlying tool.

### Unit Test Failure

```
[2019-02-06 21:53:58,121] INFO: Starting ptr.py (ptr.py:782)
[2019-02-06 21:53:58,143] INFO: Installing /Users/cooper/repos/ptr/setup.py + deps (ptr.py:417)
[2019-02-06 21:53:59,698] INFO: Running /Users/cooper/repos/ptr/ptr_tests.py tests via coverage (ptr.py:417)
-- Summary (total time 5s):

✅ PASS: 0
❌ FAIL: 1
⌛️ TIMEOUT: 0
💩 TOTAL: 1

-- 1 / 1 (100%) `setup.py`'s have `ptr` tests running

-- Failure Output --

/Users/cooper/repos/ptr/setup.py:
...F....................
======================================================================
FAIL: test_config (__main__.TestPtr)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/Users/cooper/repos/ptr/ptr_tests.py", line 125, in test_config
    self.assertEqual(len(sc["ptr"]["venv_pkgs"].split()), 4)
AssertionError: 5 != 4

----------------------------------------------------------------------
Ran 24 tests in 3.221s

FAILED (failures=1)
```

### Coverage Failure

```
[2019-02-06 21:55:42,947] INFO: Starting ptr.py (ptr.py:782)
[2019-02-06 21:55:42,969] INFO: Installing /Users/cooper/repos/ptr/setup.py + deps (ptr.py:417)
[2019-02-06 21:55:44,920] INFO: Running /Users/cooper/repos/ptr/ptr_tests.py tests via coverage (ptr.py:417)
[2019-02-06 21:55:49,628] INFO: Analyzing coverage report for /Users/cooper/repos/ptr/setup.py (ptr.py:417)
-- Summary (total time 7s):

✅ PASS: 0
❌ FAIL: 1
⌛️ TIMEOUT: 0
💩 TOTAL: 1

-- 1 / 1 (100%) `setup.py`'s have `ptr` tests running

-- Failure Output --

/Users/cooper/repos/ptr/setup.py:
The following files did not meet coverage requirements:
  ptr.py: 84 < 99 - Missing: 146-147, 175, 209, 245, 269, 288-291, 334-336, 414-415, 425-446, 466, 497, 506, 541-543, 562, 611-614, 639-688
```

### black

```
[2019-02-06 22:34:20,029] INFO: Starting ptr.py (ptr.py:804)
[2019-02-06 22:34:20,060] INFO: Installing /Users/cooper/repos/ptr/setup.py + deps (ptr.py:430)
[2019-02-06 22:34:21,614] INFO: Running /Users/cooper/repos/ptr/ptr_tests.py tests via coverage (ptr.py:430)
[2019-02-06 22:34:25,208] INFO: Analyzing coverage report for /Users/cooper/repos/ptr/setup.py (ptr.py:430)
[2019-02-06 22:34:25,450] INFO: Running mypy for /Users/cooper/repos/ptr/setup.py (ptr.py:430)
[2019-02-06 22:34:26,422] INFO: Running black for /Users/cooper/repos/ptr/setup.py (ptr.py:430)
-- Summary (total time 7s):

✅ PASS: 0
❌ FAIL: 1
⌛️ TIMEOUT: 0
💩 TOTAL: 1

-- 1 / 1 (100%) `setup.py`'s have `ptr` tests running

-- Failure Output --

/Users/cooper/repos/ptr/setup.py:
would reformat /Users/cooper/repos/ptr/ptr.py
All done! 💥 💔 💥
1 file would be reformatted, 4 files would be left unchanged.
```

### mypy

```
[2019-02-06 22:35:39,480] INFO: Starting ptr.py (ptr.py:802)
[2019-02-06 22:35:39,531] INFO: Installing /Users/cooper/repos/ptr/setup.py + deps (ptr.py:428)
[2019-02-06 22:35:41,203] INFO: Running /Users/cooper/repos/ptr/ptr_tests.py tests via coverage (ptr.py:428)
[2019-02-06 22:35:45,156] INFO: Analyzing coverage report for /Users/cooper/repos/ptr/setup.py (ptr.py:428)
[2019-02-06 22:35:45,413] INFO: Running mypy for /Users/cooper/repos/ptr/setup.py (ptr.py:428)
-- Summary (total time 6s):

✅ PASS: 0
❌ FAIL: 1
⌛️ TIMEOUT: 0
💩 TOTAL: 1

-- 1 / 1 (100%) `setup.py`'s have `ptr` tests running

-- Failure Output --

/Users/cooper/repos/ptr/setup.py:
/Users/cooper/repos/ptr/ptr.py: note: In function "_write_stats_file":
/Users/cooper/repos/ptr/ptr.py:179: error: Argument 1 to "open" has incompatible type "Path"; expected "Union[str, bytes, int]"
/Users/cooper/repos/ptr/ptr.py: note: In function "run_tests":
/Users/cooper/repos/ptr/ptr.py:700: error: Argument 1 to "_write_stats_file" has incompatible type "str"; expected "Path"
```

# FAQ ⁉️

### Q. How do I debug? I need output!

- `ptr` developers recommend that if you want output, please cause a test to fail
  - e.g. `raise ZeroDivisionError`
- Another recommended way is to run your tests with the default `setup.py test` using a `ptr` created venv:
  - `cd to/my/code`
  - `/tmp/venv/bin/python setup.py test`

### Q. How do I get specific version of black, coverage, mypy etc.?

- Just simply hard set the version in the .ptrconfig in your repo
- All `pip` [PEP 440 version specifiers](https://www.python.org/dev/peps/pep-0440/) are supported

### Q. Why is the venv creation so slow?

- `ptr` attempts to update from a PyPI compatible mirror (PEP 381) or PyPI itself
- Running a package cache or local mirror can greatly increase speed. Example software to do this:
  - [bandersnatch](https://pypi.org/project/bandersnatch): Can do selected or FULL PyPI mirrors. The maintainer is also devilishly good looking.
  - [devpi](https://pypi.org/project/devpi/): Can be ran and used to *proxy* packages locally when pip goes out to grab your dependencies.
- Please ensure you're using the `-k` or `--venv` option to no recreate a virtualenv each run when debugging your tests!

# Contact or join the ptr community 💬

To chat in real time, hit us up on IRC. Otherwise, GitHub issues are always welcome!
IRC: `#pythontestrunner` on *FreeNode*

See the [CONTRIBUTING](CONTRIBUTING.md) file for how to help out.

## License
`ptr` is MIT licensed, as found in the LICENSE file.
