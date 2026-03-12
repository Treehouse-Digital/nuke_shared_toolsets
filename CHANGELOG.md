# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [1.7-th.2.0.0] - 2026-03-12

### Changed

- **Breaking**: Dropped support for Nuke that uses Python 2
  - Switched to use `pathlib` instead of `os` for path manipulations
- Many attempts at code cleanup and algorithm optimisations

### Added

- "Release on Tag" GitHub Action workflow

### Removed

- No-longer used `shared_toolsets.randomStringDigits`


## [1.7-th.1.0.0] - 2026-03-12

### Changed

- `ruff` formatted and linted.

### Added

- `pre-commit` config and CI, which also uses `ruff`
- `pyproject.toml` purely for `ruff` settings


## History

The following was pulled from the `shared_toolsets.py` source code's comments

```
0.1 - Made base functions
1.1 - Instead of delete menu added modify menu. There you can edit, rename(move) and delete toolsets.
1.2 - Minor bug fixes. Delete .nk~ files and fixed a bug with overwriting of an existed file.
1.3 - Added tooltip in menu. Crossplatform way to define the root folder. Added undistractive filefilter.
1.4 - Opps... into menu.py added this line of code: toolbar = nuke.menu('Nodes')
1.5 - Support of Nuke 11 and backward compatibility of previous versions.
1.6 - fixed a bug that caused Nuke crashing when loading of "big" toolsets
1.7 - added a support of nuke13.x, python 3
```
