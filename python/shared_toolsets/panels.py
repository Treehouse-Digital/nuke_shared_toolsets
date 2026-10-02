"""Panel classes and routines for the shared toolsets create/rename GUI."""

from __future__ import annotations

from collections import defaultdict
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

import nuke
import nukescripts

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = (
    "BasePanel",
    "CreatePanel",
    "RenamePanel",
    "folder_path_options",
    "sanitize_new_path",
)


def folder_path_options(roster: Iterable[str], parent: str | None = None) -> list[str]:
    """Calculate folder paths to choose from in the panel.

    Roster is a list of all existing shared toolset items i.e. ``USER/foo/bar`` full
    menu sub-path pointing to ``/path/to/USER/foo/bar.nk`` file.
    """
    results = []
    prefix = ""
    if parent:
        prefix = f"{parent}.../"
    else:
        results.append(BasePanel.ROOT)

    sub_rosters: defaultdict[str, list[str]] = defaultdict(list)
    for path in map(Path, sorted(set(roster))):
        if non_blank_parents := tuple(path.parents)[:-1]:
            root = non_blank_parents[-1]
            sub_rosters[root.name].append(path.relative_to(root).as_posix())

    # Add all immediate subfolders first...
    results += [f"{prefix}{folder_name}" for folder_name in sub_rosters]

    # ...then any nested subfolders recursively
    for folder_name, sub_roster in sub_rosters.items():
        results += folder_path_options(sub_roster, parent=f"{prefix}{folder_name}")

    return results


@cache
def sanitize_new_path(path: str) -> str:
    """Sanitize a new path by converting it to a POSIX path and stripping whitespace."""
    return Path(path).as_posix().strip()


class BasePanel(nukescripts.PythonPanel):
    """Base panel class for shared toolsets create/rename panels."""

    ROOT: str = "<root>"
    """Menu item for the SharedToolSets root menu."""

    KNOBS: MappingProxyType[str, tuple[type[nuke.Knob], tuple]] = MappingProxyType(
        {
            "parentMenu": (
                nuke.CascadingEnumeration_Knob,
                ("Parent menu", []),
            ),
            "newPath": (nuke.String_Knob, ("Menu Path:",)),
            "ok": (nuke.PyScript_Knob, ("OK",)),
            "cancel": (nuke.PyScript_Knob, ("Cancel",)),
            "space": (nuke.Text_Knob, ("", "")),
            "infoText": (
                nuke.Text_Knob,
                (
                    '<span style="color:orange">"/" creates submenus,</span>',
                    '<span style="color:orange">example: newMenu/myNewToolSet</span>',
                ),
            ),
        }
    )
    """Read-only mapping of knob definitions."""

    def __init__(self, roster: Iterable[str], title: str = "") -> None:
        """Extend to store calculated folders, then add and configure extra knobs."""
        self._folder_paths = tuple(folder_path_options(roster))
        super().__init__(title=title)
        self._add_knobs()
        self._configure_knobs()

    def knobChangedCallback(self, knob: nuke.Knob) -> None:  # noqa: N802  # Inherited method naming
        """Extend to update the preset path when the parent folder choice changes."""
        if knob.name() == "parentMenu":
            self["newPath"].setValue(self._new_path_for_current_folder())
        elif knob.name() == "newPath":
            current = self["newPath"].value()
            sanitized = sanitize_new_path(current)
            if current != sanitized:
                self["newPath"].setValue(sanitized)
        else:
            super().knobChangedCallback(knob)

    # -- end of inherited methods, beginning of new methods --

    @property
    def new_path(self) -> str:
        """Current new path value set in the GUI."""
        return self["newPath"].value()

    def __getitem__(self, name: str) -> nuke.Knob:
        """Retrieve a knob by its name, raising KeyError if not found."""
        if name not in (knobs := self.knobs()):
            available = ",".join(map(repr, sorted(knobs)))
            msg = f"Knob {name!r} not found, only these are available: {available}"
            raise KeyError(msg)
        return knobs[name]

    def _add_knobs(self) -> None:
        """Add knobs based off initial values from the KNOBS mapping."""
        for knob_name, (knob_class, args) in self.KNOBS.items():
            self.addKnob(knob_class(knob_name, *args))

        # Ensure showModalDialog uses the panel's custom buttons.
        self.okButton = self["ok"]
        self.cancelButton = self["cancel"]

    def _configure_knobs(self) -> None:
        """Set knob values and properties after they've been created."""
        self["parentMenu"].setValues(self._folder_paths)
        self["parentMenu"].setTooltip(
            f"The menu location that the ToolSet will appear in. Specify {self.ROOT} "
            "to place the SharedToolSets in the main SharedToolSets menu."
        )
        self["newPath"].setFlag(nuke.STARTLINE)
        self["newPath"].setTooltip(
            "ToolSet name. Use the '/' character to create a new submenu for this "
            "ToolSet, eg to create a ToolSet named 'Basic3D' and place it in a new "
            "submenu '3D', type '3D/Basic3D'. Once created the 3D menu will appear in "
            "the ToolSet menu."
        )
        self["ok"].setFlag(nuke.STARTLINE)

    def _new_path_for_current_folder(self) -> str:
        """Calculate the new path for the current chosen folder."""
        current_name = Path(self["newPath"].value()).name
        chosen_folder_path: str = self["parentMenu"].value().replace(".../", "/")
        prefix = "" if chosen_folder_path == self.ROOT else f"{chosen_folder_path}/"
        return sanitize_new_path(f"{prefix}{current_name}")


class RenamePanel(BasePanel):
    """Panel for renaming an existing toolset."""

    def __init__(
        self,
        old_path: str,
        roster: Iterable[str],
        title: str = "Rename ToolSet",
    ) -> None:
        """Extend to store the path to rename before initializing the base panel."""
        self._old_path = str(old_path)
        super().__init__(roster, title=title)

    def _configure_knobs(self) -> None:
        super()._configure_knobs()
        self["ok"].setLabel("Rename")
        self["newPath"].setValue(self._old_path)


class CreatePanel(BasePanel):
    """Panel for creating a new toolset."""

    def __init__(self, roster: Iterable[str], title: str = "Create ToolSet") -> None:
        """Extend to initialise with "Create ToolSet" as the default title."""
        super().__init__(roster, title=title)

    def _configure_knobs(self) -> None:
        super()._configure_knobs()
        self["ok"].setLabel("Create")
