"""The dialog tools against this Mac: three dialogs show for a second each, and close by themselves."""

import pytest
from mcp import Client

from tests.helpers import text
from tests.live.helpers import call

pytestmark = pytest.mark.anyio


async def test_dialogs_left_unanswered_close_as_if_cancelled(client: Client) -> None:
    result = await client.call_tool("show_alert", {"message": "A test of mcp-server-macos", "timeout_seconds": 1})
    assert not result.is_error, text(result)

    answer = await call(client, "ask_confirmation", {"message": "A test: leave it unanswered", "timeout_seconds": 1})
    assert answer == {"confirmed": False}

    answer = await call(client, "ask_text", {"message": "A test: leave it unanswered", "timeout_seconds": 1})
    assert answer == {"text": None}
