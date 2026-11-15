"""Writing the files the tools make, without losing the one that was there when writing fails."""

import os
import secrets
import shutil
from pathlib import Path


def write(path: str, data: bytes) -> Path:
    """
    Write ``data`` to ``path``, and return where it was written.

    The bytes go to a new file beside it, which takes the place of the old one only once it's whole: a
    full disk or another failure leaves the file that was there as it was, even when it was the tool's
    own source. A symbolic link is written through, to the file it points at, and an existing file's
    permissions are kept; a new one gets the usual ones, as the process's umask makes them.
    """
    target = Path(path).expanduser().absolute()
    if target.is_symlink():
        target = target.resolve()
    temporary = _create(target.parent)
    try:
        if target.exists():
            # While the file is still empty: a private file's bytes are never readable by others, even
            # for the moment before it takes the old one's place.
            shutil.copymode(target, temporary)
        with os.fdopen(os.open(temporary, os.O_WRONLY), "wb") as written:
            written.write(data)
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return target


def _create(folder: Path) -> Path:
    """
    A new, empty file in ``folder``, for this process alone to write.

    Its name is short and fixed but for a random part, so a destination of the longest name a disk
    takes still has room beside it. It's created exclusively, with the mode a new file gets: the kernel
    applies the umask, which is never changed here (the tools run on several threads, and the umask is
    the whole process's).
    """
    while True:
        candidate = folder / ".mcp-server-macos-{}.tmp".format(secrets.token_hex(8))
        try:
            os.close(os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666))
        except FileExistsError:
            continue
        return candidate
