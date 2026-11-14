"""The tools of mcp_server_macos.tools.system, with macos.system faked."""

from datetime import timedelta

import macos
import pytest
from mcp import Client

from tests.helpers import text

pytestmark = pytest.mark.anyio

EXPECTED = {
    "macos_version": "15.6.1",
    "macos_build": "24G90",
    "model": "MacBook Pro",
    "model_identifier": "Mac14,9",
    "processor": "Apple M2 Pro",
    "memory_bytes": 17179869184,
    "computer_name": "Jean's MacBook Pro",
    "uptime_seconds": 93784,
}


@pytest.fixture
def system(monkeypatch: pytest.MonkeyPatch) -> None:
    """A fake Mac: what macos.system would say of it."""
    monkeypatch.setattr(macos.system, "version", lambda: "15.6.1")
    monkeypatch.setattr(macos.system, "build", lambda: "24G90")
    monkeypatch.setattr(macos.system, "model", lambda: "MacBook Pro")
    monkeypatch.setattr(macos.system, "model_identifier", lambda: "Mac14,9")
    monkeypatch.setattr(macos.system, "processor", lambda: "Apple M2 Pro")
    monkeypatch.setattr(macos.system, "memory", lambda: 17179869184)
    monkeypatch.setattr(macos.system, "computer_name", lambda: "Jean's MacBook Pro")
    monkeypatch.setattr(macos.system, "uptime", lambda: timedelta(days=1, hours=2, minutes=3, seconds=4.9))


@pytest.mark.usefixtures("system")
async def test_get_system_info(client: Client) -> None:
    result = await client.call_tool("get_system_info", {})

    assert not result.is_error
    assert result.structured_content == EXPECTED
    # The same as text, for the clients that only read text.
    assert '"macos_version": "15.6.1"' in text(result)


async def test_get_system_info_describes_its_result(client: Client) -> None:
    (tool,) = [tool for tool in (await client.list_tools()).tools if tool.name == "get_system_info"]

    assert tool.annotations is not None and tool.annotations.read_only_hint is True
    assert tool.input_schema.get("properties", {}) == {}
    assert tool.output_schema is not None
    assert set(tool.output_schema["properties"]) == set(EXPECTED)
    assert set(tool.output_schema["required"]) == set(EXPECTED)
    for name, field in tool.output_schema["properties"].items():
        assert field.get("description"), "{} isn't described".format(name)


@pytest.mark.usefixtures("system")
async def test_get_system_info_outside_macos(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    def version() -> str:
        raise macos.NotSupportedError("macos.system requires macOS")

    monkeypatch.setattr(macos.system, "version", version)

    result = await client.call_tool("get_system_info", {})

    assert result.is_error
    assert "NotSupportedError: macos.system requires macOS" in text(result)


@pytest.mark.usefixtures("system")
async def test_get_system_info_ignores_arguments_it_does_not_take(client: Client) -> None:
    # The SDK drops the arguments a tool doesn't declare: none reaches the function.
    result = await client.call_tool("get_system_info", {"verbose": True})

    assert not result.is_error
    assert result.structured_content == EXPECTED
