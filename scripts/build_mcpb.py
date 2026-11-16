"""
Build ``mcp-server-macos.mcpb``: the bundle Claude Desktop installs in one click (an MCP Bundle).

The bundle holds no code of the server. Its ``pyproject.toml`` asks for this very version from PyPI, which
Claude Desktop installs with uv, and its ``src/server.py`` starts the command. So it's built from the
version in ``mcp_server_macos/__init__.py``, once that version is on PyPI: the publish workflow builds it
after the upload, and attaches it to the release.

::

    python scripts/build_mcpb.py            # writes dist/mcp-server-macos.mcpb
    python scripts/build_mcpb.py --no-pack  # only the folder, build/mcpb, to look at

Packing needs Node, for the ``mcpb`` command (run with npx, at the version below).
"""

import argparse
import json
import pathlib
import shutil
import subprocess
import sys
from typing import Any, Dict, List

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import mcp_server_macos  # noqa: E402  (after the path: the checkout's, not an installed one)
from mcp_server_macos import tools  # noqa: E402

#: The mcpb command used to validate and pack, at a version that doesn't move under the build.
MCPB = "@anthropic-ai/mcpb@2.1.2"

NAME = "mcp-server-macos"
DESCRIPTION = "Let your AI assistant use your Mac: over 350 tools, from your apps to PDFs, the screen and settings."
LONG_DESCRIPTION = (
    "Your assistant stops explaining what to do on your Mac and starts doing it. It sees what an app shows "
    "(buttons, fields, menus) and uses it without a screenshot; works with PDFs, images, videos and documents; "
    "reads text and codes in images, offline; and controls windows, the keyboard and mouse, Wi-Fi, Bluetooth, "
    "audio, Dark Mode, the Dock, Time Machine and more.\n\n"
    "No shell and no scripts: every tool does one thing, and says whether it only reads or can change, delete "
    "or send something, so Claude asks you before those. No telemetry.\n\n"
    "macOS asks for a permission (Accessibility, Screen Recording...) the first time a tool needs one, for "
    "Claude Desktop: the tool says which, and where to allow it."
)


def _tools() -> List[Dict[str, str]]:
    """Every tool, with the first sentence of its description: what Claude Desktop lists before installing."""
    from mcp.server.mcpserver import MCPServer

    server = MCPServer(NAME)
    tools.register(server)
    listed = []
    for tool in server._tool_manager.list_tools():
        first = " ".join((tool.description or "").split()).split(". ")[0].rstrip(".")
        listed.append({"name": tool.name, "description": first + "."})
    return listed


def manifest(version: str) -> Dict[str, Any]:
    """The bundle's manifest.json, for ``version`` of the server."""
    return {
        "manifest_version": "0.4",
        "name": NAME,
        "display_name": "macOS",
        "version": version,
        "description": DESCRIPTION,
        "long_description": LONG_DESCRIPTION,
        "author": {"name": "Jean Loui Bernard Silva de Jesus", "url": "https://github.com/JeanExtreme002"},
        "repository": {"type": "git", "url": "https://github.com/JeanExtreme002/mcp-server-macos"},
        "homepage": "https://github.com/JeanExtreme002/mcp-server-macos",
        "documentation": "https://github.com/JeanExtreme002/mcp-server-macos#readme",
        "support": "https://github.com/JeanExtreme002/mcp-server-macos/issues",
        "license": "MIT",
        "keywords": ["macos", "mac", "automation", "accessibility", "pdf", "screenshots", "windows", "apps"],
        "server": {
            "type": "uv",
            "entry_point": "src/server.py",
            "mcp_config": {"command": "uv", "args": ["run", "--directory", "${__dirname}", "src/server.py"]},
        },
        # The server lists a few toolsets at first, and two tools that add the others: those two aren't below.
        "tools": _tools(),
        "tools_generated": True,
        "compatibility": {"platforms": ["darwin"], "runtimes": {"python": ">=3.10"}},
    }


def pyproject(version: str) -> str:
    """The bundle's pyproject.toml: this version of the server, from PyPI, which uv installs."""
    return (
        "[project]\n"
        'name = "mcp-server-macos-bundle"\n'
        'version = "{0}"\n'
        'description = "Starts mcp-server-macos {0}, for Claude Desktop."\n'
        'requires-python = ">=3.10"\n'
        'dependencies = ["mcp-server-macos=={0}"]\n'
    ).format(version)


SERVER = '''"""Starts mcp-server-macos, which this bundle's pyproject.toml installs."""

from mcp_server_macos.server import main

if __name__ == "__main__":
    main()
'''


def build(folder: pathlib.Path) -> None:
    """Write the bundle's files into ``folder``, emptied first."""
    version = mcp_server_macos.__version__
    shutil.rmtree(folder, ignore_errors=True)
    (folder / "src").mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps(manifest(version), indent=2, ensure_ascii=False) + "\n")
    (folder / "pyproject.toml").write_text(pyproject(version))
    (folder / "src" / "server.py").write_text(SERVER)
    shutil.copy(ROOT / "LICENSE", folder / "LICENSE")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--no-pack", action="store_true", help="only write build/mcpb, without packing it")
    arguments = parser.parse_args()

    folder = ROOT / "build" / "mcpb"
    build(folder)
    if arguments.no_pack:
        print(folder)
        return
    output = ROOT / "dist" / "{}.mcpb".format(NAME)
    output.parent.mkdir(exist_ok=True)
    subprocess.run(["npx", "--yes", MCPB, "validate", str(folder / "manifest.json")], check=True)
    subprocess.run(["npx", "--yes", MCPB, "pack", str(folder), str(output)], check=True)
    print(output)


if __name__ == "__main__":
    main()
