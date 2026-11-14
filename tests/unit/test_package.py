"""The package: its version, and the command that runs the server."""

import importlib.metadata
import re
import subprocess
import sys

import pytest
from mcp.server.mcpserver import MCPServer

import mcp_server_macos
from mcp_server_macos import server


def test_version_is_the_installed_one() -> None:
    # The version is read from __init__.py when the package is built: after a bump, reinstall it
    # (pip install -e .) or this fails.
    assert importlib.metadata.version("mcp-server-macos") == mcp_server_macos.__version__


def test_version_is_semantic() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", mcp_server_macos.__version__)


def test_command_prints_its_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit:
        server.main(["--version"])

    assert exit.value.code == 0
    assert capsys.readouterr().out == "mcp-server-macos {}\n".format(mcp_server_macos.__version__)


def test_command_refuses_unknown_arguments(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit:
        server.main(["--nope"])

    assert exit.value.code == 2
    assert "--nope" in capsys.readouterr().err


def test_command_runs_the_server_over_stdio(monkeypatch: pytest.MonkeyPatch) -> None:
    transports = []
    monkeypatch.setattr(MCPServer, "run", lambda self, transport: transports.append(transport))

    server.main([])

    assert transports == ["stdio"]


def test_module_runs_as_the_command() -> None:
    done = subprocess.run(
        [sys.executable, "-m", "mcp_server_macos", "--version"], capture_output=True, text=True, timeout=60
    )

    assert done.returncode == 0, done.stderr
    assert done.stdout == "mcp-server-macos {}\n".format(mcp_server_macos.__version__)
