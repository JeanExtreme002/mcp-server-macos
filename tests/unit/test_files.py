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


def test_longest_name_a_disk_takes_is_written(tmp_path: Path) -> None:
    # The temporary file's name doesn't grow with the destination's: 255 characters still fit.
    longest = "x" * 251 + ".png"

    written = _files.write(str(tmp_path / longest), b"picture")

    assert written.name == longest
    assert written.read_bytes() == b"picture"


def test_umask_of_the_process_is_never_changed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The tools run on several threads: a umask changed for a moment would apply to them all.
    def changed(mask: int) -> int:
        raise AssertionError("the umask was changed")

    monkeypatch.setattr(os, "umask", changed)

    _files.write(str(tmp_path / "new.png"), b"x")
    _files.write(str(tmp_path / "new.png"), b"y")


def test_private_file_is_never_readable_by_others_while_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Whatever the umask gives a new file, the bytes of a 0600 file only ever sit in a 0600 file.
    existing = tmp_path / "private.png"
    existing.write_bytes(b"old")
    existing.chmod(0o600)
    modes = []
    opened = os.fdopen

    def watch(descriptor: int, *args: object, **options: object) -> object:
        modes.append(os.fstat(descriptor).st_mode & 0o777)
        return opened(descriptor, *args, **options)  # type: ignore[call-overload]

    monkeypatch.setattr(os, "fdopen", watch)
    mask = os.umask(0o022)
    try:
        _files.write(str(existing), b"secret")
    finally:
        os.umask(mask)

    assert modes == [0o600]
    assert existing.stat().st_mode & 0o777 == 0o600
