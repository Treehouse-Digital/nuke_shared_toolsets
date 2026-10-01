"""GUI and menu management for shared toolsets."""

from __future__ import annotations

import contextlib
import logging
from functools import partial
from pathlib import Path

import nuke

from .logger import LOG, Timed
from .panels import CreatePanel, RenamePanel
from .paths import DiskPath, clean_file, nice_mb

__all__ = ("SharedToolsetGui", "delete_from_menu")


def delete_from_menu(root_menu: nuke.Menu, sub_path: str) -> None:
    """Remove a item from the given menu based on the sub path i.e. "Menu/SubMenu/Item".

    Nuke's documentation mentioned that `.nuke.Menu.removeItem` should be able to do
    this natively, but alas it doesn't (as recently as 14.1v8).
    """
    if parts := sub_path.split("/"):
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
        self._modify_menu = None
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
        LOG.debug(f"Creating {cmd_path = }")
        if nk_path := self._overwrite_approved_nk_path(cmd_path):
            with Timed(f"creating {nk_path}"):
                nk_path.parent.mkdir(parents=True, exist_ok=True)
                nuke.nodeCopy(str(nk_path))
            LOG.info(f"Created new: {nk_path}")
            self.refresh()
        return nk_path

    def rename(self, old_cmd_path: str, new_cmd_path: str) -> Path | None:
        """Rename an existing menu item/command path to the new location."""
        LOG.debug(f"Renaming {old_cmd_path = }")
        LOG.debug(f"      to {new_cmd_path = }")
        old_nk_path = self._toolsets_root / f"{old_cmd_path}.nk"
        LOG.debug(f"    from {old_nk_path = }")

        if new_nk_path := self._overwrite_approved_nk_path(new_cmd_path):
            with Timed(f"renaming to {new_nk_path}"):
                new_nk_path.parent.mkdir(parents=True, exist_ok=True)
                old_nk_path.replace(new_nk_path)
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

        with contextlib.ExitStack() as stack:
            nk_path = original_nk_path
            if self._localize:
                msg = f"localizing {suffix(original_nk_path)}"
                with Timed(msg, level=logging.INFO):
                    nk_path = stack.enter_context(
                        self._disk_path.temp_localized(original_nk_path)
                    )

            with Timed(f"loading {suffix(nk_path)}", level=logging.INFO):
                nuke.loadToolset(str(nk_path))

    def delete(self, cmd_path: str) -> None:
        """Delete a menu item/command path after user confirmation."""
        if nuke.ask(f"Are you sure you want to delete\n\n{cmd_path}"):
            with Timed(f"deleting {cmd_path} from menus"):
                delete_from_menu(self.main_menu, cmd_path)
                if self._modify_menu:
                    delete_from_menu(self._modify_menu, cmd_path)
            with Timed(f"deleting {cmd_path} from disk"):
                nk_path = self._menu_nk_roster.pop(cmd_path, None)
                if not isinstance(nk_path, Path):
                    LOG.warning(f"No .nk path found to delete for {cmd_path!r}")
                elif not nk_path.is_file():
                    LOG.info(f"{cmd_path!r} already deleted: {nk_path}")
                else:
                    clean_file(nk_path)

    @Timed("refreshing shared toolsets menu", level=logging.INFO)
    def refresh(self) -> None:
        """Refresh the shared toolsets menu."""
        self._modify_menu = None
        self.main_menu.clearMenu()

        self._disk_path.clean_temp_nk_files()
        self._menu_nk_roster = self._disk_path.discover_paths_for_menus()

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
        panel = CreatePanel(self._menu_nk_roster)
        if panel.showModalDialog():
            self.create(panel.new_path)

    def _rename_callback(self, old_cmd_path: str) -> None:
        panel = RenamePanel(old_cmd_path, self._menu_nk_roster)
        if panel.showModalDialog():
            self.rename(old_cmd_path, panel.new_path)

    def _overwrite_approved_nk_path(self, cmd_path: str) -> Path | None:
        nk_path = self._toolsets_root / f"{cmd_path}.nk"
        proceed = True
        if not nk_path.exists():
            LOG.debug(f"{nk_path} doesn't currently exist")
        elif proceed := nuke.ask(f"Overwrite existing\n\n{nk_path}"):
            nk_path.unlink()
            LOG.info(f"Chosen to OVERWRITE {nk_path}")
        else:
            LOG.debug(f"Refused to overwrite {nk_path}")
        return nk_path if proceed else None
