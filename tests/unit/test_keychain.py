"""The tools of mcp_server_macos.tools.keychain, with macos.keychain faked: the Keychain isn't touched."""

from typing import Any, Dict, Optional

import macos
import pytest
from mcp import Client

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio


@pytest.fixture
def keychain(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    recorder = Recorder()
    monkeypatch.setattr(macos.keychain, "accounts", recorder.function("accounts", ["alice", ""]))
    monkeypatch.setattr(macos.keychain, "get", recorder.function("get", "s3cret"))
    monkeypatch.setattr(macos.keychain, "set", recorder.function("set"))
    monkeypatch.setattr(macos.keychain, "delete", recorder.function("delete", True))
    return recorder


async def test_list_keychain_accounts(client: Client, keychain: Recorder) -> None:
    result = await client.call_tool("list_keychain_accounts", {"service": "my-app"})

    assert not result.is_error
    # An item with no account is listed as "", which the other tools take.
    assert result.structured_content == {"result": ["alice", ""]}
    assert keychain.calls == [("accounts", ("my-app",), {})]


@pytest.mark.parametrize("stored", ["s3cret", "", "pä$$ \"w\" 🔑", None])
async def test_get_keychain_password(client: Client, monkeypatch: pytest.MonkeyPatch, stored: Optional[str]) -> None:
    # None: nothing is stored, which isn't an empty password.
    recorder = Recorder()
    monkeypatch.setattr(macos.keychain, "get", recorder.function("get", stored))

    result = await client.call_tool("get_keychain_password", {"service": "my-app", "account": "alice"})

    assert not result.is_error
    assert result.structured_content == {"password": stored}
    assert recorder.calls == [("get", ("my-app", "alice"), {})]


async def test_set_keychain_password(client: Client, keychain: Recorder) -> None:
    result = await client.call_tool(
        "set_keychain_password", {"service": "my-app", "account": "alice", "password": "hunter2 $(id)"}
    )

    assert not result.is_error
    assert keychain.calls == [("set", ("my-app", "alice", "hunter2 $(id)"), {})]
    # The password isn't said back.
    assert text(result) == "Password stored for my-app (alice)."
    assert "hunter2" not in text(result)


@pytest.mark.parametrize("existed", [True, False])
async def test_delete_keychain_password(client: Client, monkeypatch: pytest.MonkeyPatch, existed: bool) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.keychain, "delete", recorder.function("delete", existed))

    result = await client.call_tool("delete_keychain_password", {"service": "my-app", "account": "alice"})

    assert not result.is_error
    assert result.structured_content == {"existed": existed}
    assert recorder.calls == [("delete", ("my-app", "alice"), {})]


async def test_account_may_be_empty(client: Client, keychain: Recorder) -> None:
    result = await client.call_tool("get_keychain_password", {"service": "my-app", "account": ""})

    assert not result.is_error
    assert keychain.calls == [("get", ("my-app", ""), {})]


@pytest.mark.parametrize(
    "error, expected",
    [
        (macos.PermissionDeniedError("the user denied access to the item"), "PermissionDeniedError: the user denied access"),
        (macos.KeychainError(-25308, "User interaction is not allowed"), "KeychainError: User interaction is not allowed"),
    ],
)
async def test_keychain_that_refuses(
    client: Client, monkeypatch: pytest.MonkeyPatch, error: Exception, expected: str
) -> None:
    monkeypatch.setattr(macos.keychain, "get", Recorder().function("get", error=error))

    result = await client.call_tool("get_keychain_password", {"service": "my-app", "account": "alice"})

    assert result.is_error
    assert expected in text(result)


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("list_keychain_accounts", {}),
        ("list_keychain_accounts", {"service": ""}),
        ("get_keychain_password", {"service": "my-app"}),
        ("get_keychain_password", {"account": "alice"}),
        ("set_keychain_password", {"service": "my-app", "account": "alice"}),
        ("set_keychain_password", {"service": "my-app", "account": "alice", "password": None}),
        ("set_keychain_password", {"service": "", "account": "alice", "password": "x"}),
        ("delete_keychain_password", {"service": "my-app"}),
    ],
)
async def test_keychain_is_not_touched_without_knowing_which_item(
    client: Client, keychain: Recorder, tool: str, arguments: Dict[str, Any]
) -> None:
    result = await client.call_tool(tool, arguments)

    assert result.is_error
    assert keychain.calls == []
