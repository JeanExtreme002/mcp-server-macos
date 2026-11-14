"""
Check what the wheel in dist/ holds: every module of the source, the py.typed marker for type checkers,
the command, the version of mcp_server_macos/__init__.py, and nothing else (no tests).

Run by the Build and the Publish workflows, after `python -m build`.
"""

import glob
import pathlib
import re
import zipfile

wheels = glob.glob("dist/*.whl")
assert len(wheels) == 1, wheels
wheel = zipfile.ZipFile(wheels[0])
names = set(wheel.namelist())

version = re.search(r'__version__ = "(.+?)"', pathlib.Path("mcp_server_macos/__init__.py").read_text()).group(1)
assert wheels[0].endswith("mcp_server_macos-{}-py3-none-any.whl".format(version)), wheels[0]

modules = {path.as_posix() for path in pathlib.Path("mcp_server_macos").rglob("*.py")}
assert modules <= names, "left out of the wheel: {}".format(sorted(modules - names))
assert "mcp_server_macos/py.typed" in names, "py.typed is missing"

extra = sorted(name for name in names if not name.startswith(("mcp_server_macos/", "mcp_server_macos-")))
assert not extra, "unexpected files in the wheel: {}".format(extra)

(entry_points,) = [name for name in names if name.endswith(".dist-info/entry_points.txt")]
assert "mcp-server-macos = mcp_server_macos.server:main" in wheel.read(entry_points).decode(), "the command is missing"

print("{}: {} files, {} modules".format(wheels[0], len(names), len(modules)))
