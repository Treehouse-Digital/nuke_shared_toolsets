"""Path management function and classes for shared toolsets."""

from __future__ import annotations

import contextlib
import os
import platform
import re
from collections import OrderedDict
from logging import INFO
from pathlib import Path, PosixPath, PurePath, WindowsPath
from tempfile import NamedTemporaryFile
from types import MappingProxyType
from typing import TYPE_CHECKING

from .logger import LOG, Timed

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Mapping

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


def clean_file(path: Path) -> None:
    """Delete given file path and remove any resulting empty parent folders."""
    if not isinstance(path, Path):
        LOG.warning(f"Expected a Path object, got {type(path).__name__!r} instead.")
    elif not path.is_file():
        LOG.info(f"{path!r} already deleted.")
    else:
        path.unlink()
        LOG.info(f"Deleted {path}")
        for folder in path.parents:
            if any(folder.iterdir()):
                break
            folder.rmdir()
            LOG.info(f"Deleted empty folder {folder}")


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
        blank_path = Path()
        for system, prefix in system_prefixes.items():
            if system == SYSTEM:
                cls = Path
            elif system == "Windows":
                cls = WindowsPath
            else:
                cls = PosixPath
            if (prefix_path := cls(prefix)) != blank_path:
                yield str(system), prefix_path.expanduser()

    def _calculate_system_prefix(self) -> Path:
        if SYSTEM not in self._system_prefixes:
            msg = f"No prefix defined for current system {SYSTEM!r}"
            raise ValueError(msg)
        return self._system_prefixes[SYSTEM]

    def _calculate_toolsets_path(self) -> Path:
        return (self._system_prefix / self._toolsets_sub_path).resolve(strict=True)

    def _calculate_localize_re(self) -> re.Pattern[str]:
        localize_re = "|".join(
            re.escape(prefix.as_posix())
            for system_name, prefix in self._system_prefixes.items()
            if system_name != SYSTEM
        )
        return re.compile(localize_re)

    @property
    def prefixes(self) -> MappingProxyType[str, Path]:
        """Read-only mapping of system names to their respective prefix paths."""
        return self._system_prefixes

    @property
    def toolsets(self) -> Path:
        """Full path to the toolsets, combining the system prefix and the sub-path."""
        return self.system_prefix / self.toolsets_sub_path

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
        iter_sub_path = (
            path.relative_to(Path(known_prefix))
            for known_prefix in self._system_prefixes.values()
            if known_prefix and path.is_relative_to(Path(known_prefix))
        )
        if not (sub_path := next(iter_sub_path, None)):
            prefixes = ", ".join(map(repr, self._system_prefixes))
            msg = f"{path} is not relative to any known system prefixes: {prefixes}"
            raise ValueError(msg)
        return self.system_prefix / sub_path

    def localize_any_posix(self, line: str) -> str:
        """Localize any known POSIX-style paths in the given line of text.

        Nuke stores all paths in ``.nk`` files in POSIX-style format, regardless of OS.
        """
        self._localize_re.sub(self.system_prefix.as_posix(), line)

    def discover_paths_for_menus(self) -> dict[str, Path]:
        """Discover and format ``.nk`` paths for toolsets menu items.

        The created dictionary maps menu item paths to their respective ``.nk`` full
        file paths on disk.
        """
        with Timed("discovering .nk files on disk"):
            nk_paths = sorted(
                path for path in self.toolsets.rglob("*.nk") if path.is_file()
            )
        return {
            path.with_suffix("").relative_to(self.toolsets).as_posix(): path
            for path in nk_paths
        }

    @Timed("cleaning temporary .nk~ files and resulting empty folders")
    def clean_temp_nk_files(self) -> None:
        """Clean up temporary .nk~ files and any resulting empty folders."""
        for path in self.toolsets.rglob("*.nk~"):
            if path.is_file():
                clean_file(path)

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
            raise OSError(msg)

        def dud_callback(_: float) -> None:
            """Don't do anything to given progress percentage."""

        percent_callback = percent_callback or dud_callback

        with NamedTemporaryFile(
            prefix="localize_shared_toolset_",
            suffix=".nk",
            dir=os.getenv("NUKE_TEMP_DIR"),
        ) as temp:
            localized_path = Path(temp.name)
            read_bytes = 0

            # Using ExitStack, can be changed to parenthesised with-statements >= Py3.10
            timed_msg = f"localizing {nice_mb(nk_path)} from {nk_path}"
            with contextlib.ExitStack() as stack:
                stack.enter_context(Timed(timed_msg, level=INFO))
                nk_file = stack.enter_context(nk_path.open(mode="rt", encoding="UTF-8"))
                localized_file = stack.enter_context(
                    localized_path.open(mode="wt", encoding="UTF-8")
                )
                for line in nk_file:
                    read_bytes += len(line.encode("UTF-8"))
                    percent_callback(read_bytes / total_bytes)
                    localized_file.write(self.localize_any_posix(line))

            yield localized_path
