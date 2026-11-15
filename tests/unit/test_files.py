"""Writing the files the tools make: whole, or not at all."""

import os
from pathlib import Path

import pytest

from mcp_server_macos import _files


def test_file_is_written(tmp_path: Path) -> None:
    written = _files.write(str(tmp_path / "new.png"), b"picture")

    assert written == tmp_path / "new.png"
    assert written.read_bytes() == b"picture"
    assert [path.name for path in tmp_path.iterdir()] == ["new.png"]  # no temporary file left


def test_file_is_replaced_with_its_permissions_kept(tmp_path: Path) -> None:
    existing = tmp_path / "photo.png"
    existing.write_bytes(b"old")
    existing.chmod(0o600)

    _files.write(str(existing), b"new")

    assert existing.read_bytes() == b"new"
    assert existing.stat().st_mode & 0o777 == 0o600


def test_link_is_written_through(tmp_path: Path) -> None:
    target = tmp_path / "real.png"
    target.write_bytes(b"old")
    link = tmp_path / "link.png"
    link.symlink_to(target)

    written = _files.write(str(link), b"new")

    assert link.is_symlink()
    assert target.read_bytes() == b"new"
    assert written == target.resolve()


def test_failure_leaves_the_file_that_was_there(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A disk that fills while writing: the source, which may be the output, stays whole.
    existing = tmp_path / "photo.png"
    existing.write_bytes(b"the original")

    def full(source: str, target: object) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "replace", full)

    with pytest.raises(OSError):
        _files.write(str(existing), b"half a pict")

    assert existing.read_bytes() == b"the original"
    assert [path.name for path in tmp_path.iterdir()] == ["photo.png"]


def test_new_file_gets_the_usual_permissions(tmp_path: Path) -> None:
    mask = os.umask(0o022)
    try:
        written = _files.write(str(tmp_path / "new.png"), b"x")
    finally:
        os.umask(mask)

    assert written.stat().st_mode & 0o777 == 0o644
