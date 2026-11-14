"""The tools of mcp_server_macos.tools.defaults, with macos.defaults faked."""

from datetime import datetime
from typing import Any, Dict

import macos
import pytest
from mcp import Client

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio


@pytest.fixture
def defaults(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    """The calls made to the functions of macos.defaults: nothing is read from or written to this Mac."""
    recorder = Recorder()
    monkeypatch.setattr(macos.defaults, "keys", recorder.function("keys", ["autohide", "orientation"]))
    monkeypatch.setattr(macos.defaults, "read", recorder.function("read", True))
    monkeypatch.setattr(macos.defaults, "write", recorder.function("write"))
    monkeypatch.setattr(macos.defaults, "delete", recorder.function("delete", True))
    return recorder


@pytest.mark.parametrize("arguments, current_host", [({}, False), ({"current_host": True}, True)])
async def test_list_preference_keys(
    client: Client, defaults: Recorder, arguments: Dict[str, Any], current_host: bool
) -> None:
    result = await client.call_tool("list_preference_keys", {"domain": "com.apple.dock", **arguments})

    assert not result.is_error
    assert result.structured_content == {"result": ["autohide", "orientation"]}
    assert defaults.calls == [("keys", ("com.apple.dock",), {"current_host": current_host})]


@pytest.mark.parametrize(
    "stored, value",
    [
        (True, True),
        (False, False),
        (3, 3),
        (0.5, 0.5),
        ("left", "left"),
        (None, None),  # not set
        (["a", 1, True], ["a", 1, True]),
        ({"nested": {"n": 1}}, {"nested": {"n": 1}}),
        (datetime(2026, 11, 14, 8, 0, 0), "2026-11-14T08:00:00"),
        (b"\x00\xff", "AP8="),
        ({"when": datetime(2026, 1, 1), "data": [b"hi"]}, {"when": "2026-01-01T00:00:00", "data": ["aGk="]}),
    ],
)
async def test_read_preference(client: Client, monkeypatch: pytest.MonkeyPatch, stored: Any, value: Any) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.defaults, "read", recorder.function("read", stored))

    result = await client.call_tool("read_preference", {"domain": "com.apple.dock", "key": "autohide"})

    assert not result.is_error
    assert result.structured_content == {"value": value}
    assert recorder.calls == [("read", ("com.apple.dock", "autohide"), {"current_host": False})]


async def test_read_preference_keeps_true_apart_from_one(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    # Written back as read, a boolean must stay a boolean: apps tell them apart.
    monkeypatch.setattr(macos.defaults, "read", Recorder().function("read", {"flag": True, "count": 1}))

    result = await client.call_tool("read_preference", {"domain": "com.example.app"})

    assert result.structured_content is not None
    value = result.structured_content["value"]
    assert value == {"flag": True, "count": 1}
    assert (type(value["flag"]), type(value["count"])) == (bool, int)


async def test_read_preference_of_a_whole_domain(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.defaults, "read", recorder.function("read", {"autohide": True, "tilesize": 48}))

    result = await client.call_tool("read_preference", {"domain": "NSGlobalDomain", "current_host": True})

    assert result.structured_content == {"value": {"autohide": True, "tilesize": 48}}
    assert recorder.calls == [("read", ("NSGlobalDomain", None), {"current_host": True})]


@pytest.mark.parametrize(
    "value",
    [True, False, 3, 0.5, "left", "", ["a", 1, True, ["nested"]], {"nested": {"n": 1, "on": False}}],
)
async def test_write_preference_writes_the_value_with_its_type(client: Client, defaults: Recorder, value: Any) -> None:
    result = await client.call_tool("write_preference", {"domain": "com.apple.dock", "key": "autohide", "value": value})

    assert not result.is_error, text(result)
    assert text(result) == "Set autohide in com.apple.dock."
    ((name, arguments, options),) = defaults.calls
    assert (name, options) == ("write", {"current_host": False})
    assert arguments == ("com.apple.dock", "autohide", value)
    assert type(arguments[2]) is type(value)  # true isn't written as 1, nor 3 as 3.0


async def test_write_preference_for_this_mac_only(client: Client, defaults: Recorder) -> None:
    await client.call_tool(
        "write_preference", {"domain": "NSGlobalDomain", "key": "k", "value": 1, "current_host": True}
    )

    assert defaults.calls == [("write", ("NSGlobalDomain", "k", 1), {"current_host": True})]


@pytest.mark.parametrize(
    "error, expected",
    [
        (ValueError("value must not be None; use delete() to remove a key"), "ValueError: value must not be None"),
        (ValueError("domain must be a name such as 'com.apple.dock', not a path: 'a/b'"), "not a path"),
        (macos.PermissionDeniedError("com.apple.x is managed by a configuration profile"), "PermissionDeniedError"),
    ],
)
async def test_write_preference_that_pymacos_refuses(
    client: Client, monkeypatch: pytest.MonkeyPatch, error: Exception, expected: str
) -> None:
    monkeypatch.setattr(macos.defaults, "write", Recorder().function("write", error=error))

    result = await client.call_tool("write_preference", {"domain": "com.apple.x", "key": "k", "value": None})

    assert result.is_error
    assert expected in text(result)


@pytest.mark.parametrize("was_set", [True, False])
async def test_delete_preference(client: Client, monkeypatch: pytest.MonkeyPatch, was_set: bool) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.defaults, "delete", recorder.function("delete", was_set))

    result = await client.call_tool("delete_preference", {"domain": "com.apple.dock", "key": "autohide"})

    assert not result.is_error
    assert result.structured_content == {"was_set": was_set}
    assert recorder.calls == [("delete", ("com.apple.dock", "autohide"), {"current_host": False})]


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("list_preference_keys", {}),
        ("list_preference_keys", {"domain": ""}),
        ("read_preference", {}),
        ("read_preference", {"key": "autohide"}),
        ("write_preference", {"domain": "com.apple.dock", "key": "autohide"}),
        ("write_preference", {"domain": "com.apple.dock", "value": True}),
        ("write_preference", {"domain": "", "key": "autohide", "value": True}),
        ("write_preference", {"domain": "com.apple.dock", "key": "", "value": True}),
        ("delete_preference", {"domain": "com.apple.dock"}),
        ("delete_preference", {"domain": "com.apple.dock", "key": ""}),
        ("delete_preference", {"key": "autohide"}),
    ],
)
async def test_preferences_are_not_touched_without_knowing_which(
    client: Client, defaults: Recorder, tool: str, arguments: Dict[str, Any]
) -> None:
    result = await client.call_tool(tool, arguments)

    assert result.is_error
    assert defaults.calls == []
