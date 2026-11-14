"""The tools of mcp_server_macos.tools.appearance, with macos.appearance faked."""

from typing import Any, Dict, List

import macos
import pytest
from mcp import Client

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio

SETTERS = ("set_mode", "set_auto_mode", "set_accent_color", "set_hide_menu_bar", "set_scroll_bars", "set_font_smoothing")


@pytest.fixture
def appearance(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    """A Mac in Dark mode, and the calls made to the functions of macos.appearance that change it."""
    recorder = Recorder()
    monkeypatch.setattr(macos.appearance, "mode", lambda: "dark")
    monkeypatch.setattr(macos.appearance, "is_auto", lambda: True)
    monkeypatch.setattr(macos.appearance, "accent_color", lambda: "#007aff")
    monkeypatch.setattr(macos.appearance, "menu_bar_hidden", lambda: False)
    monkeypatch.setattr(macos.appearance, "scroll_bars", lambda: "when_scrolling")
    monkeypatch.setattr(macos.appearance, "font_smoothing", lambda: True)
    for name in SETTERS:
        monkeypatch.setattr(macos.appearance, name, recorder.function(name))
    return recorder


async def test_get_appearance(client: Client, appearance: Recorder) -> None:
    result = await client.call_tool("get_appearance", {})

    assert not result.is_error
    assert result.structured_content == {
        "mode": "dark",
        "auto": True,
        "accent_color": "#007aff",
        "menu_bar_hidden": False,
        "scroll_bars": "when_scrolling",
        "font_smoothing": True,
    }
    assert appearance.calls == []


@pytest.mark.parametrize(
    "arguments, call, said",
    [
        ({"mode": "light"}, ("set_mode", ("light",), {}), "Changed: mode."),
        ({"auto": False}, ("set_auto_mode", (False,), {}), "Changed: auto."),
        ({"accent_color": "purple"}, ("set_accent_color", ("purple",), {}), "Changed: accent color."),
        ({"hide_menu_bar": True}, ("set_hide_menu_bar", (True,), {}), "Changed: menu bar."),
        ({"scroll_bars": "always"}, ("set_scroll_bars", ("always",), {}), "Changed: scroll bars."),
        ({"font_smoothing": False}, ("set_font_smoothing", (False,), {}), "Changed: font smoothing."),
    ],
)
async def test_set_appearance_changes_the_setting_given_and_no_other(
    client: Client, appearance: Recorder, arguments: Dict[str, Any], call: Any, said: str
) -> None:
    result = await client.call_tool("set_appearance", arguments)

    assert not result.is_error
    assert text(result) == said
    assert appearance.calls == [call]


async def test_set_appearance_changes_every_setting_given(client: Client, appearance: Recorder) -> None:
    result = await client.call_tool(
        "set_appearance",
        {
            "font_smoothing": True,
            "scroll_bars": "automatic",
            "hide_menu_bar": False,
            "accent_color": "multicolor",
            "auto": True,
            "mode": "dark",
        },
    )

    assert not result.is_error
    assert text(result) == "Changed: mode, auto, accent color, menu bar, scroll bars, font smoothing."
    # The mode first, whatever the order given: it's the one macOS may refuse.
    assert appearance.names == list(SETTERS)


async def test_set_appearance_takes_every_accent_color_of_pymacos(client: Client, appearance: Recorder) -> None:
    for name in macos.appearance.ACCENT_COLORS:
        result = await client.call_tool("set_appearance", {"accent_color": name})
        assert not result.is_error, name

    assert [arguments for _, arguments, _ in appearance.calls] == [(name,) for name in macos.appearance.ACCENT_COLORS]

    # The names the tool's description gives are the ones pymacos takes.
    (tool,) = [tool for tool in (await client.list_tools()).tools if tool.name == "set_appearance"]
    described = tool.input_schema["properties"]["accent_color"]["description"]
    for name in macos.appearance.ACCENT_COLORS:
        assert name in described, name


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"mode": None, "auto": None},
        {"accent_color": "teal"},
        {"mode": "light", "font_smoothing": True, "accent_color": "#007aff"},
        {"mode": "auto"},
        {"mode": "light", "scroll_bars": "never"},
        {"hide_menu_bar": "sometimes"},
    ],
)
async def test_set_appearance_changes_nothing_when_a_setting_is_wrong(
    client: Client, appearance: Recorder, arguments: Dict[str, Any]
) -> None:
    result = await client.call_tool("set_appearance", arguments)

    assert result.is_error
    assert "set_appearance" in text(result)
    assert appearance.calls == []


async def test_set_appearance_says_which_accent_colors_there_are(client: Client, appearance: Recorder) -> None:
    result = await client.call_tool("set_appearance", {"accent_color": "teal"})

    assert "accent_color must be one of multicolor, graphite, red" in text(result)
    assert "not 'teal'" in text(result)


async def test_set_appearance_refused_by_macos_changes_nothing(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    changed: List[str] = []

    def set_mode(mode: str) -> None:
        raise macos.PermissionDeniedError("not allowed to control System Events")

    monkeypatch.setattr(macos.appearance, "set_mode", set_mode)
    monkeypatch.setattr(macos.appearance, "set_accent_color", changed.append)

    result = await client.call_tool("set_appearance", {"accent_color": "red", "mode": "light"})

    assert result.is_error
    assert "PermissionDeniedError: not allowed to control System Events" in text(result)
    assert "System Settings › Privacy & Security › Automation" in text(result)
    assert changed == []


async def test_wait_for_appearance_change(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.appearance, "wait_for_change", recorder.function("wait_for_change", "light"))

    result = await client.call_tool("wait_for_appearance_change", {"timeout_seconds": 5})

    assert not result.is_error
    assert result.structured_content == {"mode": "light"}
    assert recorder.calls == [("wait_for_change", (), {"timeout": 5.0})]


@pytest.mark.parametrize("timeout", [0, -5, 601])
async def test_wait_for_appearance_change_does_not_wait_forever(
    client: Client, monkeypatch: pytest.MonkeyPatch, timeout: float
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.appearance, "wait_for_change", recorder.function("wait_for_change", "light"))

    result = await client.call_tool("wait_for_appearance_change", {"timeout_seconds": timeout})

    assert result.is_error
    assert recorder.calls == []


async def test_wait_for_appearance_change_when_nothing_switches(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    error = macos.WaitTimeoutError("the appearance didn't change within 60 seconds")
    monkeypatch.setattr(macos.appearance, "wait_for_change", Recorder().function("wait_for_change", error=error))

    result = await client.call_tool("wait_for_appearance_change", {})

    assert result.is_error
    assert "WaitTimeoutError" in text(result)
