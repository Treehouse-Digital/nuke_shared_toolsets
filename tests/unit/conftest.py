"""Shared fixtures and import-time Nuke stubs for unit tests."""

import platform
import sys
from unittest.mock import MagicMock

import pytest

nuke_stub = MagicMock(name="nuke")
nukescripts_stub = MagicMock(name="nukescripts")
nukescripts_stub.PythonPanel = type("PythonPanel", (), {})
sys.modules["nuke"] = nuke_stub
sys.modules["nukescripts"] = nukescripts_stub


@pytest.fixture
def fake_system(monkeypatch):
    import shared_toolsets.paths

    monkeypatch.setattr(shared_toolsets.paths, "SYSTEM", platform.system())
    return shared_toolsets.paths.SYSTEM


@pytest.fixture
def toolsets_dir(tmp_path):
    root = tmp_path / "SharedToolSets"
    (root / "nested").mkdir(parents=True)
    (root / "alpha.nk").write_text("Root toolset\n", encoding="utf-8")
    (root / "nested" / "beta.nk").write_text("Nested toolset\n", encoding="utf-8")
    (root / "stale.nk~").write_text("Backup\n", encoding="utf-8")
    return root


@pytest.fixture
def disk_path(toolsets_dir, fake_system):
    import shared_toolsets.paths

    prefixes = {
        fake_system: toolsets_dir.parent,
        **{
            system: prefix
            for system, prefix in {
                "Windows": "D:/",
                "Darwin": "/Volumes",
                "Linux": "/mnt",
            }.items()
            if system != fake_system
        },
    }
    return shared_toolsets.paths.DiskPath("SharedToolSets", **prefixes)
