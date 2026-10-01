from __future__ import annotations

from pathlib import Path

from .logger import LOG
from .menus import SharedToolsetGui
from .paths import DiskPath

__all__ = ("SharedToolsetGui", "LOG", "DiskPath", "install", "latest")

__INSTANCE: SharedToolsetGui | None = None


def install(
    toolsets_sub_path: str | Path,
    **system_prefixes: str | Path,
) -> SharedToolsetGui:
    """Install the shared toolsets GUI with the specified disk path.

    Designed for ability to localize depending on the system, ``toolsets_sub_path``
    specifies OS/platform-agnostic sub-path to the shared toolsets directory.

    Then provide at least 1 kwarg for the prefix specific to OS/platforms that are
    supported. The kwarg's name should be one of the known return values of
    `.platform.system` from Python's standard library.
    """
    global __INSTANCE

    disk_path = DiskPath(toolsets_sub_path, **system_prefixes)
    __INSTANCE = SharedToolsetGui(disk_path)

    return __INSTANCE


def latest() -> SharedToolsetGui | None:
    """Get latest installed instance if available, or None otherwise."""
    return __INSTANCE
