"""The Mac's disks: the volumes mounted, disk images, and the disks' health."""

from typing import Annotated, List, Optional

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from ..._registry import ADDITIVE, DESTRUCTIVE, READ_ONLY, add_tool


class Volume(BaseModel):
    """A mounted volume: the startup disk, an external drive, a disk image..."""

    name: str = Field(description="Its name, as Finder shows it.")
    path: str = Field(description="Where it's mounted, such as '/Volumes/Backup' ('/' for the startup disk).")
    total_bytes: int = Field(description="Its capacity, in bytes.")
    free_bytes: int = Field(description="The space available, in bytes, as Finder shows it.")
    is_internal: bool = Field(description="Whether it's on a disk inside the Mac.")
    is_removable: bool = Field(description="Whether it's a USB stick, an SD card or other removable media.")
    is_ejectable: bool = Field(description="Whether eject_volume can unmount it.")


class DiskHealth(BaseModel):
    """A physical disk, and whether it reports it's failing."""

    device: str = Field(description="Its device name, such as 'disk0'.")
    name: str = Field(description="Its model, such as 'APPLE SSD AP0512Z'.")
    size_bytes: int = Field(description="Its size, in bytes.")
    internal: bool = Field(description="Whether it's inside the Mac.")
    solid_state: Optional[bool] = Field(description="Whether it's an SSD. Null when the disk doesn't say.")
    smart: Optional[str] = Field(
        description="Its SMART status: 'verified' (healthy) or 'failing'. Null when the disk doesn't report one, "
        "as most USB disks."
    )


class Mounted(BaseModel):
    """A disk image that was mounted."""

    mount_point: str = Field(description="Where it's mounted, such as '/Volumes/Tool': what unmount_disk_image takes.")


def list_volumes() -> List[Volume]:
    """List the volumes Finder shows, the startup disk first, with their capacity and free space."""
    return [
        Volume(
            name=volume.name,
            path=str(volume.path),
            total_bytes=volume.total,
            free_bytes=volume.free,
            is_internal=volume.is_internal,
            is_removable=volume.is_removable,
            is_ejectable=volume.is_ejectable,
        )
        for volume in macos.system.volumes()
    ]


def get_disk_health() -> List[DiskHealth]:
    """List the Mac's physical disks with their SMART status, which warns when a disk is about to fail."""
    return [
        DiskHealth(
            device=disk.device,
            name=disk.name,
            size_bytes=disk.size,
            internal=disk.internal,
            solid_state=disk.solid_state,
            smart=disk.smart,
        )
        for disk in macos.system.disk_health()
    ]


def eject_volume(
    volume: Annotated[
        str,
        Field(
            description="The volume's name ('Backup') or the path where it's mounted ('/Volumes/Backup'). When "
            "several volumes share a name, give the path.",
            min_length=1,
        ),
    ],
) -> str:
    """
    Eject a volume, like Finder's eject button. Unsaved work on it is not waited for. When the volume is
    busy, the error often names the process holding it, and find_processes_using lists them.
    """
    macos.system.eject(volume)
    return "Ejected {}.".format(volume)


def mount_disk_image(
    path: Annotated[str, Field(description="The path of the disk image: a .dmg, an .iso...", min_length=1)],
) -> Mounted:
    """
    Mount a disk image, like double-clicking it, without opening a Finder window. A license the image
    shows first is accepted. A large image is checked before it's mounted, which takes a while.
    """
    return Mounted(mount_point=str(macos.system.mount_image(path)))


def unmount_disk_image(
    mount_point: Annotated[
        str, Field(description="Where the image is mounted, such as '/Volumes/Tool'.", min_length=1)
    ],
    force: Annotated[
        bool,
        Field(description="True to unmount it even while a program has files open on it, which may lose their work."),
    ] = False,
) -> str:
    """Unmount a disk image, mounted with mount_disk_image or from Finder."""
    macos.system.unmount_image(mount_point, force=force)
    return "Unmounted {}.".format(mount_point)


def register(server: MCPServer) -> None:
    add_tool(server, list_volumes, title="List the volumes", annotations=READ_ONLY)
    add_tool(server, get_disk_health, title="Check the disks' health", annotations=READ_ONLY)
    add_tool(server, mount_disk_image, title="Mount a disk image", annotations=ADDITIVE)
    # Ejecting doesn't wait for unsaved work on the volume.
    add_tool(server, eject_volume, title="Eject a volume", annotations=DESTRUCTIVE)
    add_tool(server, unmount_disk_image, title="Unmount a disk image", annotations=DESTRUCTIVE)
