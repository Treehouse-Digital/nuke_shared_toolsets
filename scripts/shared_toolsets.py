# Shared ToolSets
# Based on Nuke's ToolSets
# Copyright (c) 2009 The Foundry Visionmongers Ltd.  All Rights Reserved.
# Vitaly Musatov
# emails:
# latest.green[at]gmail[dot]com
# vit.musatov[at]gmail[dot]com
# Use setSharedToolSetsPath function to setup location of shared folder, folder must be called "SharedToolSets", but you can place it anywhere.
# 19 April 2019
# version 1.6
# History:
# 0.1 - Made base functions
# 1.1 - Instead of delete menu added modify menu. There you can edit, rename(move) and delete toolsets.
# 1.2 - Minor bug fixes. Delete .nk~ files and fixed a bug with overwriting of an existed file.
# 1.3 - Added tooltip in menu. Crossplatform way to define the root folder. Added undistractive filefilter.
# 1.4 - Opps... into menu.py added this line of code: toolbar = nuke.menu('Nodes')
# 1.5 - Support of Nuke 11 and backward compatibility of previous versions.
# 1.6 - fixed a bug that caused Nuke crashing when loading of "big" toolsets
# 1.7 - added a support of nuke13.x, python 3

import random
import string
import tempfile
from collections import defaultdict
from pathlib import Path

import nuke
import nukescripts

SHARED_TOOLSET_PATH = ""
FILE_FILTER = None


def setSharedToolSetsPath(path):
    global SHARED_TOOLSET_PATH
    SHARED_TOOLSET_PATH = path


def addFileFilter(externalFilter):
    global FILE_FILTER
    FILE_FILTER = externalFilter


# def removeToolSets():
#  nodes = nuke.menu('Nodes')
#  nodes.removeItem("ToolSets")


class CreateToolsetsPanel(nukescripts.PythonPanel):
    # rename is bool var

    def __init__(self, fullFilePath, rename):

        self.rename = rename
        self.fullFilePath = fullFilePath

        if not rename:
            self.namePanel = "Create ToolSet"
            self.nameOkButton = "Create"
        else:
            self.namePanel = "Rename ToolSet"
            self.nameOkButton = "Rename"

        nukescripts.PythonPanel.__init__(
            self, self.namePanel, "uk.co.thefoundry.Toolset"
        )

        # CREATE KNOBS
        self.userFolders = []
        fullPath = SHARED_TOOLSET_PATH
        self.buildFolderList(fullPath, "")

        self.menuItemChoice = nuke.CascadingEnumeration_Knob(
            "menuItemChoice", "SharedToolSets menu", ["root"] + self.userFolders
        )
        self.menuItemChoice.setTooltip(
            "The menu location that the ToolSet will appear in. Specify 'root' to place the SharedToolSets in the main SharedToolSets menu."
        )
        self.menuPath = nuke.String_Knob("itemName", "Menu item:")
        self.menuPath.setFlag(0x00001000)
        self.menuPath.setTooltip(
            "ToolSet name. Use the '/' character to create a new submenu for this ToolSet, eg to create a ToolSet named 'Basic3D' and place it in a new submenu '3D', type '3D/Basic3D'. Once created the 3D menu will appear in the ToolSet menu."
        )
        self.okButton = nuke.PyScript_Knob(self.nameOkButton.lower(), self.nameOkButton)
        # self.okButton.setToolTip("Create a ToolSet from the currently selected nodes with the given name")
        self.okButton.setFlag(0x00001000)
        self.cancelButton = nuke.PyScript_Knob("cancel", "Cancel")
        self.space = nuke.Text_Knob("space", "", "")
        self.infoText = nuke.Text_Knob(
            "infoText",
            '<span style="color:orange">/ - create submenus,</span>',
            '<span style="color:orange">example: newMenu/myNewToolSet</span>',
        )

        # ADD KNOBS
        self.addKnob(self.menuItemChoice)
        self.addKnob(self.menuPath)
        self.addKnob(self.okButton)
        self.addKnob(self.cancelButton)
        self.addKnob(self.space)
        self.addKnob(self.infoText)

        if rename:
            toolSetPath = str(
                Path(fullFilePath).relative_to(SHARED_TOOLSET_PATH).with_suffix("")
            )
            self.menuPath.setValue(toolSetPath)

    # COMMENT:  BUILD A LIST Of PRE_CREATED FOLDER LOCATIONS
    def buildFolderList(self, rootFolder):
        rootPath = Path(rootFolder)
        self.userFolders += sorted(
            subFolder.relative_to(rootPath).as_posix()
            for subFolder in rootPath.rglob("*")
            if subFolder.is_dir()
        )

    def createPreset(self):
        if self.renameCreateSharedToolset(str(self.menuPath.value()), False):
            # if self.createSharedToolset(str(self.menuPath.value())):
            self.finishModalDialog(True)

    def renamePreset(self):
        if self.renameCreateSharedToolset(str(self.menuPath.value()), True):
            self.finishModalDialog(True)

    def renameCreateSharedToolset(self, name, rename):
        ret = False

        destFilePath = (
            Path(SHARED_TOOLSET_PATH, name).with_suffix(".nk").expanduser().resolve()
        )

        try:
            destFilePath.parent.mkdir(parents=True, exist_ok=True)
            srcFilePath = Path(self.fullFilePath).expanduser().resolve()

            if not destFilePath.exists():
                if self.rename:
                    srcFilePath.rename(destFilePath)
                else:
                    # create way
                    nuke.nodeCopy(str(destFilePath))

            elif nuke.ask("Overwrite existing \n %s?" % destFilePath):
                if self.rename:
                    destFilePath.unlink()
                    srcFilePath.rename(destFilePath)
                else:
                    # create way
                    nuke.nodeCopy(str(destFilePath))

            ret = True
        except Exception:
            ret = False
        return ret

    def getPresetPath(self):

        # COMMENT: Added a bit of usability. Let's preserve a toolset's name
        tempToolsetName = Path(self.menuPath.value()).name
        menuItemValue = str(self.menuItemChoice.value())
        self.menuPath.setValue(
            tempToolsetName
            if menuItemValue == "root"
            else f"{menuItemValue}/{tempToolsetName}"
        )

    def knobChanged(self, knob):
        if knob == self.okButton:
            if self.rename:
                self.renamePreset()
            else:
                self.createPreset()
        elif knob == self.cancelButton:
            self.finishModalDialog(False)
        elif knob == self.menuItemChoice:
            self.getPresetPath()


# NUKESCRIPT FUNCTIONS
def renameToolset(fullFilePath):
    p = CreateToolsetsPanel(fullFilePath, True)
    p.showModalDialog()
    rootPath = SHARED_TOOLSET_PATH
    checkForEmptyToolsetDirectories(rootPath)
    refreshToolsetsMenu()
    print(fullFilePath)


def addToolsetsPanel():
    res = False
    if nuke.nodesSelected():
        res = CreateToolsetsPanel(None, False).showModalDialog()
        # COMMENT: now force a rebuild of the menu
        refreshToolsetsMenu()
    else:
        nuke.message("No nodes are selected")
    return res


def deleteToolset(rootPath, fileName):
    fullPath = Path(fileName).expanduser().resolve()
    if nuke.ask("Are you sure you want to delete ToolSet %s?" % fullPath):
        fullPath.unlink()
        # COMMENT: if this was the last file in this directory, the folder will need to be deleted.
        # Walk the directory tree from the root and recursively delete empty directories
        checkForEmptyToolsetDirectories(rootPath)
        # COMMENT: now force a rebuild of the menu
        refreshToolsetsMenu()


def checkForEmptyToolsetDirectories(currPath):
    root = Path(currPath)
    toolset_folder = Path(SHARED_TOOLSET_PATH)

    # Collect all folders by their depth in the directory tree
    depthFolders = defaultdict(list)
    for subFolder in root.rglob("*"):
        if subFolder.is_dir() and subFolder != toolset_folder:
            depth = len(subFolder.relative_to(root).parts)
            depthFolders[depth].append(subFolder)

    # Remove empty folders starting from the deepest level
    for depth, folders in sorted(depthFolders.items(), reverse=True):
        for subFolder in folders:
            if not any(subFolder.iterdir()):
                subFolder.rmdir()


def refreshToolsetsMenu():
    toolbar = nuke.menu("Nodes")
    m = toolbar.findItem("SharedToolSets")
    if m is not None:
        m.clearMenu()
        createToolsetsMenu(toolbar)


def createToolsetsMenu(toolbar):
    menu = toolbar.addMenu(name="SharedToolSets", icon="SharedToolSets.png")
    menu.addCommand(
        "Create",
        "shared_toolsets.addToolsetsPanel()",
        "",
        icon="SharedToolSets_Create.png",
    )
    menu.addCommand("-", "", "")
    if populateToolsetsMenu(menu, False):
        menu.addCommand("-", "", "")
        subMenu = menu.addMenu("Modify", "SharedToolSets_Modify.png")
        populateToolsetsMenu(subMenu, True)
    menu.addCommand(
        "Refresh",
        "shared_toolsets.refreshToolsetsMenu()",
        icon="SharedToolSets_Refresh.png",
    )


def traversePluginPaths(
    menu,
    delete: bool,
    allToolsetsList: list,
    isLocal: bool,
) -> bool:
    return createToolsetMenuItems(
        menu,
        SHARED_TOOLSET_PATH,
        Path(SHARED_TOOLSET_PATH),
        delete,
        allToolsetsList,
        isLocal,
    )


def populateToolsetsMenu(menu, delete: bool):
    # COMMENT: now do shared toolsets like the local .nuke
    return traversePluginPaths(menu, delete, [], True)


def randomStringDigits(stringLength=6):
    """Generate a random string of letters and digits"""
    lettersAndDigits = string.ascii_letters + string.digits
    return "".join(random.choice(lettersAndDigits) for i in range(stringLength))


# COMMENT: warper around loadToolset
def toolsetLoader(fullFileName):
    if FILE_FILTER is not None:
        data = fileFilter(fullFileName, FILE_FILTER)
        # SAVING TEMPORAL TOOLSET | instead of
        # QApplication.clipboard().setText(data)
        # nuke.nodePaste("%clipboard%") is craching with big files BUG
        tempFileContext = tempfile.NamedTemporaryFile(
            suffix=".nk",
            dir=SHARED_TOOLSET_PATH,
            prefix="temp_toolset_",
        )
        with tempFileContext as tempFile:
            Path(tempFile.name).write_text(data)
            nuke.loadToolset(tempFile.name)
    else:
        nuke.loadToolset(fullFileName)
    return True


# COMMENT: modify file before loading
def fileFilter(fileName, filterFunc):
    with open(fileName) as f:
        content = f.readlines()
    modifiedContentList = []
    for line in content:
        if "file" in line:
            line = filterFunc(line)
        modifiedContentList.append(line)
    modifiedContent = "".join(modifiedContentList)
    return modifiedContent


def validDir(newPath: Path) -> bool:
    """Whether to not ignore this directory when building the menu."""
    posixNewPath = newPath.as_posix()
    return newPath.is_dir() and not (
        ".svn" in newPath.parts
        or any(
            Path(excludePath).as_posix() in posixNewPath
            for excludePath in nuke.getToolsetExcludePaths()
        )
    )


# COMMENT: Main function, construct menuName
def createToolsetMenuItems(
    menu,
    rootPath: str,
    folderPath: Path,
    delete: bool,
    allToolsetsList: list,
    isLocal: bool,
):
    success = False

    for subPath in sorted(folderPath.iterdir(), key=lambda p: p.name.lower()):
        if validDir(subPath):
            menuName = subPath.name
            if not isLocal:
                allToolsetsList.append(menuName)
            elif menuName in allToolsetsList:
                menuName = f"[user] {menuName}"

            subMenu = menu.addMenu(menuName)
            success = createToolsetMenuItems(
                subMenu,
                rootPath,
                subPath,
                delete,
                allToolsetsList,
                isLocal,
            )

        elif not subPath.is_dir():
            # COMMENT: delete file with an extension ".nk~" created by edit.
            if subPath.suffix.endswith(".nk~"):
                subPath.unlink()
            elif subPath.suffix.endswith(".nk"):
                label = subPath.stem
                if delete:
                    subMenu = menu.addMenu(label)
                    labelCommands = [
                        ("Edit", f'nuke.scriptOpen("{subPath}")'),
                        ("Rename", f'shared_toolsets.renameToolset("{subPath}")'),
                        ("-", ""),
                        (
                            "Delete",
                            f'shared_toolsets.deleteToolset("{rootPath}", "{subPath}")',
                        ),
                    ]
                    for label, command in labelCommands:
                        subMenu.addCommand(label, command)
                    success = True
                else:
                    # COMMENT: get the filename below toolsets
                    subfilename = str(subPath)
                    subfilenameHasFolders = False
                    for sharedToolSetsFolder in subPath.parents:
                        if (
                            sharedToolSetsFolder.is_dir()
                            and sharedToolSetsFolder.name == "SharedToolSets"
                        ):
                            root = sharedToolSetsFolder.parent
                            relPathToRoot = subPath.relative_to(root)
                            subfilename = str(relPathToRoot)
                            subfilenameHasFolders = len(relPathToRoot.parts) > 1
                            break

                    if not isLocal:
                        allToolsetsList.append(subfilename)
                    elif (subfilename in allToolsetsList) and subfilenameHasFolders:
                        # COMMENT: if we've already appended [user] to the menu name, don't need it on the filename
                        label = f"[user] {label}"

                    # TODO: get ref module name, now it is static linking
                    # current_module = sys.modules[__name__]
                    # print(current_module)
                    menu.addCommand(
                        label, f'shared_toolsets.toolsetLoader("{subPath!s}")'
                    )
                    success = True

    # COMMENT: if we are deleting, and the sub directory is now empty, delete the directory also
    if delete and not any(folderPath.iterdir()):
        folderPath.rmdir()

    return success
