![Static Badge](https://img.shields.io/badge/Nuke_14-PASS-green) ![Static Badge](https://img.shields.io/badge/Nuke_15-PASS-green)
![Static Badge](https://img.shields.io/badge/OSX-green) ![Static Badge](https://img.shields.io/badge/WIN-green) ![Static Badge](https://img.shields.io/badge/Linux-green)

# SharedToolSets
> SharedToolSets is an extended version of Nuke's toolsets that allows you to collaborate with your co-workers.

Demo: https://vimeo.com/168542667

## Installation

1. Setup a shared folder accessible for everybody in your network.
2. Extract this folder in there, i.e. `folder/with/SharedToolSets`, where the `init.py` file is located at `folder/with/SharedToolSets/init.py`
3. In your Nuke `init.py` file, add:

    ```python
    import nuke

    nuke.pluginAddPath("/path/to/folder/with/SharedToolSets")
    ```
Then for `menu.py`, if everyone is on Linux and the parent folder is just `/mnt`, add:

```python
import shared_toolsets
shared_toolsets.install("folder/with/SharedToolSets", Linux="/mnt")
```

If everyone is accessing the SharedToolset from different platforms, e.g.

- Windows `D:/folder/with/SharedToolSets`
- Mac `/Volumes/folder/with/SharedToolSets`
- Linux `/mnt/folder/with/SharedToolSets`

Then in your Nuke `menu.py` file, you would add:

```python
import shared_toolsets
shared_toolsets.install(
    "folder/with/SharedToolSets",
    Windows="D:/",
    Darwin="/Volumes",
    Linux="/mnt",
)
```

-----

If you have found this tool helpful, please consider supporting me with a donation. <br />
This will help me maintain current tools and develop new ones. Thanks for your support!

[![paypal](https://www.paypalobjects.com/en_US/i/btn/btn_donateCC_LG.gif)](https://paypal.me/vitmusatov)
