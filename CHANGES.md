## `ptr` Change History

Each release to PyPI I'm going to give a codename as to where I am or was in the world 🌏.

### 2019.3.5
Codename: **Jaipur**

*🇮🇳 @cooperlees releasing whilst in Jaipur, India for a wedding 💒*

- Preliminary Windows support now ready for testing - Issue: #2
- Run tests/mypy/flake8 etc. in CWD of setup.py path - Issue #23 - Thanks @jreese
- Add support for linting with flake8 and pylint - Issue #20 - Thanks @jreese
- Ignore dotted directories when running black - PR #19 - Thanks @jreese

**Known Bug:** `black.exe` does not run in Windows 3.7 - **disabled** by *default* on Python 3.7 on Windows

### 2019.2.12
Codename: **Forbes**

*[Forbes, NSW, Australia](https://en.wikipedia.org/wiki/Forbes,_New_South_Wales) is the home of @aijayadams 👨🏻‍🦰🇦🇺*

- Added suite file coverage % to statistics JSON file - Issue: #16 - *Thanks @aijayadams*
- Ignore hidden '.' (dot) directories when running black - PR: #19 - *Thanks @jreese*

### 2019.2.10
Codename: **Carnival**

*🇧🇷 @cooperlees was in Rio de Janeiro, Brazil for Carnival 3 years ago today 🇧🇷*

- Added ptr `setup.cfg` support for ptr_params - Issue: #1
- Added JSON stats validation to `ci.py` - Issue: #7
- Fixed bug that allowed a step to run by default - Issue: #11

### 2019.2.8.post1/2

- Fix `setup.py` URL to ptr GitHub
- Other various `setup.py` fixes - e.g. Classifiers + License information

### 2019.2.8
Codename: **Snowbird**

*Recent shredding of Snowbird, UT, USA took place 🏂 🇺🇸*

- Initial Release to the world!
