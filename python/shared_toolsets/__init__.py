"""Shared toolsets Python sub-package."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .logger import LOG
from .menus import SharedToolsetGui
from .paths import DiskPath

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ("LOG", "DiskPath", "SharedToolsetGui", "install", "instance")

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
    global __INSTANCE  # noqa: PLW0603  # We're hiding the global instance variable

    disk_path = DiskPath(toolsets_sub_path, **system_prefixes)
    __INSTANCE = SharedToolsetGui(disk_path)

    return __INSTANCE


def instance() -> SharedToolsetGui | None:
    """Get latest installed instance if available, or None otherwise."""
    return __INSTANCE
