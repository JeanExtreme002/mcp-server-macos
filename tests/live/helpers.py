"""Helpers of the live tests."""

from typing import Any, Dict, Optional

from mcp import Client

from tests.helpers import text


async def call(client: Client, tool: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
    """Call a tool that should work, and return what it says: the value itself, for a list or a dictionary."""
    result = await client.call_tool(tool, arguments or {})
    assert not result.is_error, text(result)
    content = result.structured_content
    assert content is not None
    return content["result"] if set(content) == {"result"} else content
