"""Path management function and classes for shared toolsets."""

from __future__ import annotations

import contextlib
import os
import platform
import re
import shutil
import tempfile
from collections import OrderedDict
from logging import INFO
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from types import MappingProxyType
from typing import TYPE_CHECKING

from .logger import LOG, Timed

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterable, Mapping

__all__ = ("DiskPath", "clean_file", "nice_mb")


SYSTEM = platform.system()
"""Current system name as returned by `.platform.system`."""


def nice_mb(file_path: Path) -> str:
    """Nice formatted string for the size of the given file in megabytes."""
    if not file_path.is_file():
        error = FileNotFoundError(f"{file_path} is not a valid file.")
        error.filename = file_path
        raise error

    mega = 10**6  # i.e. mega in megabytes
    file_size_mb = file_path.stat().st_size / mega

    decimals = next(
        _decimals
        for _decimals, limit in enumerate([100, 10, 1, None])
        if limit is None or file_size_mb >= limit
    )
    return f"{file_size_mb:.{decimals}f} MB"


def clean_file(path: Path, stop_at: Path | None = None) -> None:
    """Delete given file path and remove any resulting empty parent folders."""
    if not isinstance(path, Path):
        LOG.warning(f"Expected a Path object, got {type(path).__name__!r} instead.")
        return

    if stop_at is not None:
        try:
            path.relative_to(stop_at)
        except ValueError:
            LOG.warning(f"Refusing to clean {path} outside {stop_at}")
            return

    if not path.is_file():
        LOG.info(f"{path} already deleted.")
    else:
        path.unlink()
        LOG.info(f"Deleted {path}")
        for folder in path.parents:
            if stop_at is not None and folder == stop_at:
                break
            if any(folder.iterdir()):
                break
            folder.rmdir()
            LOG.info(f"Deleted empty folder {folder}")


_SUPPORTED_SYSTEMS = ("Windows", "Darwin", "Linux")
_PERCENT_SCALE = 100
_EXCLUDED_DIRS = frozenset(
    {".git", ".hg", ".svn", ".venv", ".ruff_cache", "__pycache__"}
)
_EXCLUDED_ROOT_DIRS = frozenset({"icons", "python", "tests"})


class DiskPath:
    """Class for managing disk paths for shared toolsets, regardless of OS.

    By default it focuses on just the OS/platform. Subclasses can override the various
    ``_calculate_*`` methods to achieve even more specific behaviors i.e. different file
    server mounts for different freelancers.
    """

    def __init__(
        self,
        toolsets_sub_path: str | Path,
        **system_prefixes: str | Path,
    ) -> None:
        """Initialize with OS/platform-agnostic sub-path and system-specific prefixes.

        Designed for ability to localize depending on the system, ``toolsets_sub_path``
        specifies OS/platform-agnostic sub-path to the shared toolsets directory.

        Then provide at least 1 kwarg for the prefix specific to OS/platforms that are
        supported. The kwarg's name should be one of the known return values of
        `.platform.system` from Python's standard library.
        """
        self._toolsets_sub_path = Path(toolsets_sub_path)
        self._system_prefixes = MappingProxyType(
            OrderedDict(self._iter_resolved_prefixes(system_prefixes))
        )
        self._system_prefix = self._calculate_system_prefix()
        self._toolsets = self._calculate_toolsets_path()
        self._localize_re = self._calculate_localize_re()

    def _iter_resolved_prefixes(
        self, system_prefixes: Mapping[str, str | Path]
    ) -> Generator[tuple[str, PurePath], None, None]:
        unknown_systems = set(system_prefixes).difference(_SUPPORTED_SYSTEMS)
        if unknown_systems:
            valid_systems = ", ".join(_SUPPORTED_SYSTEMS)
            msg = (
                f"Unknown system prefix key(s) {sorted(unknown_systems)!r}; "
                f"use {valid_systems}"
            )
            raise ValueError(msg)

        for system, prefix in system_prefixes.items():
            prefix_text = os.fspath(prefix).strip()
            if not prefix_text:
                continue
            if system == SYSTEM:
                prefix_path = Path(prefix_text).expanduser()
            elif system == "Windows":
                prefix_path = PureWindowsPath(prefix_text)
            else:
                prefix_path = PurePosixPath(prefix_text)
                if prefix_path == PurePosixPath("/"):
                    msg = f"Foreign POSIX prefix for {system!r} cannot be the root path"
                    raise ValueError(msg)
            yield str(system), prefix_path

    def _calculate_system_prefix(self) -> Path:
        if SYSTEM not in self._system_prefixes:
            msg = f"No prefix defined for current system {SYSTEM!r}"
            raise ValueError(msg)
        return self._system_prefixes[SYSTEM]

    def _calculate_toolsets_path(self) -> Path:
        return (self._system_prefix / self._toolsets_sub_path).resolve(strict=True)

    def _calculate_localize_re(self) -> re.Pattern[str]:
        current_prefix = self._normalize_prefix(self._system_prefix)
        seen_prefixes = {self._prefix_key(current_prefix)}
        alternatives = []
        targets = {}

        foreign_prefixes = sorted(
            (
                self._normalize_prefix(prefix)
                for system_name, prefix in self._system_prefixes.items()
                if system_name != SYSTEM
            ),
            key=len,
            reverse=True,
        )
        for index, prefix in enumerate(foreign_prefixes):
            prefix_key = self._prefix_key(prefix)
            if not prefix or prefix_key in seen_prefixes:
                continue
            seen_prefixes.add(prefix_key)
            group = f"prefix{index}"
            drive_match = re.match(r"^[A-Za-z]:", prefix)
            if drive_match:
                drive = re.escape(prefix[:2])
                rest = re.escape(prefix[2:])
                expression = f"(?i:{drive}){rest}"
            else:
                expression = re.escape(prefix)
            alternatives.append(f"(?P<{group}>{expression})")
            targets[group] = current_prefix

        self._localize_targets = targets
        if not alternatives:
            return re.compile(r"(?!)")

        alternatives_re = "|".join(alternatives)
        return re.compile(rf"(?<![\w./\\:-])(?:{alternatives_re})(?=[/\s'\"]|$)")

    @staticmethod
    def _normalize_prefix(prefix: PurePath) -> str:
        value = prefix.as_posix()
        if len(value) > 1:
            value = value.rstrip("/")
        return value

    @staticmethod
    def _prefix_key(prefix: str) -> str:
        if re.match(r"^[A-Za-z]:", prefix):
            return prefix[0].lower() + prefix[1:]
        return prefix

    @property
    def prefixes(self) -> Mapping[str, PurePath]:
        """Read-only mapping of system names to their respective prefix paths."""
        return self._system_prefixes

    @property
    def toolsets(self) -> Path:
        """Full path to the toolsets, combining the system prefix and the sub-path."""
        return self._toolsets

    @property
    def system_prefix(self) -> Path:
        """System-specific prefix for the toolset full path."""
        return self._system_prefix

    @property
    def toolsets_sub_path(self) -> Path:
        """Sub-path for the toolsets relative to the system prefix."""
        return self._toolsets_sub_path

    def localize(self, path: Path) -> Path:
        """Localize a given path to the current system's prefix."""
        path_text = path.as_posix()
        for known_prefix in self._system_prefixes.values():
            prefix_text = self._normalize_prefix(known_prefix)
            if path_text == prefix_text:
                sub_path = ""
            elif prefix_text == "/" and path_text.startswith("/"):
                sub_path = path_text.lstrip("/")
            elif prefix_text and path_text.startswith(prefix_text + "/"):
                sub_path = path_text[len(prefix_text) + 1 :]
            else:
                continue
            return self.system_prefix / Path(sub_path)

        prefixes = ", ".join(map(repr, self._system_prefixes))
        msg = f"{path} is not relative to any known system prefixes: {prefixes}"
        raise ValueError(msg)

    def localize_any_posix(self, line: str) -> str:
        """Localize any known POSIX-style paths in the given line of text.

        Nuke stores all paths in ``.nk`` files in POSIX-style format, regardless of OS.
        """

        def replace(match: re.Match[str]) -> str:
            replacement = self._localize_targets[match.lastgroup]
            suffix = line[match.end() :]
            if suffix.startswith("/") and replacement.endswith("/"):
                return replacement[:-1]
            if (
                not suffix or suffix[0].isspace() or suffix[0] in "'\""
            ) and re.fullmatch(r"[A-Za-z]:", replacement):
                return f"{replacement}/"
            return replacement

        return self._localize_re.sub(replace, line)

    def discover_paths_for_menus(
        self, exclude_paths: Iterable[str | Path] = ()
    ) -> dict[str, Path]:
        """Discover and format ``.nk`` paths for toolsets menu items.

        The created dictionary maps menu item paths to their respective ``.nk`` full
        file paths on disk.
        """
        with Timed("discovering .nk files on disk"):
            nk_paths, backup_paths = self._walk_toolsets(exclude_paths)
            for backup_path in backup_paths:
                clean_file(backup_path, stop_at=self.toolsets)
        return {
            path.with_suffix("").relative_to(self.toolsets).as_posix(): path
            for path in nk_paths
        }

    @Timed("cleaning temporary .nk~ files and resulting empty folders")
    def clean_temp_nk_files(self, exclude_paths: Iterable[str | Path] = ()) -> None:
        """Clean up temporary .nk~ files and any resulting empty folders."""
        _, backup_paths = self._walk_toolsets(exclude_paths)
        for backup_path in backup_paths:
            clean_file(backup_path, stop_at=self.toolsets)

    def _walk_toolsets(
        self, exclude_paths: Iterable[str | Path]
    ) -> tuple[list[Path], list[Path]]:
        root = self.toolsets
        excluded = []
        for excluded_path in exclude_paths:
            excluded_text = os.fspath(excluded_path).replace("\\", "/").rstrip("/")
            if not excluded_text:
                continue
            excluded_path_obj = Path(excluded_text)
            if not excluded_path_obj.is_absolute():
                excluded_path_obj = root / excluded_path_obj
            excluded.append(excluded_path_obj.as_posix().rstrip("/"))

        nk_paths = []
        backup_paths = []
        for directory, dirnames, filenames in os.walk(root):
            directory_path = Path(directory)
            kept_dirnames = []
            for dirname in sorted(dirnames):
                child_path = directory_path / dirname
                child_text = child_path.as_posix().rstrip("/")
                is_root_excluded = (
                    directory_path == root and dirname in _EXCLUDED_ROOT_DIRS
                )
                is_hidden_or_metadata = (
                    dirname.startswith(".") or dirname in _EXCLUDED_DIRS
                )
                is_user_excluded = any(
                    child_text == excluded_path
                    or child_text.startswith(excluded_path + "/")
                    for excluded_path in excluded
                )
                if not (is_root_excluded or is_hidden_or_metadata or is_user_excluded):
                    kept_dirnames.append(dirname)
            dirnames[:] = kept_dirnames

            for filename in sorted(filenames):
                file_path = directory_path / filename
                if filename.endswith(".nk~") and file_path.is_file():
                    backup_paths.append(file_path)
                elif filename.endswith(".nk") and file_path.is_file():
                    nk_paths.append(file_path)

        return sorted(nk_paths), backup_paths

    @contextlib.contextmanager
    def temp_localized(
        self, nk_path: Path, percent_callback: Callable[[float], None] | None = None
    ) -> Generator[Path, None, None]:
        """Create a temporary copy of the .nk file with paths localized.

        This is done line by line in case the .nk file is large i.e. gigabytes in size
        because some people forgot to cleanup their roto shapes.

        Nuke also always saves (modern) .nk files in UTF-8 encoding, which we explicitly
        use in-case artist's system locale preferred encoding is different.
        """
        total_bytes = nk_path.stat().st_size
        if not total_bytes:
            msg = f"File {nk_path} is empty i.e. 0 bytes in size"
            raise ValueError(msg)

        temp_root = os.getenv("NUKE_TEMP_DIR")
        if temp_root and not Path(temp_root).is_dir():
            LOG.warning(
                "NUKE_TEMP_DIR %r does not exist; using the system temp folder",
                temp_root,
            )
            temp_root = None
        temp_directory = Path(
            tempfile.mkdtemp(prefix="localize_shared_toolset_", dir=temp_root)
        )
        localized_path = temp_directory / nk_path.name
        try:
            read_bytes = 0
            timed_msg = f"localizing {nice_mb(nk_path)} from {nk_path}"
            last_percent = -1
            with contextlib.ExitStack() as stack:
                stack.enter_context(Timed(timed_msg, level=INFO))
                nk_file = stack.enter_context(
                    nk_path.open(mode="rt", encoding="UTF-8", newline="")
                )
                localized_file = stack.enter_context(
                    localized_path.open(mode="wt", encoding="UTF-8", newline="")
                )
                for line in nk_file:
                    read_bytes += len(line.encode("UTF-8"))
                    percentage = min(read_bytes / total_bytes, 1.0)
                    integer_percent = int(percentage * _PERCENT_SCALE)
                    if percent_callback is not None and integer_percent != last_percent:
                        percent_callback(percentage)
                        last_percent = integer_percent
                    localized_file.write(self.localize_any_posix(line))

            if percent_callback is not None and last_percent != _PERCENT_SCALE:
                percent_callback(1.0)

            yield localized_path
        finally:
            shutil.rmtree(temp_directory)
