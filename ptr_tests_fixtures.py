#!/usr/bin/env python3
# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
# coding=utf8
# flake8: noqa

from os import environ
from os.path import sep
from pathlib import Path
from sys import version_info
from tempfile import gettempdir

from ptr import test_result


class FakeEventLoop:
    def close(self, *args, **kwargs) -> None:
        pass

    def run_until_complete(self, *args, **kwargs) -> int:
        return 0


# Disabled is set as we --run-disabled the run in CI
EXPECTED_TEST_PARAMS = {
    "disabled": True,
    "entry_point_module": "ptr",
    "test_suite": "ptr_tests",
    "test_suite_timeout": 120,
    "required_coverage": {"ptr.py": 85, "TOTAL": 90},
    "run_black": True,
    "run_mypy": True,
    "run_flake8": True,
    "run_pylint": True,
    "run_pyre": True,
}

EXPECTED_COVERAGE_FAIL_RESULT = test_result(
    setup_py_path=Path("unittest/setup.py"),
    returncode=3,
    output=(
        "The following files did not meet coverage requirements:\n"
        + "  unittest{}ptr.py: 69 < 99 - Missing: 70-72, 76-94, 98\n".format(sep)
    ),
    runtime=0,
    timeout=False,
)
EXPECTED_PTR_COVERAGE_FAIL_RESULT = test_result(
    setup_py_path=Path("unittest/setup.py"),
    returncode=3,
    output=(
        "The following files did not meet coverage requirements:\n  tg{}tg.py: ".format(
            sep
        )
        + "22 < 99 - Missing: 39-59, 62-73, 121, 145-149, 153-225, 231-234, 238\n  "
        + "TOTAL: 40 < 99 - Missing: \n"
    ),
    runtime=0,
    timeout=False,
)
EXPECTED_PTR_COVERAGE_MISSING_FILE_RESULT = test_result(
    setup_py_path=Path("unittest/setup.py"),
    returncode=3,
    output=(
        "fake_file.py has not reported any coverage. Does the file exist? "
        + "Does it get ran during tests? Remove from setup config."
    ),
    runtime=0,
    timeout=False,
)

EXPECTED_COVERAGE_RESULTS = [
    test_result(
        setup_py_path=Path("project69/setup.py"),
        returncode=0,
        output="Killed it",
        runtime=4,
        timeout=False,
    ),
    test_result(
        setup_py_path=Path("project1/setup.py"),
        returncode=2,
        output="Timeout during Running project1/tests.py tests via coverage",
        runtime=1,
        timeout=True,
    ),
    test_result(
        setup_py_path=Path("project2/setup.py"),
        returncode=1,
        output="..F..\nShit Failed yo!",
        runtime=2,
        timeout=False,
    ),
]

FAKE_REQ_COVERAGE = {str(Path("unittest/ptr.py")): 99, "TOTAL": 99}
FAKE_TG_REQ_COVERAGE = {str(Path("tg/tg.py")): 99, "TOTAL": 99}


SAMPLE_REPORT_OUTPUT = """\
Name                                Stmts   Miss  Cover   Missing
------------------------------------------------------------------
unittest{sep}ptr.py                     59     14     69%     70-72, 76-94, 98
unittest{sep}ptr_tests.py               24      0     100%
unittest{sep}ptr_venv_fixtures.py        1      0     100%
------------------------------------------------------------------
TOTAL                                84     14    99%
""".format(
    sep=sep
)

HARD_SET_VENV = Path("{}/ptr_venv_2580217".format(gettempdir()))
BASE_VENV_PATH = (
    Path(environ["VIRTUAL_ENV"]) if "VIRTUAL_ENV" in environ else HARD_SET_VENV
)
SAMPLE_NIX_TG_REPORT_OUTPUT = """\
Name                                                                         Stmts   Miss  Cover   Missing
----------------------------------------------------------------------------------------------------------
{base_venv_path}/lib/python{major}.{minor}/site-packages/click/__init__.py             13      0   100%
{base_venv_path}/lib/python{major}.{minor}/site-packages/click/_compat.py             433    320    26%   22, 27-31, 41-42, 47-50, 57-59, 65-76, 79-82, 86, 100-102, 105, 108-116, 119-128, 131-143, 146-153, 157-260, 275-278, 289-292, 299-307, 314-322, 333-345, 349-374, 380, 387-404, 408-412, 415-419, 422-426, 429-432, 438, 443-446, 450-455, 459-468, 475-516, 524-525, 531-534, 538, 541-550, 553, 556, 559, 562, 575-579, 587-645, 648, 659-662, 671-672, 674, 679-680
{base_venv_path}/lib/python{major}.{minor}/site-packages/click/_textwrap.py            30     16    47%   8-17, 32-38
{base_venv_path}/lib/python{major}.{minor}/site-packages/click/_unicodefun.py          71     54    24%   16-29, 34, 37-41, 53, 57-58, 62-120
{base_venv_path}/lib/python{major}.{minor}/site-packages/click/core.py                877    389    56%   35-36, 43-45, 56-58, 62-70, 81, 90-95, 107-111, 113-115, 237, 246, 262, 267, 302, 310, 328-331, 335, 351, 418, 434-435, 439-441, 453, 458-461, 465-469, 475-478, 484-488, 496, 500, 510, 534-555, 562-573, 616, 619, 637-638, 642, 649, 656, 698, 701, 706, 717-727, 729-730, 732-735, 737-742, 755-760, 764, 809, 819-821, 856, 884, 908, 910-913, 930-932, 942-948, 954-956, 995, 1005-1007, 1049-1053, 1062-1069, 1073-1082, 1086-1087, 1090-1096, 1099-1164, 1167-1190, 1196, 1202, 1221-1225, 1233-1237, 1245-1249, 1252, 1266-1268, 1272, 1275-1280, 1283-1286, 1346, 1366, 1370, 1375, 1381-1385, 1388, 1393, 1395, 1404-1411, 1416, 1431-1435, 1441, 1444, 1449-1457, 1460-1463, 1470-1473, 1482-1484, 1487, 1496-1497, 1550, 1554, 1563, 1585, 1597, 1599, 1601, 1604, 1608, 1611, 1622-1624, 1644, 1647-1649, 1652, 1666, 1689, 1695, 1707-1713, 1718-1726, 1729, 1731, 1740-1745, 1754-1761, 1767-1773, 1776-1784, 1789, 1803-1810, 1815-1817, 1820-1829, 1832-1842, 1845, 1848, 1851
{base_venv_path}/lib/python{major}.{minor}/site-packages/click/decorators.py          147     89    39%   17, 27, 53-66, 71, 77-78, 83-85, 132, 149-153, 195-205, 220-225, 240-283, 296-307
{base_venv_path}/lib/python{major}.{minor}/site-packages/click/exceptions.py          115     81    30%   6-8, 18-23, 26, 29, 32-35, 38-40, 54-56, 59-70, 93-95, 98-106, 123-124, 127-148, 165-169, 172-179, 193-194, 206, 213-218, 221
{base_venv_path}/lib/python{major}.{minor}/site-packages/click/formatting.py          134     18    87%   59, 61, 68-69, 82, 108, 143-146, 185, 192-193, 197-198, 205-208, 250
{base_venv_path}/lib/python{major}.{minor}/site-packages/click/globals.py              18      4    78%   24-26, 45
{base_venv_path}/lib/python{major}.{minor}/site-packages/click/parser.py              236    122    48%   41-47, 50-64, 69-71, 77-79, 85, 94-95, 100-113, 126, 136, 150, 153-160, 167-169, 172-180, 239, 255-257, 270-272, 280, 292, 295-299, 323-325, 333-343, 346, 354-398, 406, 416-427
{base_venv_path}/lib/python{major}.{minor}/site-packages/click/termui.py              195    165    15%   42-43, 47-52, 92-138, 160-182, 190-229, 244-258, 344-346, 361-369, 425-449, 461, 476-478, 510-515, 540-541, 569-572, 576-577, 595-606
{base_venv_path}/lib/python{major}.{minor}/site-packages/click/testing.py             207     86    58%   19, 28-29, 32, 35-36, 39, 42, 45, 48, 51, 57-62, 66-67, 69, 94, 99, 105-107, 112, 159, 191-197, 201, 206-207, 216-220, 223-225, 228-232, 239, 253-260, 264-270, 318, 331, 334, 337-346, 364-374
{base_venv_path}/lib/python{major}.{minor}/site-packages/click/types.py               318    203    36%   55, 65, 69, 77, 83-84, 87-94, 101, 104, 111-123, 126, 145-146, 149, 152, 156-179, 183, 209, 216, 219-222, 226-231, 236, 243-246, 249, 268-285, 288, 295-298, 302, 316-318, 321-338, 341, 350-355, 358, 365-371, 374, 408-412, 415-421, 424-452, 493-510, 513-518, 521-560, 578, 582, 586, 589-592, 602, 608, 610, 620, 622, 628-634
{base_venv_path}/lib/python{major}.{minor}/site-packages/click/utils.py               179    124    31%   13-14, 22, 27-32, 37-42, 47-67, 79-95, 98, 101-103, 110-121, 125-126, 132-133, 136, 139, 142-143, 149, 152, 155, 158, 161, 164, 216, 222, 229, 237-242, 253-257, 274-277, 291-294, 321-327, 346-348, 363-365, 403-414, 429, 432-437, 440
{base_venv_path}/lib/python{major}.{minor}/site-packages/tabulate.py                  545    455    17%   14-25, 41, 113-121, 127-128, 132-141, 145-148, 153, 157-170, 173-181, 184-186, 195-199, 202-216, 412, 419-423, 439-444, 454, 469, 491-510, 526-537, 547-548, 558-559, 569-570, 574, 579-582, 593-600, 604-607, 612, 617-627, 631-654, 660-689, 693-696, 721-722, 737-756, 761-775, 780-787, 792-795, 829-955, 1244-1309, 1320-1326, 1330-1335, 1340-1341, 1346-1351, 1355-1356, 1360-1369, 1374-1381, 1385-1386, 1391-1432, 1458-1503, 1508-1510, 1514
{base_venv_path}/lib/python{major}.{minor}/site-packages/tg/__init__.py                 0      0   100%
{base_venv_path}/lib/python{major}.{minor}/site-packages/tg/commands/__init__.py        0      0   100%
{base_venv_path}/lib/python{major}.{minor}/site-packages/tg/commands/base.py          228    173    24%   33, 39, 43, 61-64, 69-72, 77-81, 87-117, 121-124, 129-132, 135-148, 155-188, 193-219, 222-237, 244-279, 282-293, 296-305, 308-317, 320-331, 334-343, 347-360, 363-388, 391-415, 418-431, 434-436, 439-441
{base_venv_path}/lib/python{major}.{minor}/site-packages/tg/commands/consts.py         20      0   100%
{base_venv_path}/lib/python{major}.{minor}/site-packages/tg/commands/zeroize.py        45      1    98%   24
{base_venv_path}/lib/python{major}.{minor}/site-packages/tg/tests/base.py              26      0   100%
{base_venv_path}/lib/python{major}.{minor}/site-packages/tg/tests/test_zeroize.py      29      1    97%   44
{base_venv_path}/lib/python{major}.{minor}/site-packages/tg/tg.py                     116     90    22%   39-59, 62-73, 121, 145-149, 153-225, 231-234, 238
----------------------------------------------------------------------------------------------------------
TOTAL                                                                         3982   2391    40%
""".format(
    base_venv_path=str(BASE_VENV_PATH),
    major=version_info.major,
    minor=version_info.minor,
)

SAMPLE_WIN_TG_REPORT_OUTPUT = """\
Name                                                                         Stmts   Miss  Cover   Missing
----------------------------------------------------------------------------------------------------------
C:\\temp\\tp\\Lib\\site-packages\\click\\testing.py              207     86    58%   19, 28-29, 32, 35-36, 39, 42, 45, 48, 51, 57-62, 66-67, 69, 94, 99, 105-107, 112, 159, 191-197, 201, 206-207, 216-220, 223-225, 228-232, 239, 253-260, 264-270, 318, 331, 334, 337-346, 364-374
C:\\temp\\tp\\Lib\\site-packages\\click\\types.py                207     86    58%   19, 28-29, 32, 35-36, 39, 42, 45, 48, 51, 57-62, 66-67
{base_venv_path}\\Lib\\site-packages\\tg\\__init__.py            0      0   100%
{base_venv_path}\\Lib\\site-packages\\tg\\commands\\__init__.py  0      0   100%
{base_venv_path}\\Lib\\site-packages\\tg\\commands\\base.py      228    173    24%   33, 39, 43, 61-64, 69-72, 77-81, 87-117, 121-124, 129-132, 135-148, 155-188, 193-219, 222-237, 244-279, 282-293, 296-305, 308-317, 320-331, 334-343, 347-360, 363-388, 391-415, 418-431, 434-436, 439-441
{base_venv_path}\\Lib\\site-packages\\tg\\commands\\consts.py    20      0   100%
{base_venv_path}\\Lib\\site-packages\\tg\\commands\\zeroize.py   45      1    98%   24
{base_venv_path}\\Lib\\site-packages\\tg\\tests\\base.py         26      0   100%
{base_venv_path}\\Lib\\site-packages\\tg\\tests\\test_zeroize.py 29      1    97%   44
{base_venv_path}\\Lib\\site-packages\\tg\\tg.py                  116     90    22%   39-59, 62-73, 121, 145-149, 153-225, 231-234, 238
----------------------------------------------------------------------------------------------------------
TOTAL                                                    3982   2391    40%
""".format(
    base_venv_path=str(BASE_VENV_PATH)
)

SAMPLE_SETUP_PY = """\
#!/usr/bin/env python3
# Copyright 2004-present Facebook. All Rights Reserved.

from setuptools import setup


# Specific Python Test Runner (ptr) params for Unit Testing Enforcement
ptr_params = {
    "test_suite": "coop.tests.base",
    "test_suite_timeout": 60,
    "required_coverage": {
        "coop/coop.py": 99,
        "coop/commands/pwn.py": 100,
        "coop/commands/destroy.py": 69,
        "TOTAL": 90,
    },
    "run_mypy": False,
}


setup(
    name="coop",
    version="6.9",
    packages=["coop", "coop.commands"],
    entry_points={"console_scripts": ["coop = coop.coop:main"]},
    install_requires=["click", "tabulate"],
    test_suite=ptr_params["test_suite"],
)
"""

# Disabled is set as we --run-disabled the run in CI
SAMPLE_SETUP_CFG = """\
[ptr]
disabled = true
entry_point_module = ptr
test_suite = ptr_tests
test_suite_timeout = 120
required_coverage_ptr.py = 85
required_coverage_TOTAL = 90
run_black = true
run_mypy = true
run_flake8 = true
run_pylint = true
run_pyre = true
"""

SAMPLE_SETUP_PY_PTR = {
    "test_suite": "coop.tests.base",
    "test_suite_timeout": 60,
    "required_coverage": {
        "coop/coop.py": 99,
        "coop/commands/pwn.py": 100,
        "coop/commands/destroy.py": 69,
        "TOTAL": 90,
    },
    "run_mypy": False,
}
