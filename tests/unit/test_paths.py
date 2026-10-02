from __future__ import annotations

import logging
import os
from collections import OrderedDict
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import MappingProxyType
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from shared_toolsets.paths import DiskPath, clean_file, nice_mb

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


def make_localizer(system, current_prefix, foreign_prefixes):
    disk_path = object.__new__(DiskPath)
    disk_path._system_prefix = current_prefix
    disk_path._system_prefixes = MappingProxyType(
        OrderedDict([(system, current_prefix), *foreign_prefixes.items()])
    )
    with patch("shared_toolsets.paths.SYSTEM", system):
        disk_path._localize_re = disk_path._calculate_localize_re()
    return disk_path


def host_prefixes(system, current_prefix):
    return {
        system: current_prefix,
        **{
            name: prefix
            for name, prefix in {
                "Windows": "D:/",
                "Darwin": "/Volumes",
                "Linux": "/mnt",
            }.items()
            if name != system
        },
    }


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        (0, "0.000 MB"),
        (500_000, "0.500 MB"),
        (1_000_000, "1.00 MB"),
        (9_990_000, "9.99 MB"),
        (10_000_000, "10.0 MB"),
        (99_900_000, "99.9 MB"),
        (100_000_000, "100 MB"),
    ],
)
def test_nice_mb_formatting(tmp_path, size, expected):
    file_path = tmp_path / "size.nk"
    file_path.write_bytes(b"x" * size)

    assert nice_mb(file_path) == expected


def test_nice_mb_missing_file_has_filename(tmp_path):
    missing = tmp_path / "missing.nk"

    with pytest.raises(FileNotFoundError) as error:
        nice_mb(missing)

    assert error.value.filename == missing


def test_clean_file_ignores_non_path(caplog):
    with caplog.at_level(logging.WARNING):
        clean_file("not-a-path")

    assert "Expected a Path object" in caplog.text


def test_clean_file_removes_empty_parents_but_stops_at_root(tmp_path, caplog):
    root = tmp_path / "root"
    nested = root / "one" / "two"
    nested.mkdir(parents=True)
    file_path = nested / "tool.nk~"
    file_path.touch()

    with caplog.at_level(logging.INFO):
        clean_file(file_path, stop_at=root)

    assert not file_path.exists()
    assert not nested.exists()
    assert not (root / "one").exists()
    assert root.is_dir()
    assert str(file_path) in caplog.text
    assert "PosixPath(" not in caplog.text


def test_clean_file_stops_at_nonempty_parent(tmp_path):
    root = tmp_path / "root"
    nested = root / "folder"
    nested.mkdir(parents=True)
    (root / "keep.nk").touch()
    file_path = nested / "remove.nk"
    file_path.touch()

    clean_file(file_path, stop_at=root)

    assert not file_path.exists()
    assert not nested.exists()
    assert (root / "keep.nk").exists()


def test_clean_file_does_not_touch_paths_outside_stop_at(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    file_path = outside / "keep.nk"
    file_path.touch()

    clean_file(file_path, stop_at=tmp_path / "root")

    assert file_path.exists()
    assert outside.is_dir()


def test_clean_file_missing_path_is_noop(tmp_path, caplog):
    missing = tmp_path / "missing.nk"
    with caplog.at_level(logging.INFO):
        clean_file(missing, stop_at=tmp_path)
    assert "already deleted" in caplog.text


def test_disk_path_prefixes_current_and_foreign(toolsets_dir, fake_system):
    disk_path = DiskPath(
        "SharedToolSets", **host_prefixes(fake_system, toolsets_dir.parent)
    )

    assert disk_path.toolsets == toolsets_dir.resolve()
    assert disk_path.system_prefix == toolsets_dir.parent
    assert disk_path.toolsets_sub_path == Path("SharedToolSets")
    assert isinstance(disk_path.prefixes, MappingProxyType)
    assert list(disk_path.prefixes) == list(
        host_prefixes(fake_system, toolsets_dir.parent)
    )
    with pytest.raises(TypeError):
        disk_path.prefixes["Linux"] = Path("/mnt")


@pytest.mark.skipif(
    os.name == "nt", reason="Windows is the current, not foreign, system"
)
@pytest.mark.posix_only
def test_disk_path_accepts_foreign_windows_prefix_on_posix(toolsets_dir, fake_system):
    disk_path = DiskPath(
        "SharedToolSets", **host_prefixes(fake_system, toolsets_dir.parent)
    )

    assert disk_path.prefixes["Windows"] == PureWindowsPath("D:/")


def test_disk_path_drops_blank_prefix_and_expands_current_home(
    toolsets_dir, fake_system, monkeypatch
):
    if fake_system == "Windows":
        pytest.skip("This case checks a foreign Windows prefix on a POSIX host")
    monkeypatch.setenv("HOME", str(toolsets_dir.parent))
    blank_system = "Darwin" if fake_system != "Darwin" else "Linux"
    prefixes = {fake_system: "~", blank_system: ""}
    prefixes["Windows"] = "D:/"
    disk_path = DiskPath("SharedToolSets", **prefixes)

    assert disk_path.system_prefix == toolsets_dir.parent
    assert "Darwin" not in disk_path.prefixes
    assert disk_path.prefixes["Windows"] == PureWindowsPath("D:/")


def test_disk_path_requires_current_prefix(toolsets_dir, fake_system):
    foreign_system = next(
        name for name in ("Windows", "Darwin", "Linux") if name != fake_system
    )
    with pytest.raises(ValueError, match=fake_system):
        DiskPath("SharedToolSets", **{foreign_system: "/elsewhere"})


def test_disk_path_rejects_unknown_system_name(toolsets_dir, fake_system):
    with pytest.raises(ValueError, match=r"Windows.*Darwin.*Linux"):
        DiskPath(
            "SharedToolSets", **{fake_system: toolsets_dir.parent, "linux": "/mnt"}
        )


def test_disk_path_rejects_foreign_posix_root(toolsets_dir, fake_system):
    foreign_system = "Darwin" if fake_system != "Darwin" else "Linux"
    with pytest.raises(ValueError, match="root"):
        DiskPath(
            "SharedToolSets",
            **{fake_system: toolsets_dir.parent, foreign_system: "/"},
        )


def test_disk_path_missing_root_raises(tmp_path, fake_system):
    with pytest.raises(FileNotFoundError):
        DiskPath("missing", **{fake_system: tmp_path})


@pytest.mark.parametrize(
    ("system", "current", "foreign", "line", "expected"),
    [
        (
            "Linux",
            Path("/mnt"),
            {"Darwin": PurePosixPath("/Volumes")},
            "file /Volumes/project.nk",
            "file /mnt/project.nk",
        ),
        (
            "Linux",
            Path("/mnt"),
            {"Windows": PureWindowsPath("D:/")},
            'file "D:/folder/tool.nk"',
            'file "/mnt/folder/tool.nk"',
        ),
        (
            "Windows",
            PureWindowsPath("D:/"),
            {"Linux": PurePosixPath("/mnt")},
            "file /mnt/folder/tool.nk",
            "file D:/folder/tool.nk",
        ),
    ],
)
def test_localize_any_posix_rewrites_prefixes(system, current, foreign, line, expected):
    localizer = make_localizer(system, current, foreign)

    result = localizer.localize_any_posix(line)

    assert result == expected
    assert isinstance(result, str)


def test_localize_windows_drive_letter_is_case_insensitive():
    localizer = make_localizer(
        "Linux", Path("/mnt"), {"Windows": PureWindowsPath("D:/")}
    )

    assert localizer.localize_any_posix("file d:/folder") == "file /mnt/folder"


def test_localize_exact_roots_preserves_root_semantics():
    windows_localizer = make_localizer(
        "Windows", PureWindowsPath("D:/"), {"Linux": PurePosixPath("/mnt")}
    )
    root_localizer = make_localizer(
        "Linux", Path("/"), {"Darwin": PurePosixPath("/Volumes")}
    )

    assert windows_localizer.localize_any_posix('file "/mnt"') == 'file "D:/"'
    assert root_localizer.localize_any_posix("file /Volumes/tool.nk") == "file /tool.nk"


def test_localize_posix_prefix_is_case_sensitive():
    localizer = make_localizer(
        "Linux", Path("/mnt"), {"Darwin": PurePosixPath("/Volumes")}
    )

    assert localizer.localize_any_posix("file /volumes/a") == "file /volumes/a"


@pytest.mark.parametrize("line", ["file /home/mnt/x", "file /mntfoo/x"])
def test_localize_respects_prefix_boundaries(line):
    localizer = make_localizer("Linux", Path("/mnt"), {"Darwin": PurePosixPath("/mnt")})

    assert localizer.localize_any_posix(line) == line


def test_localize_prefers_longest_prefix():
    localizer = make_localizer(
        "Linux",
        Path("/mnt"),
        OrderedDict(
            [
                ("Darwin", PurePosixPath("/Volumes")),
                ("Other", PurePosixPath("/Volumes/Project")),
            ]
        ),
    )

    assert localizer.localize_any_posix("file /Volumes/Project/a") == "file /mnt/a"


def test_localize_replaces_multiple_occurrences_and_suffix_boundary():
    localizer = make_localizer(
        "Linux", Path("/mnt"), {"Darwin": PurePosixPath("/Volumes")}
    )

    assert localizer.localize_any_posix('x /Volumes/a " /Volumes') == 'x /mnt/a " /mnt'


def test_localize_replacement_is_literal_and_single_prefix_is_safe():
    localizer = make_localizer(
        "Linux", Path(r"C:\new\1"), {"Darwin": PurePosixPath("/Volumes")}
    )
    single = make_localizer("Linux", Path("/mnt"), {})

    assert localizer.localize_any_posix("file /Volumes/a") == r"file C:\new\1/a"
    assert single.localize_any_posix("file untouched") == "file untouched"


def test_localize_ignores_prefixes_equal_to_current_and_duplicate():
    localizer = make_localizer(
        "Linux",
        Path("/mnt"),
        OrderedDict(
            [
                ("Darwin", PurePosixPath("/mnt")),
                ("Other", PurePosixPath("/Volumes")),
                ("Third", PurePosixPath("/Volumes")),
            ]
        ),
    )

    assert (
        localizer.localize_any_posix("file /mnt/a /Volumes/b") == "file /mnt/a /mnt/b"
    )


def test_localize_path_object(disk_path):
    source = disk_path.system_prefix / "SharedToolSets" / "nested" / "beta.nk"

    assert disk_path.localize(source) == source


def test_discover_and_cleanup_walk_toolsets_once(tmp_path, fake_system, monkeypatch):
    root = tmp_path / "SharedToolSets"
    (root / ".hidden").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "folder.nk").mkdir()
    (root / "nested").mkdir()
    (root / "z.nk").touch()
    (root / "nested" / "a.nk").touch()
    (root / ".hidden" / "secret.nk").touch()
    (root / "tests" / "fixture.nk").touch()
    (root / "nested" / "stale.nk~").touch()
    disk_path = DiskPath("SharedToolSets", **{fake_system: tmp_path})
    walk = os.walk
    calls = []

    def counted_walk(
        top: Path,
        topdown: bool = True,
        onerror: Callable[[OSError], None] | None = None,
        followlinks: bool = False,
    ) -> Iterator[tuple[str, list[str], list[str]]]:
        calls.append(top)
        return walk(top, topdown, onerror, followlinks)

    monkeypatch.setattr("shared_toolsets.paths.os.walk", counted_walk)
    roster = disk_path.discover_paths_for_menus(exclude_paths=[root / "tests"])

    assert list(roster) == ["nested/a", "z"]
    assert not (root / "nested" / "stale.nk~").exists()
    assert len(calls) == 1


def test_clean_temp_nk_files_removes_backup_and_empty_folders(
    toolsets_dir, fake_system
):
    backup = toolsets_dir / "nested" / "remove.nk~"
    backup.touch()
    (toolsets_dir / "empty" / "nested").mkdir(parents=True)
    (toolsets_dir / "empty" / "nested" / "last.nk~").touch()

    disk_path = DiskPath("SharedToolSets", **{fake_system: toolsets_dir.parent})
    disk_path.clean_temp_nk_files()

    assert not backup.exists()
    assert not (toolsets_dir / "empty").exists()
    assert toolsets_dir.is_dir()


def test_temp_localized_writes_and_removes_temporary_copy(
    disk_path, tmp_path, monkeypatch
):
    foreign_prefix = next(
        prefix
        for prefix in disk_path.prefixes.values()
        if prefix != disk_path.system_prefix
    )
    foreign_prefix_text = foreign_prefix.as_posix().rstrip("/")
    source = disk_path.toolsets / "source.nk"
    source.write_text(f"file {foreign_prefix_text}/project.nk\n", encoding="utf-8")
    temp_root = tmp_path / "temp"
    temp_root.mkdir()

    monkeypatch.setenv("NUKE_TEMP_DIR", str(temp_root))
    with disk_path.temp_localized(source) as localized:
        temp_dir = localized.parent
        assert localized.name == source.name
        expected_path = disk_path.system_prefix / "project.nk"
        assert localized.read_text(encoding="utf-8") == f"file {expected_path}\n"
        assert localized.exists()

    assert not temp_dir.exists()


def test_temp_localized_preserves_utf8_and_crlf(disk_path):
    foreign_prefix = next(
        prefix
        for prefix in disk_path.prefixes.values()
        if prefix != disk_path.system_prefix
    )
    foreign_prefix_text = foreign_prefix.as_posix().rstrip("/")
    source = disk_path.toolsets / "utf8.nk"
    source.write_bytes(f"name café\r\nfile {foreign_prefix_text}/a\r\n".encode())

    with disk_path.temp_localized(source) as localized:
        assert localized.read_bytes() == (
            "name café\r\nfile " + disk_path.system_prefix.as_posix() + "/a\r\n"
        ).encode("utf-8")


def test_temp_localized_callback_is_throttled_and_finishes_at_one(disk_path):
    source = disk_path.toolsets / "large.nk"
    source.write_text("x\n" * 20_000, encoding="utf-8")
    percentages = []

    with disk_path.temp_localized(source, percent_callback=percentages.append):
        pass

    assert percentages == sorted(percentages)
    assert all(0 <= value <= 1 for value in percentages)
    assert percentages[-1] == 1.0
    assert len(percentages) <= 101


def test_temp_localized_cleans_up_if_body_raises(disk_path, tmp_path, monkeypatch):
    temp_root = tmp_path / "temp"
    temp_root.mkdir()
    monkeypatch.setenv("NUKE_TEMP_DIR", str(temp_root))
    source = disk_path.toolsets / "body.nk"
    source.write_text("body\n", encoding="utf-8")

    with pytest.raises(RuntimeError), disk_path.temp_localized(source):
        raise RuntimeError

    assert list(temp_root.iterdir()) == []


def test_temp_localized_cleans_up_if_progress_callback_raises(
    disk_path, tmp_path, monkeypatch
):
    temp_root = tmp_path / "temp"
    temp_root.mkdir()
    monkeypatch.setenv("NUKE_TEMP_DIR", str(temp_root))
    source = disk_path.toolsets / "callback.nk"
    source.write_text("body\n", encoding="utf-8")

    def fail_callback(_) -> None:
        failure = RuntimeError("callback failed")
        raise failure

    with (
        pytest.raises(RuntimeError, match="callback failed"),
        disk_path.temp_localized(source, percent_callback=fail_callback),
    ):
        pass

    assert list(temp_root.iterdir()) == []


def test_temp_localized_empty_file_has_clear_error(disk_path):
    source = disk_path.toolsets / "empty.nk"
    source.touch()

    with pytest.raises(ValueError, match=str(source)), disk_path.temp_localized(source):
        pass


def test_temp_localized_falls_back_for_missing_temp_root(
    disk_path, tmp_path, monkeypatch
):
    source = disk_path.toolsets / "fallback.nk"
    source.write_text("body\n", encoding="utf-8")
    missing = tmp_path / "missing-temp"
    monkeypatch.setenv("NUKE_TEMP_DIR", str(missing))

    with disk_path.temp_localized(source) as localized:
        assert localized.parent != missing
        assert localized.exists()

    assert not localized.parent.exists()


@pytest.mark.windows_only
@pytest.mark.skipif(os.name != "nt", reason="Requires Windows file sharing semantics")
def test_temp_localized_output_can_be_reopened_while_active(disk_path):
    source = disk_path.toolsets / "windows.nk"
    source.write_text("body\n", encoding="utf-8")

    with disk_path.temp_localized(source) as localized:
        assert localized.read_text(encoding="utf-8") == "body\n"
