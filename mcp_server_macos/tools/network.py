"""Tools for the network: the connection, Wi-Fi, VPNs and how fast data flows, from ``macos.network``."""

from typing import Annotated, List, Optional

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from .._registry import OPEN_ENDED, READ_ONLY, READ_ONLY_ONLINE, REPLACING, add_tool

VPNName = Annotated[
    str, Field(description="The VPN's name, as set up in System Settings › VPN: list_vpns lists them.", min_length=1)
]


class WiFiSignal(BaseModel):
    """How good the Wi-Fi connection is right now."""

    quality: str = Field(description="'excellent', 'good', 'fair' or 'poor', from the signal strength.")
    rssi_dbm: int = Field(description="The signal strength, in dBm: -55 and up is excellent, below -75 poor.")
    noise_dbm: int = Field(description="The background noise, in dBm: the lower, the better.")
    snr_db: int = Field(description="The signal-to-noise ratio, in dB: above 25 is good, below 15 unreliable.")
    transmit_rate_mbps: float = Field(
        description="The speed the link runs at, in megabits per second: an upper bound, not the internet's speed."
    )
    channel: Optional[int] = Field(description="The channel.")
    band: Optional[str] = Field(description="'2.4GHz', '5GHz' or '6GHz'.")
    channel_width_mhz: Optional[int] = Field(description="The channel's width, in MHz: 20, 40, 80 or 160.")
    security: Optional[str] = Field(description="The network's security, such as 'wpa2_personal'.")


class Proxies(BaseModel):
    """The proxies in use. Each is 'host:port', or null when off."""

    http: Optional[str] = Field(description="The proxy for HTTP.")
    https: Optional[str] = Field(description="The proxy for HTTPS.")
    socks: Optional[str] = Field(description="The SOCKS proxy.")
    auto_config_url: Optional[str] = Field(description="A PAC file's address, which decides the proxy for each site.")
    exceptions: List[str] = Field(description="The hosts reached without a proxy, such as '*.local'.")


class NetworkStatus(BaseModel):
    """The Mac's network connection."""

    online: bool = Field(
        description="Whether the Mac has a connection that can reach the internet, checked without contacting any "
        "server. A captive portal, like a hotel's login page, still counts as online."
    )
    interface: Optional[str] = Field(
        description="The interface internet traffic goes through, such as 'en0'. Null when offline."
    )
    ip: Optional[str] = Field(
        description="The Mac's IPv4 address on that interface: its address on the local network, or the tunnel's "
        "while a VPN carries all traffic. Null when offline."
    )
    wifi_power: Optional[bool] = Field(description="Whether Wi-Fi is turned on. Null on a Mac without Wi-Fi.")
    wifi_signal: Optional[WiFiSignal] = Field(
        description="The Wi-Fi connection's signal. Null when not connected to Wi-Fi. The network's name isn't part "
        "of it: macOS keeps it behind the Location permission."
    )
    dns_servers: List[str] = Field(description="The DNS servers the Mac asks, in order. Empty when offline.")
    proxies: Proxies = Field(description="The proxies in use.")


class NetworkInterface(BaseModel):
    """A network interface: Wi-Fi, Ethernet, a VPN tunnel..."""

    name: str = Field(description="The system's name for it, such as 'en0'.")
    display_name: Optional[str] = Field(
        description="Its name in System Settings, such as 'Wi-Fi'. Null for virtual ones, like VPN tunnels."
    )
    mac: Optional[str] = Field(description="Its hardware address, such as 'a4:83:e7:12:34:56'.")
    ipv4: List[str] = Field(description="Its IPv4 addresses.")
    ipv6: List[str] = Field(description="Its IPv6 addresses.")
    up: bool = Field(description="Whether it's turned on.")
    active: bool = Field(description="Whether it's up with an address to talk with.")


class Bandwidth(BaseModel):
    """How fast data went through a network interface, over an interval."""

    interface: str = Field(description="The system's name for it, such as 'en0'.")
    display_name: Optional[str] = Field(description="Its name in System Settings, such as 'Wi-Fi'.")
    download_mbps: float = Field(description="Megabits per second received.")
    upload_mbps: float = Field(description="Megabits per second sent.")
    received_bytes: int = Field(description="Bytes received in the interval.")
    sent_bytes: int = Field(description="Bytes sent in the interval.")


class SpeedTest(BaseModel):
    """How fast the internet connection is."""

    download_mbps: float = Field(description="The download speed, in megabits per second, as internet plans are sold.")
    upload_mbps: float = Field(description="The upload speed, in megabits per second.")
    latency_ms: Optional[float] = Field(description="The round trip to the test server when idle, in milliseconds.")
    loaded_latency_ms: Optional[float] = Field(
        description="The round trip while the connection is busy, in milliseconds: how laggy calls and games get "
        "under load."
    )
    responsiveness_rpm: Optional[float] = Field(
        description="The same under load as a score, in round trips per minute: the higher, the better."
    )
    interface: Optional[str] = Field(description="The network interface measured, such as 'en0'.")
    server: Optional[str] = Field(description="Apple's test server that answered.")


class VPN(BaseModel):
    """A VPN set up in System Settings › VPN."""

    name: str = Field(description="Its name, which connect_vpn and disconnect_vpn take.")
    kind: str = Field(description="Such as 'L2TP' or 'IPSec', or the bundle ID of the app that made it.")
    status: str = Field(description="'connected', 'connecting', 'disconnecting' or 'disconnected'.")
    id: str = Field(description="Its identifier, which stays the same when it's renamed.")


def get_network_status() -> NetworkStatus:
    """
    Get the Mac's network connection: whether it's online, the interface and address in use, whether
    Wi-Fi is on and how good its signal is, the DNS servers and the proxies.
    """
    try:
        wifi_power: Optional[bool] = macos.network.wifi_power()
    except macos.NotSupportedError:
        wifi_power = None  # a Mac without Wi-Fi
    signal = macos.network.wifi_signal()
    proxies = macos.network.proxies()
    return NetworkStatus(
        online=macos.network.is_online(),
        interface=macos.network.interface(),
        ip=macos.network.ip(),
        wifi_power=wifi_power,
        wifi_signal=None
        if signal is None
        else WiFiSignal(
            quality=signal.quality,
            rssi_dbm=signal.rssi,
            noise_dbm=signal.noise,
            snr_db=signal.snr,
            transmit_rate_mbps=signal.transmit_rate,
            channel=signal.channel,
            band=signal.band,
            channel_width_mhz=signal.channel_width,
            security=signal.security,
        ),
        dns_servers=macos.network.dns_servers(),
        proxies=Proxies(
            http=proxies.http,
            https=proxies.https,
            socks=proxies.socks,
            auto_config_url=proxies.auto_config_url,
            exceptions=list(proxies.exceptions),
        ),
    )


def list_network_interfaces() -> List[NetworkInterface]:
    """List every network interface with its addresses: Wi-Fi, Ethernet, Thunderbolt, VPN tunnels..."""
    return [
        NetworkInterface(
            name=found.name,
            display_name=found.display_name,
            mac=found.mac,
            ipv4=list(found.ipv4),
            ipv6=list(found.ipv6),
            up=found.up,
            active=found.active,
        )
        for found in macos.network.interfaces()
    ]


def get_bandwidth(
    interval_seconds: Annotated[
        float, Field(description="How long to measure for, in seconds: up to 60.", gt=0, le=60)
    ] = 1.0,
) -> List[Bandwidth]:
    """
    Measure how fast data is going through each network interface right now, the busiest first. For
    which process moves the data, see get_network_usage.
    """
    return [
        Bandwidth(
            interface=use.interface,
            display_name=use.display_name,
            download_mbps=use.download,
            upload_mbps=use.upload,
            received_bytes=use.received,
            sent_bytes=use.sent,
        )
        for use in macos.network.bandwidth(interval_seconds)
    ]


def run_speed_test(
    sequential: Annotated[
        bool,
        Field(
            description="True to measure download and upload one after the other instead of together, which reads "
            "each more exactly and takes longer."
        ),
    ] = False,
) -> SpeedTest:
    """
    Measure the internet connection's download and upload speed, and its latency, against Apple's
    servers. It takes 15 to 60 seconds and moves a few hundred megabytes: mind a metered connection.
    """
    result = macos.network.speed_test(sequential=sequential)
    return SpeedTest(
        download_mbps=result.download,
        upload_mbps=result.upload,
        latency_ms=result.latency,
        loaded_latency_ms=result.loaded_latency,
        responsiveness_rpm=result.responsiveness,
        interface=result.interface,
        server=result.server,
    )


def set_wifi_power(
    on: Annotated[bool, Field(description="True to turn Wi-Fi on, false to turn it off.")],
) -> str:
    """
    Turn Wi-Fi on or off, like the switch in Control Center. Turning it off takes a Mac that's on Wi-Fi
    offline, which cuts the connection of whatever needs the internet, an assistant that isn't running
    on this Mac included.
    """
    macos.network.set_wifi_power(on)
    return "Wi-Fi turned {}.".format("on" if on else "off")


def list_vpns() -> List[VPN]:
    """
    List the VPNs set up in System Settings, with whether each is connected. VPN apps that don't add
    theirs to System Settings aren't listed, and IKEv2 VPNs may not be either.
    """
    return [VPN(name=vpn.name, kind=vpn.kind, status=vpn.status, id=vpn.id) for vpn in macos.network.vpns()]


def connect_vpn(name: VPNName) -> str:
    """
    Connect a VPN set up in System Settings, and wait until it's connected, up to 30 seconds. It uses
    the password saved with it: a VPN that asks each time may show its prompt. Nothing to do when it's
    already connected.
    """
    macos.network.connect_vpn(name)
    return "{} is connected.".format(name)


def disconnect_vpn(name: VPNName) -> str:
    """Disconnect a VPN, and wait until it's done. Nothing to do when it isn't connected."""
    macos.network.disconnect_vpn(name)
    return "{} is disconnected.".format(name)


def register(server: MCPServer) -> None:
    add_tool(server, get_network_status, title="Get the network status", annotations=READ_ONLY)
    add_tool(server, list_network_interfaces, title="List the network interfaces", annotations=READ_ONLY)
    add_tool(server, get_bandwidth, title="Measure the bandwidth in use", annotations=READ_ONLY)
    # It talks to Apple's servers, and changes nothing on the Mac.
    add_tool(server, run_speed_test, title="Run an internet speed test", annotations=READ_ONLY_ONLINE)
    add_tool(server, set_wifi_power, title="Turn Wi-Fi on or off", annotations=REPLACING)
    add_tool(server, list_vpns, title="List the VPNs", annotations=READ_ONLY)
    # A VPN changes where all of the Mac's traffic goes, over the network: beyond this Mac, then.
    add_tool(server, connect_vpn, title="Connect a VPN", annotations=OPEN_ENDED)
    add_tool(server, disconnect_vpn, title="Disconnect a VPN", annotations=OPEN_ENDED)
