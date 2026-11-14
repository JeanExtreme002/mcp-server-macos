"""The system's settings that pymacos reads and changes: Finder's and the save dialog's habits, units, the menu bar."""

from typing import Annotated, Dict, List, Literal, Optional, Union

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from ..._registry import READ_ONLY, REPLACING, add_tool

ClockDate = Literal["auto", "always", "never"]


class Clock(BaseModel):
    """How the menu bar's clock shows the time."""

    seconds: bool = Field(description="Whether it shows the seconds.")
    day_of_week: bool = Field(description="Whether it shows the day of the week.")
    am_pm: bool = Field(description="Whether it shows AM or PM.")
    analog: bool = Field(description="Whether it's a clock face instead of digits.")
    date: str = Field(description="When it shows the date: 'auto' (when there's room), 'always' or 'never'.")


class MenuBar(BaseModel):
    """The menu bar's settings."""

    battery_percentage_shown: bool = Field(description="Whether the battery icon shows the percentage.")
    clock: Clock = Field(description="How the clock shows the time.")
    spacing: Optional[int] = Field(
        description="The space around each icon on the right of the menu bar, in points. Null for macOS's own."
    )
    items: Dict[str, bool] = Field(
        description="Which of Control Center's icons the menu bar shows, by name: wifi, bluetooth, sound..."
    )


class SystemSettings(BaseModel):
    """A few of the system's settings."""

    ds_store_on_network: bool = Field(description="Whether Finder writes .DS_Store files into network shares it opens.")
    ds_store_on_usb: bool = Field(
        description="Whether Finder writes .DS_Store files onto USB drives and other external disks."
    )
    keep_windows_on_quit: bool = Field(description="Whether apps reopen the windows they had when they quit.")
    save_to_icloud_by_default: bool = Field(
        description="Whether new documents are saved to iCloud Drive unless another place is chosen."
    )
    expanded_save_dialog: bool = Field(
        description="Whether the Save dialog opens expanded, with the sidebar and the folders."
    )
    measurement_units: str = Field(description="The units of measure: 'metric' or 'us' (inches, pounds, miles).")
    temperature_unit: str = Field(description="The unit of temperatures: 'celsius' or 'fahrenheit'.")
    open_photos_on_device_connect: bool = Field(
        description="Whether Photos opens by itself when an iPhone, an iPad or a camera is connected."
    )
    menu_bar: MenuBar = Field(description="The menu bar's settings.")


def get_system_settings() -> SystemSettings:
    """
    Get a few of the system's settings: whether Finder writes .DS_Store files on network shares and USB
    drives, how apps and the Save dialog open, the units of measure and temperature, whether Photos
    opens for a device, and the menu bar's clock, icons and spacing.
    """
    clock = macos.system.clock_format()
    return SystemSettings(
        ds_store_on_network=macos.system.ds_store_on_network(),
        ds_store_on_usb=macos.system.ds_store_on_usb(),
        keep_windows_on_quit=macos.system.keep_windows_on_quit(),
        save_to_icloud_by_default=macos.system.save_to_icloud_by_default(),
        expanded_save_dialog=macos.system.expanded_save_dialog(),
        measurement_units=macos.system.measurement_units(),
        temperature_unit=macos.system.temperature_unit(),
        open_photos_on_device_connect=macos.system.open_photos_on_device_connect(),
        menu_bar=MenuBar(
            battery_percentage_shown=macos.system.battery_percentage_shown(),
            clock=Clock(
                seconds=bool(clock["seconds"]),
                day_of_week=bool(clock["day_of_week"]),
                am_pm=bool(clock["am_pm"]),
                analog=bool(clock["analog"]),
                date=str(clock["date"]),
            ),
            spacing=macos.system.menu_bar_spacing(),
            items=macos.system.menu_bar_items(),
        ),
    )


def _changed(changed: List[str]) -> str:
    if not changed:
        raise ValueError("no setting was given: say which one to change")
    return "Changed: {}.".format(", ".join(changed))


def set_system_settings(
    ds_store_on_network: Annotated[
        Optional[bool],
        Field(description="Let Finder write .DS_Store files into network shares, or not. Takes effect at the next login."),
    ] = None,
    ds_store_on_usb: Annotated[
        Optional[bool],
        Field(
            description="Let Finder write .DS_Store files onto USB drives and external disks, or not. Takes effect "
            "at the next login."
        ),
    ] = None,
    keep_windows_on_quit: Annotated[
        Optional[bool],
        Field(description="True for apps to reopen their windows when opened again, false to start fresh."),
    ] = None,
    save_to_icloud_by_default: Annotated[
        Optional[bool],
        Field(
            description="True to offer iCloud Drive first when saving a new document, false for the Mac. Apps pick "
            "it up when reopened."
        ),
    ] = None,
    expanded_save_dialog: Annotated[
        Optional[bool],
        Field(
            description="True to open the Save dialog expanded, with every folder, false for the small one. Apps "
            "pick it up when reopened."
        ),
    ] = None,
    measurement_units: Annotated[
        Optional[Literal["metric", "us"]],
        Field(description="Use 'metric' or 'us' units (inches, pounds, miles). Apps pick it up when reopened."),
    ] = None,
    temperature_unit: Annotated[
        Optional[Literal["celsius", "fahrenheit"]],
        Field(description="Show temperatures in 'celsius' or 'fahrenheit'. Apps pick it up when reopened."),
    ] = None,
    open_photos_on_device_connect: Annotated[
        Optional[bool],
        Field(description="Let Photos open by itself when an iPhone, an iPad or a camera is connected, or not."),
    ] = None,
) -> str:
    """
    Change system settings: Finder's .DS_Store files, how apps and the Save dialog open, the units, and
    Photos opening for a device. Give only the settings to change: the others stay as they are. The
    menu bar has its own tool, set_menu_bar_settings.
    """
    changed: List[str] = []
    if ds_store_on_network is not None:
        macos.system.set_ds_store_on_network(ds_store_on_network)
        changed.append(".DS_Store on network shares")
    if ds_store_on_usb is not None:
        macos.system.set_ds_store_on_usb(ds_store_on_usb)
        changed.append(".DS_Store on USB drives")
    if keep_windows_on_quit is not None:
        macos.system.set_keep_windows_on_quit(keep_windows_on_quit)
        changed.append("windows kept on quit")
    if save_to_icloud_by_default is not None:
        macos.system.set_save_to_icloud_by_default(save_to_icloud_by_default)
        changed.append("saving to iCloud by default")
    if expanded_save_dialog is not None:
        macos.system.set_expanded_save_dialog(expanded_save_dialog)
        changed.append("expanded Save dialog")
    if measurement_units is not None:
        macos.system.set_measurement_units(measurement_units)
        changed.append("measurement units")
    if temperature_unit is not None:
        macos.system.set_temperature_unit(temperature_unit)
        changed.append("temperature unit")
    if open_photos_on_device_connect is not None:
        macos.system.set_open_photos_on_device_connect(open_photos_on_device_connect)
        changed.append("Photos opening for a device")
    return _changed(changed)


def set_menu_bar_settings(
    show_battery_percentage: Annotated[
        Optional[bool], Field(description="Show the battery percentage next to its icon, or not.")
    ] = None,
    clock_seconds: Annotated[Optional[bool], Field(description="Show the seconds in the clock, or not.")] = None,
    clock_day_of_week: Annotated[Optional[bool], Field(description="Show the day of the week in the clock, or not.")] = None,
    clock_am_pm: Annotated[Optional[bool], Field(description="Show AM or PM in the clock, or not.")] = None,
    clock_analog: Annotated[
        Optional[bool], Field(description="True for a clock face, false for digits.")
    ] = None,
    clock_date: Annotated[
        Optional[ClockDate],
        Field(description="When the clock shows the date: 'auto' (when there's room), 'always' or 'never'."),
    ] = None,
    spacing: Annotated[
        Union[Annotated[int, Field(ge=0, le=30)], Literal["default"], None],
        Field(
            description="The space around each icon on the right of the menu bar, in points, from 0 to 30 (macOS's "
            "own is about 16), or 'default' for macOS's own. Takes effect at the next login."
        ),
    ] = None,
    padding: Annotated[
        Optional[int],
        Field(
            description="With a spacing in points: the room around an icon when clicked, from 0 to 30. The same as "
            "the spacing by default.",
            ge=0,
            le=30,
        ),
    ] = None,
    items: Annotated[
        Optional[Dict[str, bool]],
        Field(
            description="Control Center's icons to show (true) or hide (false) in the menu bar, by name: wifi, "
            "bluetooth, sound, display, battery, focus, now_playing, screen_mirroring, stage_manager, "
            "keyboard_brightness. Those left out stay as they are."
        ),
    ] = None,
) -> str:
    """
    Change the menu bar: the battery percentage, how the clock shows the time, the space between the
    icons on the right, and which of Control Center's icons show. Give only the settings to change: the
    others stay as they are.
    """
    # Checked before anything is changed, so a wrong value doesn't leave the settings half applied.
    if padding is not None and not isinstance(spacing, int):
        raise ValueError("padding goes with a spacing in points: give both")
    if items is not None:
        unknown = [name for name in items if name not in macos.system.MENU_BAR_ITEMS]
        if unknown:
            raise ValueError(
                "items must be among {}, not {}".format(", ".join(macos.system.MENU_BAR_ITEMS), ", ".join(unknown))
            )
        if not items:
            raise ValueError("items is empty: name the icons to show or hide")

    changed: List[str] = []
    if show_battery_percentage is not None:
        macos.system.set_show_battery_percentage(show_battery_percentage)
        changed.append("battery percentage")
    if any(option is not None for option in (clock_seconds, clock_day_of_week, clock_am_pm, clock_analog, clock_date)):
        macos.system.set_clock_format(
            seconds=clock_seconds, day_of_week=clock_day_of_week, am_pm=clock_am_pm, analog=clock_analog, date=clock_date
        )
        changed.append("clock")
    if spacing is not None:
        if spacing == "default":
            macos.system.set_menu_bar_spacing(None)
        else:
            macos.system.set_menu_bar_spacing(spacing, padding=padding)
        changed.append("spacing")
    if items is not None:
        macos.system.set_menu_bar_items(**items)
        changed.append("icons")
    return _changed(changed)


def register(server: MCPServer) -> None:
    add_tool(server, get_system_settings, title="Get system settings", annotations=READ_ONLY)
    add_tool(server, set_system_settings, title="Change system settings", annotations=REPLACING)
    add_tool(server, set_menu_bar_settings, title="Change the menu bar", annotations=REPLACING)
