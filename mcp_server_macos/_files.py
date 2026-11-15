"""Writing the files the tools make, without losing the one that was there when writing fails."""

import os
import shutil
import tempfile
from pathlib import Path


def write(path: str, data: bytes) -> Path:
    """
    Write ``data`` to ``path``, and return where it was written.

    The bytes go to a new file beside it, which takes the place of the old one only once it's whole: a
    full disk or another failure leaves the file that was there as it was, even when it was the tool's
    own source. A symbolic link is written through, to the file it points at, and an existing file's
    permissions are kept.
    """
    target = Path(path).expanduser().absolute()
    if target.is_symlink():
        target = target.resolve()
    handle, temporary = tempfile.mkstemp(dir=target.parent, prefix=".{}.".format(target.name), suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as written:
            written.write(data)
        if target.exists():
            shutil.copymode(target, temporary)
        else:
            os.chmod(temporary, 0o666 & ~_umask())
        os.replace(temporary, target)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return target


def _umask() -> int:
    # The only way to read it is to set it: set it back at once.
    current = os.umask(0)
    os.umask(current)
    return current
