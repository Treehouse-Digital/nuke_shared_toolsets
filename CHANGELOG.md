# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [1.7-th.2.0.0] - 2026-10-01

### Breaking

- Removed the legacy public APIs `setSharedToolSetsPath`, `addFileFilter`,
  `createToolsetsMenu`, `refreshToolsetsMenu`, `addToolsetsPanel`, and
  `toolsetLoader`, along with the sample `SharedToolSets/SharedToolSet.nk`.
- The generated menu is now named `FastSharedToolsets` instead of
  `SharedToolSets`; integrations that refer to the old menu name must be updated.

### Changed

- Now a Python sub-package under `python` subfolder instead of single file under `scripts` subfolder
- Simpler install `init.py` instructions
- Overhauled `menu.py` installation instructions to use new `install()` function
- Minimum targeted Python version is now 3.9 (Nuke 14)
- Toolset paths are localized from the configured per-OS prefixes.
- Menu discovery prunes hidden and repository/tooling directories and cleans `.nk~` backups in one scan.

### Fixed

- Cross-platform prefix handling, path localization boundaries, and temporary localized-file cleanup.
- Toolset create and rename operations preserve existing files until a replacement is ready.
- Menu paths are validated before use, and deleting the final item keeps the menu and disk in sync.
- Progress reporting, cancellation, missing-file handling, and elapsed-time logging.

### Added

- This `CHANGELOG.md`
- pre-commit based checks using ruff, configured by `pyproject.toml`
- Non-Nuke unit tests and pytest/coverage configuration for `logger.py` and `paths.py`.

### Removed

- Old `add_me_to_*.py` scripts in-favor of new installation instructions in `README.md`
