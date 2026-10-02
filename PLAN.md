# PLAN: address review findings and add non-Nuke unit tests

Scope: branch `complete-rewrite` versus `upstream/master`
(`git diff upstream/master`). This plan is for review first, then hand-off to an
agent. The implementation and automated checks are complete; manual Nuke 14/15
smoke testing remains pending.

Conventions for the agent:

- Python target is 3.9 (Nuke 14). The venv `.venv/` is Python 3.9.25.
- Keep changes focused. Do not add features beyond what a finding requires.
- Comments only where the code cannot say it itself, one short line.
- Do not touch `CHANGELOG.md` / `README.md` except where a finding says so.

---

## 1. Baseline facts (verified before implementation)

| Item | Value |
| --- | --- |
| Test runner | `.venv/bin/pytest` 8.4.2 |
| Coverage | `.venv/bin/coverage` 7.10.7 |
| `pytest-mock` | NOT installed (use `unittest.mock`) |
| `pip` in venv | not present; do not plan on installing extra packages |
| `ruff`, `pre-commit` | `~/.local/bin/ruff`, `~/.local/bin/pre-commit` (not in venv) |
| `ruff check python init.py` | passes today ("All checks passed!") |
| `.pre-commit-config.yaml` | pins ruff-pre-commit `v0.15.5`; no `files:` filter, so `tests/**` is linted automatically |
| `pyproject.toml` | only `[tool.ruff*]`; no pytest or coverage config yet |
| `.gitignore` | none in the repo (`git status` is clean, so something global/excluded ignores `.venv`, `.ruff_cache`); add one, see T0 |
| Existing tests | none (`tests/` does not exist) |
| Nuke imports | `menus.py` and `panels.py` import `nuke` / `nukescripts`. `paths.py` and `logger.py` do not. The package `__init__.py` imports `menus`, so importing anything under `shared_toolsets` needs to `unittest.mock.MagicMock` the `nuke` and `nukescripts` modules. |

Not run during the review (do these first, record results in the PR):

- `pre-commit run --all-files` (confirms the pinned ruff version agrees with `~/.local/bin/ruff`).
- Any runtime probe of `paths.py`. The findings below marked "confirm with test"
  come from reading the code and the Python 3.9 `pathlib` semantics.

---

## 2. Status of the previous review

Fixed in the current HEAD:

- `OSError(f"...")` replaced (`FileNotFoundError`), no EM102.
- Parenthesised multi-item `with` replaced by `ExitStack` (valid on 3.9).
- `Callable` typing in `logger.py`.
- Foreign-OS prefixes are no longer `.resolve()`d.
- Progress UI moved out of `DiskPath` into `SharedToolsetGui.load` via `percent_callback`.

Outstanding at the start of implementation (carried over, IDs below): localize returns `None` (B2),
temp-file double open (B3), `clean_file` climbs above the root (B4),
rename/overwrite data loss (B5), no selection check on create (B6), unvalidated
user paths (B7), timing format spec (B8), knob identity comparison (B9),
duplicate timing logs (P6), unused `_toolsets` (P7), changelog/attribution (D1, D2).

---

## 3. Findings and fixes

Priority: B = blocker (wrong behaviour / data loss), P = should fix before merge,
Q = polish. "Test" names refer to section 5.

### B1. Cross-OS prefixes cannot be constructed (`paths.py`, `_iter_resolved_prefixes`)

- `WindowsPath` / `PosixPath` are instantiated for foreign systems. On 3.9 this
  raises `NotImplementedError: cannot instantiate 'WindowsPath' on your system`
  (and the reverse on Windows). That makes the README's multi-platform example
  fail on every OS. (Confirm with test.)
- `.expanduser()` does not exist on `PurePath`, so the pure types need a different path.
- `system_prefixes` is annotated `str | Path` but is a mapping.

Fix:

- Use `PureWindowsPath` for `"Windows"` and `PurePosixPath` for other foreign
  systems. Only the current `SYSTEM` uses a real `Path` (with `.expanduser()`).
- Annotate as `Mapping[str, str | Path]`.
- Reject a root-only foreign prefix (`/`) with `ValueError`, it cannot be localized safely (see B2).

Test: `test_paths.py::TestDiskPathPrefixes`.

### B2. Localization regex and replacement are unsafe (`paths.py`)

Problems in `_calculate_localize_re` / `localize_any_posix`:

1. `localize_any_posix` has no `return`; it returns `None`, and
   `localized_file.write(None)` raises `TypeError`.
2. With a single prefix the pattern is `""`; `re.sub` would insert the prefix
   between every character. Only avoided today because `load()` skips
   localization when there is one prefix. `SharedToolsetGui(localize=True)` bypasses that.
3. Drive roots: `PureWindowsPath("D:/").as_posix()` is `"D:/"`. Replacing it by
   `/mnt` yields `/mntfolder/...`; the reverse gives `D://folder`. Normalize by stripping the
   trailing `/` from both sides.
4. No boundary: prefix `/mnt` matches inside `/home/mnt/x` and `/mntfoo`.
   Require "not preceded by a path character" and "followed by `/`, whitespace, quote or end of line".
5. Alternation order: sort prefixes longest first (`/Volumes/Project` before `/Volumes`).
6. Windows drive letters are case-insensitive (the old filter handled `P:` and
   `p:`). Match drive-letter prefixes case-insensitively; keep POSIX prefixes case-sensitive.
7. The replacement string is interpreted by `re` (backslashes, `\1`). Use a
   function replacement.
8. Annotation says `-> str`, returns `re.Pattern`.
9. Prefixes equal to the current system's prefix, or duplicated between systems, should be skipped from the pattern.

Fix: build the pattern from normalized (no trailing slash) foreign prefixes,
longest first, wrapped in the boundary lookarounds; return the substituted line.
Keep the public name `localize_any_posix`.

Optional (ask reviewer, see section 7): only substitute on lines containing `file`
like the old filter did. Pro: fewer false positives in node labels. Con: misses
other path-bearing knobs (`proxy`, `fonts`, custom).

Test: `test_paths.py::TestLocalizeAnyPosix`.

### B3. `NamedTemporaryFile` is opened twice (`paths.py`, `temp_localized`)

The handle stays open while `localized_path.open()` reopens the same name. This
fails with `PermissionError` on Windows. `delete_on_close` needs 3.12.

Fix: use `tempfile.mkdtemp(prefix=..., dir=os.getenv("NUKE_TEMP_DIR"))` and write
`<dir>/<nk_path.name>`; remove with `shutil.rmtree` in a `finally`. This also keeps the
toolset name visible in Nuke's undo/log. Alternatively `mkstemp` + `os.close`.

Also in the same function:

- Open both files with `newline=""` so `len(line.encode())` matches bytes on disk
  and line endings are preserved (progress will otherwise drift on CRLF files).
- Throttle `percent_callback`: only call when the integer percentage changes
  (a multi-GB file would otherwise make millions of GUI calls).
- If the callback raises, the temp dir must still be removed (covered by `finally`).
- Handle `NUKE_TEMP_DIR` set to a non-existent folder (fall back to the system temp dir, log a warning).

Test: `test_paths.py::TestTempLocalized`.

### B4. `clean_file` removes folders above the toolsets root (`paths.py`)

The loop over `path.parents` only stops at a non-empty folder. Deleting the last
toolset can remove the root and every empty ancestor.

Fix: `clean_file(path, stop_at: Path | None = None)`; never remove `stop_at` or
anything outside it. Callers (`SharedToolsetGui.delete`,
`DiskPath.clean_temp_nk_files`) pass the toolsets root. Also log `{path}` not `{path!r}`
(currently prints `PosixPath('...')`).

Test: `test_paths.py::TestCleanFile`.

### B5. Overwrite and rename can destroy data (`menus.py`)

- `_overwrite_approved_nk_path` unlinks the target before the new content is
  written. If `nodeCopy` raises or old and new are the same path, the toolset is lost.
- Rename to the identical name: the "overwrite" step deletes the source, then
  `old_nk_path.replace(...)` raises `FileNotFoundError`.
- Rename leaves the old, now empty, folders behind (old code cleaned them).
- Rename of a missing source (deleted by someone else) is not handled.

Fix:

- Split into "ask for approval" (no side effects) and "perform". Write via a
  sibling temp name (`<name>.nk.part`, does not match `*.nk` or `*.nk~`) and
  `Path.replace` into place after success.
- Return early (no prompt) when old and new command paths are equal.
- After rename, `clean_file`-style cleanup of the old parent folders up to the root.
- Wrap filesystem failures in a user-visible `nuke.message` (see Q3).

Verification: manual (section 6 step 6); `menus.py` has no automated tests.

### B6. Create does not check for selected nodes (`menus.py`)

The old code guarded with `nuke.nodesSelected()` and `nuke.message("No nodes are selected")`.
`_create_callback` now opens the dialog regardless and ignores `nuke.nodeCopy`'s return value.

Fix: check selection in `_create_callback` before opening the panel; check the
return value of `nodeCopy` and remove any partial file on failure.
(Verify in Nuke which of `nodesSelected()` / `selectedNodes()` is the right check
for 14 and 15; the old `== True` comparison is unreliable.)

Verification: manual (section 6 step 6); `menus.py` has no automated tests.

### B7. User-entered menu paths are not validated (`panels.py`, `menus.py`)

- `sanitize_new_path` allows `..` and absolute paths: `root / "/etc/x"` ignores
  the root, `../../x` escapes it (path traversal on a shared drive).
- Empty input becomes `"."`, producing a file named `..nk`.
- Whitespace is stripped only around the whole string, not per component.
- A trailing `.nk`, backslashes, control chars and reserved Windows characters
  (`<>:"|?*`) are accepted.
- `@cache` on this function is unbounded and unnecessary.

Fix: add a single validator, e.g. `validate_cmd_path(cmd_path) -> str` raising
`ValueError` with a user-readable message, used by the panel (message in the GUI)
and re-checked in `SharedToolsetGui` (defence in depth: resolved target must be
inside `toolsets_root`). Remove `@cache`.

Also check (confirm in Nuke): a command `a` and a command `a/b` collide in the menu
(leaf vs submenu); the panel's `...` trick avoids this for folders but not for
creating `a/b` while `a.nk` exists.

Verification: manual (section 6 step 6); `panels.py` / `menus.py` have no automated tests.

### B8. Timing format spec is wrong (`logger.py:39`)

`{x:7> .2f}` parses as fill `7`, align `>`, no width, so it does nothing useful.
Intended `{x:> 7.2f}` (right-aligned, width 7, leading space for sign).

Also: use `time.perf_counter()`; store start times so the same `Timed` instance
(class-level decorator on `refresh`, `_populate_load_menu_items`, ...) is safe if
re-entered (e.g. a stack list, or return a fresh copy from `_recreate_cm`).

Test: `test_logger.py`.

### B9. Knob identity comparison and OK/Cancel wiring (`panels.py`)

- `knob is self["parentMenu"]` relies on Nuke returning the same Python wrapper
  object each time; use `knob.name() == "parentMenu"` (or `==`).
- `self.okButton` / `self.cancelButton` are assigned so `showModalDialog` closes on
  OK/Cancel. This depends on `nukescripts.PythonPanel` internals. Manually verify
  in Nuke 14 and 15 that OK returns True, Cancel returns False, and the new path is
  updated when the parent menu changes. Fix typo "showModelDialog" in the comment.
- Prefer overriding the documented `knobChanged` if the base `knobChangedCallback`
  already routes to it (check in the Nuke install, not from memory).

Verification: manual (section 6 step 6); `panels.py` has no automated tests.

### P1. `DiskPath` public/private mismatch (`paths.py`)

- `self._toolsets` is computed (resolved, `strict=True`, doubles as existence
  check) but unused; the `toolsets` property returns the unresolved path.
  Decide: return the resolved path (symlinked mounts then show real paths in the
  log) or drop `_toolsets` and keep only the existence check. Recommended: use `_toolsets`.
- `localize()` is unused and `known_prefix and ...` is always truthy. Remove it,
  or keep it and test it (and use the same normalization as B2).
- Wrong return annotations: `_calculate_localize_re` (see B2).

### P2. Discovery walks the whole tree twice and includes repo folders (`paths.py`)

- `discover_paths_for_menus` and `clean_temp_nk_files` each `rglob` the share on
  every refresh. Walk once with `os.walk` (prune directories in-place), collect
  `*.nk`, and delete `*.nk~` in the same pass.
- README installs the plugin into the toolsets folder, so `.git/`, `.venv/`,
  `python/`, `icons/`, `tests/`, `.ruff_cache/` are walked, and any `.nk` fixture
  under `tests/` would become a menu item. Prune hidden directories and a small
  explicit exclude set. The old code also honored `.svn` and
  `nuke.getToolsetExcludePaths()`; decide whether to keep that (needs `nuke` in `paths.py`, which currently has none, so
  prefer an `exclude` argument passed in by `menus.py`).
- Keep `.nk~` cleanup behaviour, but note it deletes backups other users may be creating (existing upstream behaviour).

Test: `test_paths.py::TestDiscover`, `::TestCleanTempNkFiles`.

### P3. `load` error handling and ProgressTask lifetime (`menus.py`)

- `nice_mb()` raises `FileNotFoundError` if the file vanished since the last refresh;
  menu callbacks then surface a traceback. Catch `OSError`, `nuke.message`, and refresh.
- `del task` is not in `finally`; if localization raises, the progress dialog is
  closed only when the frame is garbage collected. Use `try/finally`.
- No cancel support: poll `task.isCancelled()` in the callback and abort cleanly
  (remove temp dir, do not load).
- Remove the empty-file `OSError` ambiguity: raise `ValueError` or a custom message that mentions the file.

### P4. `install()` input validation (`__init__.py`, `paths.py`)

- Keys not in `{"Windows", "Darwin", "Linux"}` (e.g. `linux`) are silently kept;
  the user then gets "No prefix defined for current system 'Linux'". Validate keys
  and mention the accepted names in the error.
- Calling `install()` twice re-uses the existing `FastSharedToolsets` menu
  (`addMenu` returns it) and refreshes; verify manually (section 6 step 6).
- `SharedToolsetGui.__init__` documents `parent: nuke.Menu`; confirm `nuke.Toolbar`
  subclasses `nuke.Menu` in 14/15 or the `isinstance` check rejects valid parents.

### P5. Delete leaves stale menu structure (`menus.py`)

`delete` removes the leaf from the menus, but empty parent submenus remain until
the user presses Refresh, and the menu is edited before the file deletion is known to
succeed (a permission error leaves menu and disk out of sync). Either call
`self.refresh()` after delete (simplest; then `delete_from_menu` could go), or
prune empty parent menus and only edit menus after the delete succeeded. Reviewer decision, see section 7.

### P6. Duplicate timing logs for localization

`SharedToolsetGui.load` and `DiskPath.temp_localized` both wrap the same work in
`Timed("localizing <size> from <path>")` at INFO. Keep one (prefer `temp_localized`).

### P7. Logging setup

`LOG = logging.getLogger("SharedToolSets")` has no handler; INFO/DEBUG output is
invisible unless the studio configures logging. Add `logging.NullHandler()` for
library hygiene and document how to enable output in the README (one line).

### Q1. Types and annotations that ruff cannot catch

- `_iter_resolved_prefixes(self, system_prefixes: str | Path)` -> `Mapping[...]`.
- `RenamePanel(roster: dict[str, Path])` vs `BasePanel(roster: Iterable[str])`: align.
- `SharedToolsetGui._modify_menu` is untyped (`nuke.Menu | None`).
- `delete_from_menu`: `if parts := sub_path.split("/")` is always truthy; simplify.
- Consider adding pyright or mypy later (out of scope here).

### Q2. Docstring typos

"Create a temporary a copy", "Remove a item", "Value of representing".

### Q3. User-facing failures

Menu callbacks (`create`, `rename`, `load`, `delete`) let filesystem exceptions
escape to Nuke's script editor. Catch `OSError` at the callback boundary only,
log with `LOG.exception`, and show `nuke.message(...)`.

### D1. CHANGELOG (`CHANGELOG.md`)

Add under the existing version: Changed (menu is now `FastSharedToolsets`;
localization is by per-OS prefix rather than a user-supplied filter function),
Removed (public API `setSharedToolSetsPath`, `addFileFilter`, `createToolsetsMenu`,
`refreshToolsetsMenu`, `addToolsetsPanel`, `toolsetLoader`; the sample
`SharedToolSets/SharedToolSet.nk`), Fixed/Added entries for the items above, and
tests/coverage config. Mark the API removals as breaking.

### D2. Attribution

The deleted `scripts/shared_toolsets.py` carried "Based on Nuke's ToolSets,
Copyright (c) 2009 The Foundry" and the original author credit/history. Check the
upstream licence and keep a notice in the README or a `NOTICE`/`LICENSE`
file if required. The README still links the original author's donation page.

### D3. README

- "Then for `menu.py`" sits directly under the numbered list's code fence; add a
  blank line and make it a numbered step.
- State that `.nk` toolsets live in the same folder as the plugin (so users know
  what gets scanned, see P2).
- Valid keyword names: `Windows`, `Darwin`, `Linux`.
- Optional: how to enable logging (P7).

---

## 4. Code-quality notes (code-quality skill)

- Lint is clean now, but ruff does not validate annotation correctness or logic;
  see Q1 and the blockers.
- The in-house convention in the `code-quality` skill (baked `.ruff.toml` via an
  `expand-ruff-extend` hook, `extend = "$TH_PIPELINE_ROOT/config/global-ruff.toml"`,
  a `files:` regex) is not used in this repo. `pyproject.toml` is self-contained and
  mirrors the global ignore list. Reviewer decision, see section 7.
- `**/tests/**/*.py` per-file ignores already exist. Tests will additionally
  trigger docstring rules (`D1xx`) and probably `PT*`, `S108`, `E501` on long
  parametrize ids. Add only the minimum needed to `[tool.ruff.lint.per-file-ignores]`
  (expected: `"D1"`), each with a one-line reason like the existing entries.
- Final gate: `pre-commit run --all-files`, then `ruff check` and `ruff format --check` on `tests/`.

---

## 5. Test plan (unit tests for `logger.py` and `paths.py`, pytest + coverage)

Brief: only create unit tests, mock the `nuke` and `nukescripts` modules, and only
test `logger.py` and `paths.py`, both of which do not import `nuke` or `nukescripts`.

Scope consequences:

- `nuke` and `nukescripts` are stubbed only so the package imports (its `__init__`
  imports `menus`, which imports `panels`). No test asserts on Nuke behaviour.
- `menus.py`, `panels.py` and `__init__.py` get no automated tests. Findings that live
  there (B5, B6, B7, B9, P3, P4 `install()` re-run, P5, Q3) are verified by the manual
  Nuke smoke test in section 6 step 6, not by pytest.
- Findings in `logger.py` / `paths.py` (B1 to B4, B8, P1, P2, P4 key validation, P7)
  each get regression tests below.

### T0. Tooling and config

Add to `pyproject.toml` (project convention: central config, no `.coveragerc`/`pytest.ini`):

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["python"]
addopts = ["-ra", "--strict-markers"]
markers = [
    "windows_only: requires a real Windows host",
    "posix_only: requires a real POSIX host",
]

[tool.coverage.run]
source_pkgs = ["shared_toolsets"]
branch = true

[tool.coverage.report]
# only the two modules under test; menus/panels/__init__ are imported but not tested
include = ["*/shared_toolsets/logger.py", "*/shared_toolsets/paths.py"]
show_missing = true
skip_empty = true
exclude_also = ["if TYPE_CHECKING:"]
# measured combined line/branch coverage is 94.19%; keep the whole-percent floor
fail_under = 94
```

Add `.gitignore`: `.venv/`, `.ruff_cache/`, `.pytest_cache/`, `.coverage*`, `htmlcov/`, `__pycache__/`.

Run commands (must work from the repo root, using the venv):

```bash
.venv/bin/coverage run -m pytest
.venv/bin/coverage report
.venv/bin/coverage html          # optional, htmlcov/index.html
```

Constraints: Python 3.9 syntax only in tests (no `match`, no parenthesised
`with`, no runtime `X | Y` unions); no `pytest-mock` (use `unittest.mock`); no `.nk`
files committed under `tests/` (they would be discovered as menu items if the repo
folder is used as a toolsets root); build all fixtures under `tmp_path`.

### T1. Layout

```
tests/
    unit/
        conftest.py          # nuke / nukescripts stubs + fixtures
        test_logger.py
        test_paths.py
```

(`INP001` is already ignored for tests, so `__init__.py` files are not needed.)

### T2. `conftest.py`: Nuke stubs and fixtures

At the top of `conftest.py` (not in a fixture; the stubs must exist before
`shared_toolsets` is first imported), install into `sys.modules`:

- `nuke`: a bare `unittest.mock.MagicMock()`. `menus.py` / `panels.py` only touch
  attributes of it at import time (`nuke.String_Knob`, ...), which a `MagicMock` absorbs.
- `nukescripts`: a `MagicMock()` whose `PythonPanel` is replaced by a real empty class
  (`type("PythonPanel", (), {})`), because `panels.BasePanel` subclasses it and a
  `MagicMock` attribute is not a usable base class.

No behaviour is added to the stubs. If a test needs more than this, the code under test
is in the wrong module for this suite.

Fixtures:

- `toolsets_dir`: `tmp_path / "SharedToolSets"` pre-populated with a few `.nk`
  files (including nested folders and a `.nk~`).
- `fake_system(monkeypatch)`: sets `shared_toolsets.paths.SYSTEM`.
- `disk_path`: `DiskPath("SharedToolSets", <system>=tmp_path, ...)` for the current host.

For other-OS scenarios on a Linux CI host: subclass `DiskPath` overriding
`_calculate_toolsets_path` (the class docstring explicitly allows overriding `_calculate_*`)
so the real filesystem is only touched for the current system. Real
Windows behaviours get `windows_only` tests that skip elsewhere.

### T3. `test_logger.py`

- `Timed` as context manager logs once at the requested level with the message.
- `Timed` as decorator logs once; `caplog` record `funcName`/`lineno` point at
  the caller, not `logger.py` (stacklevel 2 vs 3).
- Elapsed time formatting matches `r"took\s+\d+\.\d{2}s for ..."` (guards B8); patch `time.perf_counter`.
- Exception inside the block: still logged, exception propagates.
- Re-entrancy: nested use of the same decorated function logs two correct times.

### T4. `test_paths.py`

`nice_mb` (parametrize on sizes): 0 bytes -> 3 decimals; 0.5 MB; 1 MB; 9.99 MB;
10 MB; 99.9 MB; 100 MB; missing file raises `FileNotFoundError` with `.filename`.

`TestCleanFile`: not a `Path` -> warning, no exception; missing file; removes file and
empty parents; stops at first non-empty parent; stops at `stop_at` and never
removes it (B4); `stop_at` outside the path; log text uses plain path.

`TestDiskPathPrefixes` (B1, P1, P4):

- Current system only; current + foreign; foreign-only -> `ValueError` naming the system.
- `Windows="D:/"` on a POSIX host constructs without error (guards `NotImplementedError`).
- Blank prefix (`""`) is dropped; `~` expands only for the current system.
- Root-only foreign prefix `/` rejected.
- Unknown key (e.g. `linux`) rejected with a message listing valid names.
- Missing toolsets dir -> `FileNotFoundError`.
- `prefixes` is read-only (`MappingProxyType`), ordering preserved.
- `toolsets`, `system_prefix`, `toolsets_sub_path` values.

`TestLocalizeAnyPosix` (B2), parametrize over (prefixes, current system, input line, expected):

- `/Volumes` -> `/mnt` for a `file` line; no change when no prefix present.
- Windows `D:/` <-> `/mnt` both directions, including no `/mntfolder` and no `D://folder`.
- Lowercase drive `d:/` matches; POSIX prefix case-sensitive.
- Boundary: `/home/mnt/x` and `/mntfoo` unchanged.
- Longest prefix wins (`/Volumes/Project` over `/Volumes`).
- Several occurrences in one line; prefix at end of line; quoted path.
- Replacement containing backslashes or `\1` is inserted literally.
- Single-prefix instance returns the line unchanged (no empty-pattern corruption).
- Return type is `str` (guards the missing `return`).

`TestDiscover` / `TestCleanTempNkFiles` (P2): nested roster keys use `/` and no
suffix; sorted; ignores directories named `*.nk`; skips hidden/excluded dirs;
`.nk~` removed along with newly empty folders but never the root; second call is a no-op.

`TestTempLocalized` (B3):

- Yields a file with localized content; file and temp dir are removed after the context.
- Cleanup on exception raised inside the `with` body, and on callback exception.
- Empty source file raises the documented error.
- Honors `NUKE_TEMP_DIR`; missing `NUKE_TEMP_DIR` dir falls back.
- Non-ASCII (UTF-8) content round-trips; CRLF line endings preserved.
- `percent_callback` receives monotonic values in `[0, 1]`, ends at 1.0, and is
  called at most ~100 times for a large synthetic file.
- Windows-only: output file can be opened while the context is active (`windows_only`).

### T5. Coverage targets

the achieved floor (rounded down) at the end of the work. Every B-item in these two
test first, confirm it fails against current code, then fix.
Aim for >= 90 % line and branch coverage over `logger.py` and `paths.py` (the report
`include` in T0 excludes the untested modules). The implemented suite measures 94.19%,
with `fail_under = 94`. Every B-item in these two modules (B1 to B4, B8) has a
regression test that was confirmed failing before its fix.

---

## 6. Execution order

1. T0 tooling (pytest/coverage config, `.gitignore`), `conftest.py` with the `nuke` / `nukescripts` stubs. Run `pre-commit run --all-files` for a baseline.
2. Write failing tests for B1, B2, B3, B4, B8 (`logger.py` / `paths.py`); fix.
3. P1, P2, P4 (key validation), P7, Q1 (`paths.py` items) in `paths.py` / `logger.py`; tests.
4. B5, B6, B7, B9, P3, P4 (`install()` re-run), P5, P6, Q3 in `menus.py` / `panels.py` / `__init__.py`; no automated tests, covered by step 6.
5. D1, D2, D3 docs; final `pre-commit run --all-files`; coverage report pasted into the PR.
6. Manual Nuke smoke test (not automatable here), on Nuke 14 and 15:
   - install with one prefix and with Windows + Darwin + Linux prefixes;
   - Create with and without nodes selected; OK and Cancel both close the dialog;
   - Create over an existing toolset (approve and decline); a failed copy keeps the old file;
   - Enter invalid menu paths (empty, `..`, absolute, trailing `.nk`) and confirm nothing is written outside the toolsets folder;
  - Attempt leaf/submenu conflicts (`a` and `a/b`) during create and rename; confirm the conflict is rejected;
   - Parent menu dropdown rewrites the path; nested `...` entries;
   - Rename to the same name, to a new folder, onto an existing toolset; old empty folders are removed;
   - Delete the last toolset in a folder; Refresh; Edit opens the `.nk`;
   - Load a localized toolset (progress bar, cancel), then check node file paths;
   - Load a toolset deleted by someone else since the last refresh (message, no traceback);
   - Run twice-`install()` in the same session.
  - Install under a Nuke `Toolbar` parent and confirm it is accepted.

Definition of done:

- [x] `.venv/bin/coverage run -m pytest` green; `coverage report` meets `fail_under`.
- [x] `pre-commit run --all-files` green.
- [x] B1 to B4 and B8 have regression tests; remaining B/P code paths are implemented and listed for manual verification.
- [x] CHANGELOG/README updated; original attribution retained.
- [ ] Manual Nuke checklist completed on 14 and 15.

---

## 7. Implementation decisions

1. Localize every line; this also reaches path-bearing knobs beyond `file`.
2. Honor `nuke.getToolsetExcludePaths()` and `.svn`, in addition to pruning hidden and repository/tooling directories.
3. Refresh the full menu after delete.
4. Use the resolved `_toolsets` path and retain the `DiskPath.localize()` API.
5. Keep the self-contained Ruff configuration in `pyproject.toml`.
6. Keep `FastSharedToolsets`; the changelog records the old-to-new menu name for integrations.
7. Do not add a test-dependency manifest: pytest and coverage are already available in the specified venv, and the project has no package metadata or venv pip.
8. Set the local coverage gate to the measured rounded-down value, 93%; pre-commit remains a lint/format gate.
