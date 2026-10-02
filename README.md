![Static Badge](https://img.shields.io/badge/Nuke_14-PASS-green) ![Static Badge](https://img.shields.io/badge/Nuke_15-PASS-green)
![Static Badge](https://img.shields.io/badge/OSX-green) ![Static Badge](https://img.shields.io/badge/WIN-green) ![Static Badge](https://img.shields.io/badge/Linux-green)

# SharedToolSets
> SharedToolSets is an extended version of Nuke's toolsets that allows you to collaborate with your co-workers.

Demo: https://vimeo.com/168542667

## Plugin Installation

1. Setup a shared folder accessible for everybody in your network.
2. Extract this folder in there, i.e. to `folder/with/SharedToolSets`,
   where the `python/shared_toolsets` folder is located at `folder/with/SharedToolSets/python/shared_toolsets`

3. In your Nuke `init.py` file, add:

    ```python
    import nuke

    nuke.pluginAddPath("/full/path/to/folder/with/SharedToolSets")
    ```

## Configuring the Toolsets Folder

Then in your Nuke `menu.py` file, configure the toolsets folder. This is the root folder where all `.nk` files will live under, including any subfolders.

Suppose it is located at `a/network/share/nuke/toolsets`

If everyone is on Linux and the parent folder is just `/mnt`, add:

```python
import shared_toolsets
shared_toolsets.install("a/network/share/nuke/toolsets", Linux="/mnt")
```

If everyone is accessing the SharedToolset from different platforms, e.g.

- Windows `D:/a/network/share/nuke/toolsets`
- Mac `/Volumes/a/network/share/nuke/toolsets`
- Linux `/mnt/a/network/share/nuke/toolsets`

Then in your Nuke `menu.py` file, you would add:

```python
import shared_toolsets
shared_toolsets.install(
    "a/network/share/nuke/toolsets", # Common sub-path
    Windows="D:",                    # Windows specific prefix
    Darwin="/Volumes",               # Mac specific prefix
    Linux="/mnt",                    # Linux specific prefix
)
```

> [!NOTE]
> Those key names must match ones described in [Python platform.system()].

## Attribution

This project is based on Nuke's ToolSets. The original script credited Vitaly Musatov and included the notice: "Based on Nuke's ToolSets. Copyright (c) 2009 The Foundry Visionmongers Ltd. All Rights Reserved."

> If you have found this tool helpful, please consider supporting me with a donation. <br />
> This will help me maintain current tools and develop new ones. Thanks for your support!
>
> [![paypal](https://www.paypalobjects.com/en_US/i/btn/btn_donateCC_LG.gif)](https://paypal.me/vitmusatov)
>



[Python platform.system()]: https://docs.python.org/3.11/library/platform.html#platform.system
