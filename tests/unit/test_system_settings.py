"""The tools of mcp_server_macos.tools.system.settings, with macos.system faked."""

from typing import Any, Dict, List

import macos
import pytest
from mcp import Client

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio

SETTERS = (
    "set_ds_store_on_network",
    "set_ds_store_on_usb",
    "set_keep_windows_on_quit",
    "set_save_to_icloud_by_default",
    "set_expanded_save_dialog",
    "set_measurement_units",
    "set_temperature_unit",
    "set_open_photos_on_device_connect",
    "set_show_battery_percentage",
    "set_clock_format",
    "set_menu_bar_spacing",
    "set_menu_bar_items",
)


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    """A Mac's settings, and the calls made to the functions of macos.system that change them."""
    recorder = Recorder()
    monkeypatch.setattr(macos.system, "ds_store_on_network", lambda: True)
    monkeypatch.setattr(macos.system, "ds_store_on_usb", lambda: False)
    monkeypatch.setattr(macos.system, "keep_windows_on_quit", lambda: False)
    monkeypatch.setattr(macos.system, "save_to_icloud_by_default", lambda: True)
    monkeypatch.setattr(macos.system, "expanded_save_dialog", lambda: False)
    monkeypatch.setattr(macos.system, "measurement_units", lambda: "metric")
    monkeypatch.setattr(macos.system, "temperature_unit", lambda: "celsius")
    monkeypatch.setattr(macos.system, "open_photos_on_device_connect", lambda: True)
    monkeypatch.setattr(macos.system, "battery_percentage_shown", lambda: True)
    monkeypatch.setattr(
        macos.system,
        "clock_format",
        lambda: {"seconds": False, "day_of_week": True, "am_pm": True, "analog": False, "date": "auto"},
    )
    monkeypatch.setattr(macos.system, "menu_bar_spacing", lambda: None)
    monkeypatch.setattr(macos.system, "menu_bar_items", lambda: {"wifi": True, "bluetooth": False})
    for name in SETTERS:
        monkeypatch.setattr(macos.system, name, recorder.function(name))
    return recorder


async def test_get_system_settings(client: Client, settings: Recorder) -> None:
    result = await client.call_tool("get_system_settings", {})

    assert not result.is_error
    assert result.structured_content == {
        "ds_store_on_network": True,
        "ds_store_on_usb": False,
        "keep_windows_on_quit": False,
        "save_to_icloud_by_default": True,
        "expanded_save_dialog": False,
        "measurement_units": "metric",
        "temperature_unit": "celsius",
        "open_photos_on_device_connect": True,
        "menu_bar": {
            "battery_percentage_shown": True,
            "clock": {"seconds": False, "day_of_week": True, "am_pm": True, "analog": False, "date": "auto"},
            "spacing": None,
            "items": {"wifi": True, "bluetooth": False},
        },
    }
    assert settings.calls == []


@pytest.mark.parametrize(
    "arguments, call, said",
    [
        ({"ds_store_on_network": False}, ("set_ds_store_on_network", (False,), {}), ".DS_Store on network shares"),
        ({"ds_store_on_usb": False}, ("set_ds_store_on_usb", (False,), {}), ".DS_Store on USB drives"),
        ({"keep_windows_on_quit": True}, ("set_keep_windows_on_quit", (True,), {}), "windows kept on quit"),
        (
            {"save_to_icloud_by_default": False},
            ("set_save_to_icloud_by_default", (False,), {}),
            "saving to iCloud by default",
        ),
        ({"expanded_save_dialog": True}, ("set_expanded_save_dialog", (True,), {}), "expanded Save dialog"),
        ({"measurement_units": "us"}, ("set_measurement_units", ("us",), {}), "measurement units"),
        ({"temperature_unit": "fahrenheit"}, ("set_temperature_unit", ("fahrenheit",), {}), "temperature unit"),
        (
            {"open_photos_on_device_connect": False},
            ("set_open_photos_on_device_connect", (False,), {}),
            "Photos opening for a device",
        ),
    ],
)
async def test_set_system_settings_changes_the_setting_given_and_no_other(
    client: Client, settings: Recorder, arguments: Dict[str, Any], call: Any, said: str
) -> None:
    result = await client.call_tool("set_system_settings", arguments)

    assert not result.is_error
    assert text(result) == "Changed: {}.".format(said)
    assert settings.calls == [call]


async def test_set_system_settings_changes_every_setting_given(client: Client, settings: Recorder) -> None:
    result = await client.call_tool(
        "set_system_settings",
        {
            "open_photos_on_device_connect": True,
            "temperature_unit": "celsius",
            "measurement_units": "metric",
            "expanded_save_dialog": False,
            "save_to_icloud_by_default": True,
            "keep_windows_on_quit": False,
            "ds_store_on_usb": True,
            "ds_store_on_network": True,
        },
    )

    assert not result.is_error
    assert settings.names == list(SETTERS[:8])


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"ds_store_on_usb": None},
        {"measurement_units": "imperial"},
        {"temperature_unit": "kelvin", "ds_store_on_usb": False},
        {"keep_windows_on_quit": "sometimes"},
    ],
)
async def test_set_system_settings_changes_nothing_when_a_setting_is_wrong(
    client: Client, settings: Recorder, arguments: Dict[str, Any]
) -> None:
    result = await client.call_tool("set_system_settings", arguments)

    assert result.is_error
    assert settings.calls == []


@pytest.mark.parametrize(
    "arguments, calls, said",
    [
        ({"show_battery_percentage": False}, [("set_show_battery_percentage", (False,), {})], "battery percentage"),
        (
            {"clock_seconds": True},
            [
                (
                    "set_clock_format",
                    (),
                    {"seconds": True, "day_of_week": None, "am_pm": None, "analog": None, "date": None},
                )
            ],
            "clock",
        ),
        (
            {"clock_analog": False, "clock_date": "always", "clock_am_pm": True, "clock_day_of_week": False},
            [
                (
                    "set_clock_format",
                    (),
                    {"seconds": None, "day_of_week": False, "am_pm": True, "analog": False, "date": "always"},
                )
            ],
            "clock",
        ),
        ({"spacing": 6}, [("set_menu_bar_spacing", (6,), {"padding": None})], "spacing"),
        ({"spacing": 0, "padding": 30}, [("set_menu_bar_spacing", (0,), {"padding": 30})], "spacing"),
        ({"spacing": "default"}, [("set_menu_bar_spacing", (None,), {})], "spacing"),
        (
            {"items": {"bluetooth": True, "now_playing": False}},
            [("set_menu_bar_items", (), {"bluetooth": True, "now_playing": False})],
            "icons",
        ),
    ],
)
async def test_set_menu_bar_settings(
    client: Client, settings: Recorder, arguments: Dict[str, Any], calls: List[Any], said: str
) -> None:
    result = await client.call_tool("set_menu_bar_settings", arguments)

    assert not result.is_error, text(result)
    assert text(result) == "Changed: {}.".format(said)
    assert settings.calls == calls


async def test_set_menu_bar_settings_changes_every_setting_given(client: Client, settings: Recorder) -> None:
    result = await client.call_tool(
        "set_menu_bar_settings",
        {"items": {"wifi": False}, "spacing": 8, "clock_seconds": False, "show_battery_percentage": True},
    )

    assert text(result) == "Changed: battery percentage, clock, spacing, icons."
    assert settings.names == list(SETTERS[8:])


async def test_set_menu_bar_settings_takes_every_icon_of_pymacos(client: Client, settings: Recorder) -> None:
    everything = {name: True for name in macos.system.MENU_BAR_ITEMS}

    result = await client.call_tool("set_menu_bar_settings", {"items": everything})

    assert not result.is_error
    assert settings.calls == [("set_menu_bar_items", (), everything)]

    # The names the tool's description gives are the ones pymacos takes.
    (tool,) = [tool for tool in (await client.list_tools()).tools if tool.name == "set_menu_bar_settings"]
    for name in macos.system.MENU_BAR_ITEMS:
        assert name in tool.input_schema["properties"]["items"]["description"], name


@pytest.mark.parametrize(
    "arguments, why",
    [
        ({}, "no setting was given"),
        ({"padding": 4}, "padding goes with a spacing in points"),
        ({"spacing": "default", "padding": 4}, "padding goes with a spacing in points"),
        ({"items": {"wifi": True, "airdrop": True}, "clock_seconds": True}, "not airdrop"),
        ({"items": {}}, "items is empty"),
        ({"spacing": 31}, "set_menu_bar_settings"),
        ({"spacing": -1}, "set_menu_bar_settings"),
        ({"spacing": "wide"}, "set_menu_bar_settings"),
        ({"spacing": 6, "padding": 99}, "set_menu_bar_settings"),
        ({"clock_date": "sometimes", "show_battery_percentage": True}, "set_menu_bar_settings"),
        ({"items": {"wifi": "yes please"}}, "set_menu_bar_settings"),
    ],
)
async def test_set_menu_bar_settings_changes_nothing_when_a_setting_is_wrong(
    client: Client, settings: Recorder, arguments: Dict[str, Any], why: str
) -> None:
    result = await client.call_tool("set_menu_bar_settings", arguments)

    assert result.is_error
    assert why in text(result)
    assert settings.calls == []
