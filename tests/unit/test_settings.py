"""The tools of mcp_server_macos.tools.settings, with macos.settings faked: no setting is changed."""

import warnings
from typing import Any, Dict

import macos
import pytest
from mcp import Client

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio


async def test_list_setting_names(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(macos.settings, "names", lambda: ["dock.autohide", "keyboard.key_repeat"])

    result = await client.call_tool("list_setting_names", {})

    assert result.structured_content == {"result": ["dock.autohide", "keyboard.key_repeat"]}


async def test_export_settings(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    exported = {"dock": {"autohide": True, "size": 48}, "keyboard": {"key_repeat": (0.03, 0.225)}, "finder": {}}
    monkeypatch.setattr(macos.settings, "export", lambda: exported)

    result = await client.call_tool("export_settings", {})

    assert not result.is_error
    # As JSON has it, which apply_settings takes back.
    assert result.structured_content == {
        "settings": {"dock": {"autohide": True, "size": 48}, "keyboard": {"key_repeat": [0.03, 0.225]}, "finder": {}},
        "left_out": [],
    }


async def test_export_settings_says_what_it_left_out(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    # pymacos warns about a setting it can't save: the model is told, the rest is still exported.
    def export() -> Any:
        warnings.warn("screen.screenshot_folder is '~/Missing', which apply() can't set, and was left out", RuntimeWarning)
        warnings.warn("an unrelated deprecation", DeprecationWarning)
        return {"dock": {"autohide": True}}

    monkeypatch.setattr(macos.settings, "export", export)

    result = await client.call_tool("export_settings", {})

    assert not result.is_error
    assert result.structured_content == {
        "settings": {"dock": {"autohide": True}},
        "left_out": ["screen.screenshot_folder is '~/Missing', which apply() can't set, and was left out"],
    }


@pytest.mark.parametrize("changed", [["dock.autohide", "dock.size"], []])
async def test_apply_settings(client: Client, monkeypatch: pytest.MonkeyPatch, changed: Any) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.settings, "apply", recorder.function("apply", changed))
    settings = {"dock": {"autohide": True, "size": 48}, "finder": {"show_extensions": True}}

    result = await client.call_tool("apply_settings", {"settings": settings})

    assert not result.is_error
    assert result.structured_content == {"changed": changed}
    assert recorder.calls == [("apply", (settings,), {})]


async def test_apply_settings_that_pymacos_refuses(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    error = ValueError("unknown settings: dock.no_such; see macos.settings.names()")
    monkeypatch.setattr(macos.settings, "apply", Recorder().function("apply", error=error))

    result = await client.call_tool("apply_settings", {"settings": {"dock": {"no_such": 1}}})

    assert result.is_error
    assert "unknown settings: dock.no_such" in text(result)


@pytest.mark.parametrize("arguments", [{}, {"settings": []}, {"settings": {"dock": True}}, {"settings": "dock.autohide"}])
async def test_apply_settings_needs_settings_by_section(
    client: Client, monkeypatch: pytest.MonkeyPatch, arguments: Dict[str, Any]
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.settings, "apply", recorder.function("apply", []))

    result = await client.call_tool("apply_settings", arguments)

    assert result.is_error
    assert recorder.calls == []
