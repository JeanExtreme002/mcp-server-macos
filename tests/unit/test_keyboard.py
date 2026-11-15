"""The tools of mcp_server_macos.tools.keyboard, with macos.keyboard faked: no key is pressed, no setting changed."""

import contextlib
import threading
from typing import Any, Dict, Iterator, List

import macos
import pytest
from mcp import Client

from mcp_server_macos.tools import keyboard
from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio


@pytest.fixture
def mac(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    recorder = Recorder()

    @contextlib.contextmanager
    def batch() -> Iterator[None]:
        recorder.calls.append(("batch", (), {}))
        yield

    monkeypatch.setattr(macos.settings, "batch", batch)
    for name in macos.keyboard.__all__:
        if name.startswith("set_") or name in ("press", "type", "remap", "clear_remappings"):
            monkeypatch.setattr(macos.keyboard, name, recorder.function(name, "ABC" if name == "set_layout" else None))
    return recorder


async def test_get_keyboard_status(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    threads = []
    monkeypatch.setattr(macos.keyboard, "caps_lock", lambda: False)

    def layout() -> str:
        threads.append(threading.current_thread())
        return "ABC"

    monkeypatch.setattr(macos.keyboard, "layout", layout)
    monkeypatch.setattr(macos.keyboard, "layouts", lambda: ["ABC", "French"])
    monkeypatch.setattr(macos.keyboard, "brightness", lambda: 0.426)
    monkeypatch.setattr(macos.keyboard, "auto_brightness", lambda: True)
    monkeypatch.setattr(macos.keyboard, "backlight_timeout", lambda: 30.0)
    monkeypatch.setattr(macos.keyboard, "has_permission", lambda: True)
    monkeypatch.setattr(macos.keyboard, "has_listen_permission", lambda: False)

    result = await client.call_tool("get_keyboard_status", {})

    assert result.structured_content == {
        "caps_lock": False,
        "layout": "ABC",
        "layouts": ["ABC", "French"],
        "backlight": 43,
        "backlight_auto": True,
        "backlight_timeout_seconds": 30.0,
        "accessibility_permission": True,
        "input_monitoring_permission": False,
    }
    # The layouts are only read on the main thread, which macOS asks for.
    assert threads == [threading.main_thread()]


async def test_keyboard_without_a_backlight(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    def none() -> float:
        raise macos.NotSupportedError("this keyboard has no backlight")

    for name, value in (
        ("caps_lock", True),
        ("layout", "ABC"),
        ("layouts", ["ABC"]),
        ("has_permission", False),
        ("has_listen_permission", False),
    ):
        monkeypatch.setattr(macos.keyboard, name, lambda value=value: value)
    monkeypatch.setattr(macos.keyboard, "brightness", none)

    result = await client.call_tool("get_keyboard_status", {})

    assert result.structured_content is not None
    assert (result.structured_content["backlight"], result.structured_content["backlight_auto"]) == (None, None)


@pytest.mark.parametrize(
    "tool, arguments, call, said",
    [
        ("press_keys", {"keys": "cmd+shift+4"}, ("press", ("cmd+shift+4",), {"times": 1}), "Pressed cmd+shift+4."),
        ("press_keys", {"keys": "down", "times": 3}, ("press", ("down",), {"times": 3}), "Pressed down 3 times."),
        (
            "type_text",
            {"text": "Olá, mundo ✅"},
            ("type", ("Olá, mundo ✅",), {"interval": 0.0}),
            "Typed 12 characters.",
        ),
        ("set_keyboard_layout", {"name": "abc"}, ("set_layout", ("abc",), {}), "Switched to ABC."),
        (
            "remap_key",
            {"key": "caps_lock", "to": "escape"},
            ("remap", ("caps_lock", "escape"), {}),
            "caps_lock acts as escape.",
        ),
        (
            "remap_key",
            {"key": "caps_lock", "to": None},
            ("remap", ("caps_lock", None), {}),
            "caps_lock acts as itself again.",
        ),
        ("clear_key_remappings", {}, ("clear_remappings", (), {}), "Every key acts as itself again."),
        (
            "set_app_shortcut",
            {"app": "Safari", "menu_item": "Export as PDF…", "keys": "cmd+shift+e"},
            ("set_app_shortcut", ("Safari", "Export as PDF…", "cmd+shift+e"), {}),
            "Export as PDF… has cmd+shift+e.",
        ),
        (
            "set_system_shortcut",
            {"name": "spotlight", "on": False},
            ("set_system_shortcut", ("spotlight", False), {}),
            "spotlight is off.",
        ),
    ],
)
async def test_keyboard_does_as_asked(
    client: Client, mac: Recorder, tool: str, arguments: Dict[str, Any], call: Any, said: str
) -> None:
    result = await client.call_tool(tool, arguments)

    assert not result.is_error, text(result)
    assert text(result) == said
    assert mac.calls == [call]


async def test_typing_without_the_permission_asks_for_it(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(
        macos.keyboard,
        "type",
        recorder.function("type", error=macos.PermissionDeniedError("Accessibility permission is missing")),
    )
    monkeypatch.setattr(macos.keyboard, "request_permission", recorder.function("request_permission", False))

    result = await client.call_tool("type_text", {"text": "hi"})

    assert result.is_error
    assert recorder.names == ["type", "request_permission"]
    assert "System Settings › Privacy & Security › Accessibility" in text(result)


async def test_set_keyboard_backlight(client: Client, mac: Recorder) -> None:
    result = await client.call_tool("set_keyboard_backlight", {"brightness": 50, "auto": False, "timeout_seconds": 0})

    assert not result.is_error, text(result)
    # A timeout of 0 keeps it on, which pymacos says with None.
    assert mac.calls == [
        ("set_auto_brightness", (False,), {}),
        ("set_brightness", (0.5,), {}),
        ("set_backlight_timeout", (None,), {}),
    ]


async def test_set_keyboard_settings(client: Client, mac: Recorder) -> None:
    result = await client.call_tool(
        "set_keyboard_settings",
        {"key_repeat_interval_seconds": 0.03, "smart_quotes": False, "fn_key_action": "nothing"},
    )

    assert not result.is_error, text(result)
    assert mac.calls == [
        ("batch", (), {}),
        ("set_key_repeat", (0.03,), {"delay": None}),
        ("set_smart_quotes", (False,), {}),
        ("set_fn_key_action", (None,), {}),
    ]


async def test_every_keyboard_setter_is_offered(client: Client) -> None:
    (tool,) = [tool for tool in (await client.list_tools()).tools if tool.name == "set_keyboard_settings"]
    offered = set(tool.input_schema["properties"])
    others = {
        "layout",
        "brightness",
        "auto_brightness",
        "backlight_timeout",
        "app_shortcut",
        "system_shortcut",
        "key_repeat",
    }
    setters = {name[len("set_") :] for name in macos.keyboard.__all__ if name.startswith("set_")} - others

    assert setters <= offered
    assert {"key_repeat_interval_seconds", "key_repeat_delay_seconds"} <= offered


async def test_system_shortcuts_are_those_of_pymacos() -> None:
    assert set(keyboard.SystemShortcut.__args__) == set(macos.keyboard.SYSTEM_SHORTCUTS)  # type: ignore[attr-defined]


@pytest.mark.parametrize("pressed", [True, False])
async def test_wait_for_key_press(client: Client, monkeypatch: pytest.MonkeyPatch, pressed: bool) -> None:
    closed: List[bool] = []

    class Keys:
        def __iter__(self) -> Iterator[Any]:
            if pressed:
                yield macos.keyboard.KeyPress(key="k", modifiers=("cmd", "shift"), text="", code=40, repeat=False)

        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(macos.keyboard, "watch", lambda timeout: Keys())

    result = await client.call_tool("wait_for_key_press", {"timeout_seconds": 5})

    expected = {"key": "k", "modifiers": ["cmd", "shift"], "shortcut": "cmd+shift+k", "text": "", "repeat": False}
    assert result.structured_content == {"key": expected if pressed else None}
    # Listening stops with the call.
    assert closed == [True]


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("press_keys", {}),
        ("press_keys", {"keys": ""}),
        ("press_keys", {"keys": "a", "times": 0}),
        ("type_text", {"text": ""}),
        ("type_text", {"text": "a", "interval_seconds": 5}),
        ("set_keyboard_backlight", {}),
        ("set_keyboard_backlight", {"brightness": 101}),
        ("set_keyboard_settings", {}),
        ("set_keyboard_settings", {"fn_key_action": "siri"}),
        ("set_system_shortcut", {"name": "siri", "on": True}),
        ("wait_for_key_press", {"timeout_seconds": 601}),
    ],
)
async def test_keyboard_is_not_touched_without_what_it_needs(
    client: Client, mac: Recorder, monkeypatch: pytest.MonkeyPatch, tool: str, arguments: Dict[str, Any]
) -> None:
    monkeypatch.setattr(macos.keyboard, "watch", mac.function("watch", []))

    result = await client.call_tool(tool, arguments)

    assert result.is_error
    assert mac.calls == []
