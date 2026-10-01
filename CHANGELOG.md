# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [1.7-th.2.0.0] - 2026-10-01

### Changed

- Now a Python sub-package under `python` subfolder instead of single file under `scripts` subfolder
- Simpler install `init.py` instructions
- Overhauled `menu.py` installation instructions to use new `install()` function
- Minimum targeted Python version is now 3.9 (Nuke 14)

### Added

- This `CHANGELOG.md`
- pre-commit based checks using ruff, configured by `pyproject.toml`

### Removed

- Old `add_me_to_*.py` scripts in-favor of new installation instructions in `README.md`
