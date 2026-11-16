"""scripts/build_mcpb.py: the bundle Claude Desktop installs, built from this version and its tools."""

import importlib.util
import json
import pathlib
from types import ModuleType

import mcp_server_macos
from mcp.server.mcpserver import MCPServer

from mcp_server_macos import tools

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "build_mcpb.py"


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_mcpb", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_bundle_is_this_version_for_macos(tmp_path: pathlib.Path) -> None:
    script = _script()

    script.build(tmp_path / "bundle")

    manifest = json.loads((tmp_path / "bundle" / "manifest.json").read_text())
    version = mcp_server_macos.__version__
    assert manifest["version"] == version
    assert manifest["server"]["type"] == "uv" and manifest["server"]["entry_point"] == "src/server.py"
    assert manifest["compatibility"]["platforms"] == ["darwin"]
    # It installs this very version from PyPI, and starts its command.
    assert 'dependencies = ["mcp-server-macos=={}"]'.format(version) in (tmp_path / "bundle" / "pyproject.toml").read_text()
    assert "from mcp_server_macos.server import main" in (tmp_path / "bundle" / "src" / "server.py").read_text()
    assert (tmp_path / "bundle" / "LICENSE").exists()


def test_the_bundle_lists_every_tool() -> None:
    server = MCPServer("all")
    tools.register(server)
    registered = {tool.name for tool in server._tool_manager.list_tools()}

    listed = _script().manifest("1.0.0")["tools"]

    assert {tool["name"] for tool in listed} == registered
    assert all(tool["description"].endswith(".") and len(tool["description"]) > 10 for tool in listed)
