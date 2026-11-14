"""Tools for Bluetooth: its power and the paired devices, from ``macos.bluetooth``."""

from typing import Annotated, Dict, List, Optional

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from .._permissions import BLUETOOTH
from .._registry import READ_ONLY, REPLACING, add_tool

DeviceName = Annotated[
    str,
    Field(
        description="The device: its name, a part of its name that matches only one device ('AirPods'), or its "
        "address. When two devices share a name, give the address.",
        min_length=1,
    ),
]


class Device(BaseModel):
    """A Bluetooth device paired with this Mac."""

    name: str = Field(description="Its name.")
    address: str = Field(description="Its hardware address, such as 'E4:61:F4:CC:49:B2'.")
    connected: bool = Field(description="Whether it's connected now.")
    kind: str = Field(description="What it is, as macOS says: 'headphones', 'mouse', 'keyboard'...")
    battery_percent: Dict[str, int] = Field(
        description="Its battery levels in percent, when it reports them: {'main': 80}, or left, right and case "
        "for AirPods. Empty otherwise."
    )


class BluetoothStatus(BaseModel):
    """Bluetooth on this Mac."""

    power: Optional[bool] = Field(description="Whether Bluetooth is on. Null on a Mac without Bluetooth.")
    devices: List[Device] = Field(description="The devices paired with this Mac, connected ones first.")


def _device(device: "macos.bluetooth.Device") -> Device:
    return Device(
        name=device.name,
        address=device.address,
        connected=device.connected,
        kind=device.kind,
        battery_percent=dict(device.battery),
    )


def get_bluetooth_status() -> BluetoothStatus:
    """Get whether Bluetooth is on, and the devices paired with this Mac, with which are connected and their battery."""
    try:
        power: Optional[bool] = macos.bluetooth.power()
    except macos.NotSupportedError:
        return BluetoothStatus(power=None, devices=[])  # a Mac without Bluetooth
    return BluetoothStatus(power=power, devices=[_device(device) for device in macos.bluetooth.devices()])


def set_bluetooth_power(
    on: Annotated[bool, Field(description="True to turn Bluetooth on, false to turn it off.")],
) -> str:
    """
    Turn Bluetooth on or off, like the switch in Control Center. Turning it off disconnects every
    Bluetooth device: on a desktop Mac, that may be the keyboard and the mouse the user has.
    """
    macos.bluetooth.set_power(on)
    return "Bluetooth turned {}.".format("on" if on else "off")


def connect_bluetooth_device(device: DeviceName) -> Device:
    """
    Connect a paired Bluetooth device, like clicking it in the Bluetooth menu, and wait until it's
    connected, up to 10 seconds. The device must be on and in range.
    """
    return _device(macos.bluetooth.connect(device))


def disconnect_bluetooth_device(device: DeviceName) -> Device:
    """Disconnect a Bluetooth device, and wait until it's done. It stays paired."""
    return _device(macos.bluetooth.disconnect(device))


def register(server: MCPServer) -> None:
    add_tool(server, get_bluetooth_status, title="Get the Bluetooth status", annotations=READ_ONLY, permission=BLUETOOTH)
    add_tool(server, set_bluetooth_power, title="Turn Bluetooth on or off", annotations=REPLACING, permission=BLUETOOTH)
    add_tool(server, connect_bluetooth_device, title="Connect a Bluetooth device", annotations=REPLACING, permission=BLUETOOTH)
    add_tool(
        server, disconnect_bluetooth_device, title="Disconnect a Bluetooth device", annotations=REPLACING, permission=BLUETOOTH
    )
