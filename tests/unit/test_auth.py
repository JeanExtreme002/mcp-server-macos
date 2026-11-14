"""The tools of mcp_server_macos.tools.auth, with macos.auth faked: nobody is asked for a fingerprint."""

from typing import Any, Dict

import macos
import pytest
from mcp import Client

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("touch_id", [True, False])
async def test_check_user_authentication(client: Client, monkeypatch: pytest.MonkeyPatch, touch_id: bool) -> None:
    monkeypatch.setattr(macos.auth, "is_available", lambda *, only_touch_id=False: touch_id if only_touch_id else True)

    result = await client.call_tool("check_user_authentication", {})

    assert not result.is_error
    assert result.structured_content == {"available": True, "touch_id": touch_id}


@pytest.mark.parametrize(
    "arguments, options",
    [
        ({}, {"only_touch_id": False, "timeout": 120.0}),
        ({"only_touch_id": True, "timeout_seconds": 20}, {"only_touch_id": True, "timeout": 20.0}),
    ],
)
@pytest.mark.parametrize("confirmed", [True, False])
async def test_authenticate_user(
    client: Client, monkeypatch: pytest.MonkeyPatch, arguments: Dict[str, Any], options: Dict[str, Any], confirmed: bool
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.auth, "confirm", recorder.function("confirm", confirmed))

    result = await client.call_tool("authenticate_user", {"reason": "unlock the production credentials", **arguments})

    assert not result.is_error
    # A "no" is an answer: the prompt was shown and not confirmed.
    assert result.structured_content == {"confirmed": confirmed}
    assert recorder.calls == [("confirm", ("unlock the production credentials",), options)]


async def test_authenticate_user_where_macos_cannot_ask(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    error = macos.NotSupportedError("Touch ID isn't available on this Mac")
    monkeypatch.setattr(macos.auth, "confirm", Recorder().function("confirm", error=error))

    result = await client.call_tool("authenticate_user", {"reason": "deploy", "only_touch_id": True})

    # Not a "no": nobody was asked.
    assert result.is_error
    assert "NotSupportedError: Touch ID isn't available" in text(result)


@pytest.mark.parametrize(
    "arguments",
    [{}, {"reason": ""}, {"reason": "deploy", "timeout_seconds": 0}, {"reason": "deploy", "timeout_seconds": 601}],
)
async def test_authenticate_user_needs_a_reason(
    client: Client, monkeypatch: pytest.MonkeyPatch, arguments: Dict[str, Any]
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.auth, "confirm", recorder.function("confirm", True))

    result = await client.call_tool("authenticate_user", arguments)

    assert result.is_error
    assert recorder.calls == []
