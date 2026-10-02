"""GUI and menu management for shared toolsets."""

from __future__ import annotations

import contextlib
import logging
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

import nuke

from .logger import LOG, Timed
from .panels import CreatePanel, RenamePanel, validate_cmd_path
from .paths import DiskPath, clean_file, nice_mb

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = ("SharedToolsetGui", "delete_from_menu")


class _LoadCancelledError(Exception):
    """Internal signal used to stop localization when Nuke cancels progress."""


def _check_progress_cancelled(task: nuke.ProgressTask) -> None:
    if task.isCancelled():
        raise _LoadCancelledError


def delete_from_menu(root_menu: nuke.Menu, sub_path: str) -> None:
    """Remove an item from the given menu by its path, e.g. "Menu/SubMenu/Item".

    Nuke's documentation mentioned that `.nuke.Menu.removeItem` should be able to do
    this natively, but alas it doesn't (as recently as 14.1v8).
    """
    parts = sub_path.split("/")
    item_name = parts.pop()
    sub_menu_parts = []
    menu = root_menu

    for menu_name in parts:
        sub_menu_parts.append(menu_name)
        if submenu := menu.menu(menu_name):
            menu = submenu
        else:
            msg = "Nothing to delete as submenu %r not found in menu path %r"
            LOG.warning(msg, menu_name, "/".join(sub_menu_parts))
            return

    menu.removeItem(item_name)


class SharedToolsetGui:
    """Main Shared Toolset GUI class."""

    def __init__(
        self,
        disk_path: DiskPath,
        parent: nuke.Menu | None = None,
        *,
        localize: bool | None = None,
    ) -> None:
        """Initialize the SharedToolsetGui with the given disk path and parent menu.

        If ``localize`` is not specified (or None), then it'll be set to on if there's
        more than 1 prefixes being handled in the disk path.
        """
        self._disk_path = disk_path
        self._modify_menu: nuke.Menu | None = None
        self._menu_nk_roster: dict[str, Path] = {}
        if localize is None:
            localize = len(disk_path.prefixes) > 1
        self._localize = localize

        if parent is None:
            parent = nuke.menu("Nodes")
        elif not isinstance(parent, nuke.Menu):
            msg = "parent must be a nuke.Menu e.g. a nuke.Toolbar"
            raise TypeError(msg)
        self._parent = parent
        self._main_menu = self.parent.addMenu(
            "FastSharedToolsets", icon="SharedToolSets.png"
        )
        self._toolsets_root = disk_path.toolsets
        self.refresh()

    @property
    def toolsets_root(self) -> Path:
        """Root path where the shared toolsets are stored."""
        return self._toolsets_root

    @property
    def parent(self) -> nuke.Menu:
        """Parent menu of the shared toolsets main menu."""
        return self._parent

    @property
    def main_menu(self) -> nuke.Menu:
        """Main menu of the shared toolsets."""
        return self._main_menu

    def create(self, cmd_path: str) -> Path | None:
        """Create a new .nk file for the menu item/command path."""
        cmd_path = self._validate_cmd_path(cmd_path)
        nk_path = self._overwrite_approved_nk_path(cmd_path)
        if nk_path is None:
            return None

        temporary_path = nk_path.with_name(nk_path.name + ".part")
        try:
            with Timed(f"creating {nk_path}"):
                nk_path.parent.mkdir(parents=True, exist_ok=True)
                result = nuke.nodeCopy(str(temporary_path))
                if result is False or not temporary_path.is_file():
                    msg = f"Nuke did not create the toolset file {temporary_path}"
                    raise OSError(msg)
                temporary_path.replace(nk_path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

        LOG.info(f"Created new: {nk_path}")
        self.refresh()
        return nk_path

    def rename(self, old_cmd_path: str, new_cmd_path: str) -> Path | None:
        """Rename an existing menu item/command path to the new location."""
        old_cmd_path = validate_cmd_path(old_cmd_path)
        new_cmd_path = self._validate_cmd_path(new_cmd_path, ignore=old_cmd_path)
        old_nk_path = self._toolsets_root / f"{old_cmd_path}.nk"
        if not old_nk_path.is_file():
            msg = f"Source toolset no longer exists: {old_nk_path}"
            raise FileNotFoundError(msg)
        if old_cmd_path == new_cmd_path:
            return old_nk_path

        new_nk_path = self._overwrite_approved_nk_path(new_cmd_path)
        if new_nk_path is None:
            return None

        old_parent = old_nk_path.parent
        with Timed(f"renaming {old_nk_path} to {new_nk_path}"):
            new_nk_path.parent.mkdir(parents=True, exist_ok=True)
            old_nk_path.replace(new_nk_path)
            self._remove_empty_parents(old_parent)

        LOG.info(f"Renamed to new: {new_nk_path}")
        self.refresh()
        return new_nk_path

    def load(self, original_nk_path: Path) -> None:
        """Load toolset ``.nk`` file path given.

        If localization is enabled, the path will be temporarily localized to the
        current system's prefix before loading.
        """

        def suffix(file_path: Path) -> str:
            return f"{nice_mb(file_path)} from {file_path}"

        task = None
        try:
            with contextlib.ExitStack() as stack:
                nk_path = original_nk_path
                if self._localize:
                    task = nuke.ProgressTask(f"Localizing {nk_path.stem}")

                    def task_callback(percentage: float) -> None:
                        _check_progress_cancelled(task)
                        task.setProgress(int(percentage * 100))

                    nk_path = stack.enter_context(
                        self._disk_path.temp_localized(
                            original_nk_path, percent_callback=task_callback
                        )
                    )
                    _check_progress_cancelled(task)

                with Timed(f"loading {suffix(nk_path)}", level=logging.INFO):
                    nuke.loadToolset(str(nk_path))
        except _LoadCancelledError:
            LOG.info("Loading cancelled for %s", original_nk_path)
        except (OSError, ValueError) as error:
            LOG.exception("Could not load toolset %s", original_nk_path)
            nuke.message(f"Could not load toolset {original_nk_path}: {error}")
            self.refresh()
        finally:
            if task is not None:
                del task

    def delete(self, cmd_path: str) -> None:
        """Delete a menu item/command path after user confirmation."""
        if nuke.ask(f"Are you sure you want to delete\n\n{cmd_path}"):
            nk_path = self._menu_nk_roster.get(cmd_path)
            if not isinstance(nk_path, Path):
                LOG.warning("No .nk path found to delete for %r", cmd_path)
            elif not nk_path.is_file():
                LOG.info("%r already deleted: %s", cmd_path, nk_path)
            else:
                try:
                    with Timed(f"deleting {cmd_path} from disk"):
                        clean_file(nk_path, stop_at=self._toolsets_root)
                except OSError as error:
                    LOG.exception("Could not delete toolset %s", nk_path)
                    nuke.message(f"Could not delete toolset {nk_path}: {error}")
                finally:
                    self.refresh()
                return
            self.refresh()

    @Timed("refreshing shared toolsets menu", level=logging.INFO)
    def refresh(self) -> None:
        """Refresh the shared toolsets menu."""
        self._modify_menu = None
        self.main_menu.clearMenu()

        exclude_paths = self._nuke_excluded_paths()
        self._menu_nk_roster = self._disk_path.discover_paths_for_menus(
            exclude_paths=exclude_paths
        )

        self.main_menu.addCommand(
            "Create",
            command=self._create_callback,
            icon="SharedToolSets_Create.png",
        )
        self.main_menu.addCommand("-")
        self._populate_load_menu_items()
        self.main_menu.addCommand("-")
        self._modify_menu = self._create_modify_menu()
        self.main_menu.addCommand(
            "Refresh", command=self.refresh, icon="SharedToolSets_Refresh.png"
        )

    @Timed("populating load menu items")
    def _populate_load_menu_items(self, parent: nuke.Menu | None = None) -> None:
        parent = parent or self.main_menu
        for cmd_path, nk_path in self._menu_nk_roster.items():
            parent.addCommand(cmd_path, command=partial(self.load, nk_path))

    @Timed("creating Modify menu and items")
    def _create_modify_menu(self, parent: nuke.Menu | None = None) -> nuke.Menu:
        parent = parent or self.main_menu
        menu = parent.addMenu("Modify", icon="SharedToolSets_Modify.png")
        for cmd_path, nk_path in self._menu_nk_roster.items():
            # Don't use sub-menus i.e. menu.addMenu(cmd_path) will slow everything down
            modify_roster = (
                ["Edit", partial(nuke.scriptOpen, str(nk_path))],
                ["Rename", partial(self._rename_callback, cmd_path)],
                ["-", ""],
                ["Delete", partial(self.delete, cmd_path)],
            )
            for label, command in modify_roster:
                menu.addCommand(f"{cmd_path}/{label}", command=command)
        return menu

    def _create_callback(self) -> None:
        if not nuke.nodesSelected():
            nuke.message("No nodes are selected")
        elif (panel := CreatePanel(self._menu_nk_roster)).showModalDialog():
            try:
                self.create(panel.new_path)
            except (OSError, ValueError) as error:
                self._show_callback_error("create", error)

    def _rename_callback(self, old_cmd_path: str) -> None:
        panel = RenamePanel(old_cmd_path, self._menu_nk_roster)
        if panel.showModalDialog():
            try:
                self.rename(old_cmd_path, panel.new_path)
            except (OSError, ValueError) as error:
                self._show_callback_error("rename", error)

    def _overwrite_approved_nk_path(self, cmd_path: str) -> Path | None:
        nk_path = self._toolsets_root / f"{cmd_path}.nk"
        if nk_path.exists() and not nuke.ask(f"Overwrite existing\n\n{nk_path}"):
            LOG.debug("Refused to overwrite %s", nk_path)
            return None
        if nk_path.exists():
            LOG.info("Chosen to OVERWRITE %s", nk_path)
        return nk_path

    def _validate_cmd_path(self, cmd_path: str, ignore: str | None = None) -> str:
        normalized = validate_cmd_path(cmd_path)
        target = (self._toolsets_root / f"{normalized}.nk").resolve()
        try:
            target.relative_to(self._toolsets_root.resolve())
        except ValueError as error:
            msg = "Toolset path must remain inside the toolsets folder"
            raise ValueError(msg) from error

        for existing in self._menu_nk_roster:
            if existing == normalized:
                continue
            if existing == ignore and existing.startswith(normalized + "/"):
                continue
            if existing.startswith(normalized + "/") or normalized.startswith(
                existing + "/"
            ):
                msg = (
                    f"Menu path {normalized!r} conflicts with existing toolset "
                    f"{existing!r}"
                )
                raise ValueError(msg)
        return normalized

    def _remove_empty_parents(self, folder: Path) -> None:
        for parent in (folder, *folder.parents):
            if parent == self._toolsets_root:
                break
            try:
                parent.rmdir()
            except OSError:
                break

    @staticmethod
    def _nuke_excluded_paths() -> Iterable[str | Path]:
        get_excluded = getattr(nuke, "getToolsetExcludePaths", None)
        return get_excluded() if callable(get_excluded) else ()

    @staticmethod
    def _show_callback_error(action: str, error: OSError | ValueError) -> None:
        LOG.exception("Could not %s toolset", action)
        nuke.message(f"Could not {action} toolset: {error}")
