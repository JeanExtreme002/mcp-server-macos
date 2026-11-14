"""Helpers shared by the tests."""

from mcp.types import CallToolResult, TextContent


def text(result: CallToolResult) -> str:
    """The text of a tool's result: what a model reads of it."""
    assert all(isinstance(block, TextContent) for block in result.content), result.content
    return "\n".join(block.text for block in result.content if isinstance(block, TextContent))
