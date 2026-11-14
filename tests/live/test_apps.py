"""The apps tools against this Mac: Calculator is opened in the background and quit, and nothing is installed or removed."""

import subprocess
from pathlib import Path

import pytest
from mcp import Client

from tests.helpers import text
from tests.live.helpers import call

pytestmark = pytest.mark.anyio


async def test_running_apps(client: Client) -> None:
    apps = await call(client, "list_running_apps")
    everything = await call(client, "list_running_apps", {"include_background": True})

    assert len(everything) >= len(apps)
    assert all(isinstance(app["pid"], int) for app in everything)

    finder = (await call(client, "get_running_app", {"name": "finder"}))["app"]
    assert finder["bundle_id"] == "com.apple.finder"
    assert (await call(client, "get_running_app", {"name": "com.apple.finder"}))["app"]["pid"] == finder["pid"]
    assert (await call(client, "get_running_app", {"name": "no app is named like this"}))["app"] is None

    front = (await call(client, "get_frontmost_app"))["app"]
    assert front is None or front["is_active"]


async def test_app_is_opened_hidden_and_quit(client: Client) -> None:
    if (await call(client, "get_running_app", {"name": "com.apple.calculator"}))["app"] is not None:
        pytest.skip("Calculator is open: the test would quit it")

    opened = await call(client, "open_app", {"name": "com.apple.calculator", "background": True})
    try:
        assert opened["bundle_id"] == "com.apple.calculator"
        assert (await call(client, "get_running_app", {"name": "com.apple.calculator"}))["app"]["pid"] == opened["pid"]

        result = await client.call_tool("set_app_hidden", {"name": "com.apple.calculator", "hidden": True})
        assert not result.is_error, text(result)
        assert (await call(client, "get_running_app", {"name": "com.apple.calculator"}))["app"]["is_hidden"] is True
    finally:
        result = await client.call_tool("quit_app", {"name": "com.apple.calculator", "force": True})

    assert not result.is_error, text(result)
    assert (await call(client, "get_running_app", {"name": "com.apple.calculator"}))["app"] is None

    result = await client.call_tool("quit_app", {"name": "com.apple.calculator"})
    assert result.is_error
    assert "isn't running" in text(result)


async def test_app_that_does_not_exist_is_not_opened(client: Client) -> None:
    result = await client.call_tool("open_app", {"name": "no app is named like this"})

    assert result.is_error
    assert "AppNotFoundError" in text(result)


async def test_installed_apps_and_the_defaults(client: Client) -> None:
    found = await call(client, "list_installed_apps", {"search": "calculator"})
    assert "com.apple.calculator" in [app["bundle_id"] for app in found]
    assert len(await call(client, "list_installed_apps", {"limit": 3})) == 3

    assert (await call(client, "get_default_app", {"kind": "txt"}))["path"].endswith(".app")
    assert (await call(client, "get_default_app", {"kind": "no-such-extension-xyz"}))["path"] is None
    browser = (await call(client, "get_default_app", {"kind": "browser"}))["path"]
    assert browser is None or browser.endswith(".app")


async def test_app_of_macos_is_not_uninstalled(client: Client) -> None:
    result = await client.call_tool("uninstall_app", {"name": "com.apple.calculator", "dry_run": True})

    assert result.is_error
    assert "MacOSError" in text(result)


async def test_downloaded_mark_is_found_and_removed(client: Client, tmp_path: Path) -> None:
    file = tmp_path / "downloaded.txt"
    file.write_text("from the internet")
    assert await call(client, "check_quarantine", {"path": str(file)}) == {"quarantined": False}

    subprocess.run(["xattr", "-w", "com.apple.quarantine", "0081;00000000;Safari;", str(file)], check=True, timeout=30)
    assert await call(client, "check_quarantine", {"path": str(file)}) == {"quarantined": True}

    assert await call(client, "remove_quarantine", {"path": str(file)}) == {"files": 1}
    assert await call(client, "check_quarantine", {"path": str(file)}) == {"quarantined": False}
    assert await call(client, "remove_quarantine", {"path": str(file)}) == {"files": 0}

    result = await client.call_tool("check_quarantine", {"path": str(tmp_path / "nope.txt")})
    assert result.is_error
    assert "FileNotFoundError" in text(result)
