"""What the Mac is: its model and system, its protections, its fonts, what's plugged into it, its updates."""

from typing import Annotated, List, Optional

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from ..._registry import READ_ONLY, READ_ONLY_ONLINE, add_tool


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


class SecurityStatus(BaseModel):
    """Whether the Mac's protections are on. Null when macOS didn't say."""

    filevault: Optional[bool] = Field(description="Whether the disk is encrypted (FileVault).")
    firewall: Optional[bool] = Field(
        description="Whether the application firewall blocks unwanted incoming connections."
    )
    gatekeeper: Optional[bool] = Field(description="Whether apps are checked before they open (Gatekeeper).")
    system_integrity_protection: Optional[bool] = Field(
        description="Whether System Integrity Protection guards the system's files."
    )


class USBDevice(BaseModel):
    """A device connected over USB."""

    name: Optional[str] = Field(description="The device's name, such as 'Samsung T7'.")
    vendor: Optional[str] = Field(description="Who made it.")
    vendor_id: Optional[int] = Field(description="The USB ID of its maker.")
    product_id: Optional[int] = Field(description="The USB ID of the product.")
    serial: Optional[str] = Field(description="Its serial number.")
    speed: Optional[str] = Field(
        description="How fast it's connected: 'low', 'full' (USB 1), 'high' (USB 2), 'super' or 'super_plus' (USB 3)."
    )
    is_hub: bool = Field(description="Whether it's a hub: a device behind a slow hub runs slowly.")


class Update(BaseModel):
    """A software update macOS offers."""

    label: str = Field(description="The name the softwareupdate command takes to install it.")
    title: str = Field(description="What it is, such as 'macOS Sequoia 15.8.1'.")
    version: str = Field(description="Its version.")
    size_bytes: Optional[int] = Field(description="Its download size, in bytes.")
    recommended: bool = Field(description="Whether Apple recommends it.")
    restart: bool = Field(description="Whether installing it restarts the Mac.")


def get_security_status() -> SecurityStatus:
    """
    Check whether the Mac's protections are on: disk encryption (FileVault), the firewall, Gatekeeper
    and System Integrity Protection.
    """
    status = macos.system.security_status()
    return SecurityStatus(
        filevault=status.filevault,
        firewall=status.firewall,
        gatekeeper=status.gatekeeper,
        system_integrity_protection=status.sip,
    )


def list_fonts(
    search: Annotated[
        Optional[str],
        Field(description="Keep only the fonts whose name has this text, in any case. All of them by default."),
    ] = None,
) -> List[str]:
    """
    List the font families installed on the Mac, sorted, by the names apps show in their font menus.
    A Mac has hundreds: search for the one you need.
    """
    fonts = macos.system.fonts()
    if search is None:
        return fonts
    return [font for font in fonts if search.casefold() in font.casefold()]


def list_usb_devices() -> List[USBDevice]:
    """
    List the devices connected over USB, hubs included: name, maker, IDs and speed. Built-in keyboards
    and trackpads of recent Macs aren't USB, so they aren't listed.
    """
    return [
        USBDevice(
            name=device.name,
            vendor=device.vendor,
            vendor_id=device.vendor_id,
            product_id=device.product_id,
            serial=device.serial,
            speed=device.speed,
            is_hub=device.is_hub,
        )
        for device in macos.system.usb_devices()
    ]


def list_available_updates() -> List[Update]:
    """
    List the macOS and app updates Software Update offers. Empty when everything is up to date. It asks
    Apple's servers, which often takes 10 to 30 seconds. It doesn't install anything.
    """
    return [
        Update(
            label=update.label,
            title=update.title,
            version=update.version,
            size_bytes=update.size,
            recommended=update.recommended,
            restart=update.restart,
        )
        for update in macos.system.available_updates()
    ]


def register(server: MCPServer) -> None:
    add_tool(server, get_system_info, title="Get system information", annotations=READ_ONLY)
    add_tool(server, get_security_status, title="Check the Mac's protections", annotations=READ_ONLY)
    add_tool(server, list_fonts, title="List the installed fonts", annotations=READ_ONLY)
    add_tool(server, list_usb_devices, title="List the USB devices", annotations=READ_ONLY)
    add_tool(server, list_available_updates, title="List the software updates", annotations=READ_ONLY_ONLINE)
