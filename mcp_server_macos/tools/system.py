"""Tools about the Mac itself, from ``macos.system``."""

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from .._registry import READ_ONLY, add_tool


class SystemInfo(BaseModel):
    """What the Mac is, and how long it has been running."""

    macos_version: str = Field(description="The macOS version, e.g. '15.6.1'.")
    macos_build: str = Field(description="The macOS build number, e.g. '24G90'.")
    model: str = Field(description="The Mac's marketing name, e.g. 'MacBook Pro'.")
    model_identifier: str = Field(description="The Mac's model identifier, e.g. 'Mac14,9'.")
    processor: str = Field(description="The processor's name, e.g. 'Apple M2 Pro'.")
    memory_bytes: int = Field(description="The installed memory (RAM), in bytes.")
    computer_name: str = Field(description="The computer's name, as shown in System Settings and on the network.")
    uptime_seconds: int = Field(description="Seconds since the Mac last started, sleep time included.")


def get_system_info() -> SystemInfo:
    """
    Get information about this Mac: the macOS version and build, the model, the processor, the installed
    memory, the computer's name and how long it has been running.
    """
    return SystemInfo(
        macos_version=macos.system.version(),
        macos_build=macos.system.build(),
        model=macos.system.model(),
        model_identifier=macos.system.model_identifier(),
        processor=macos.system.processor(),
        memory_bytes=macos.system.memory(),
        computer_name=macos.system.computer_name(),
        uptime_seconds=int(macos.system.uptime().total_seconds()),
    )


def register(server: MCPServer) -> None:
    add_tool(server, get_system_info, title="Get system information", annotations=READ_ONLY)
