"""The server as a client sees it: who it is, and which tools it lists."""

import re

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer

import mcp_server_macos
from mcp_server_macos import create_server
from mcp_server_macos._registry import ADDITIVE, DESTRUCTIVE, OPEN_ENDED, READ_ONLY, READ_ONLY_ONLINE, REPLACING
from tests.helpers import text

pytestmark = pytest.mark.anyio

# Every tool, by name, with what it does to the Mac. A new tool is added here, and only here (the other
# tests use this list): a client finds tools by name, so renaming or dropping one breaks whoever relies
# on it, and decides by these annotations whether to ask the user before a call, so a tool that changes
# or deletes something must never pass for one that only reads. Neither should change unnoticed.
ANNOTATIONS = {
    # appearance
    "get_appearance": READ_ONLY,
    "set_appearance": REPLACING,
    "wait_for_appearance_change": READ_ONLY,
    # apps
    "list_running_apps": READ_ONLY,
    "get_frontmost_app": READ_ONLY,
    "get_running_app": READ_ONLY,
    "list_installed_apps": READ_ONLY,
    "open_app": OPEN_ENDED,
    "activate_app": REPLACING,
    "set_app_hidden": REPLACING,
    "quit_app": DESTRUCTIVE,
    "get_default_app": READ_ONLY,
    "set_default_app": REPLACING,
    "install_app_from_disk_image": DESTRUCTIVE,
    "uninstall_app": DESTRUCTIVE,
    "list_login_items": READ_ONLY,
    "add_login_item": ADDITIVE,
    "remove_login_item": REPLACING,
    "check_quarantine": READ_ONLY,
    "remove_quarantine": DESTRUCTIVE,
    # audio
    "get_audio_status": READ_ONLY,
    "set_audio_output": OPEN_ENDED,
    "set_audio_input": REPLACING,
    "set_microphone": REPLACING,
    "get_microphone_level": READ_ONLY,
    "record_microphone": DESTRUCTIVE,
    "record_until_silence": DESTRUCTIVE,
    "get_audio_info": READ_ONLY,
    "classify_audio": READ_ONLY,
    "convert_audio": DESTRUCTIVE,
    "trim_audio": DESTRUCTIVE,
    "join_audio": DESTRUCTIVE,
    "fade_audio": DESTRUCTIVE,
    "change_audio_volume": DESTRUCTIVE,
    "reverse_audio": DESTRUCTIVE,
    "change_audio_speed": DESTRUCTIVE,
    # auth
    "check_user_authentication": READ_ONLY,
    "authenticate_user": ADDITIVE,
    # bluetooth
    "get_bluetooth_status": READ_ONLY,
    "set_bluetooth_power": REPLACING,
    "connect_bluetooth_device": REPLACING,
    "disconnect_bluetooth_device": REPLACING,
    # browser
    "list_browser_tabs": READ_ONLY,
    "get_current_tab": READ_ONLY,
    "open_in_browser": OPEN_ENDED,
    "switch_to_browser_tab": REPLACING,
    "reload_browser_tab": OPEN_ENDED,
    "navigate_browser_tab": OPEN_ENDED,
    "close_browser_tab": DESTRUCTIVE,
    "run_javascript_in_browser": OPEN_ENDED,
    # camera
    "list_cameras": READ_ONLY,
    "take_photo": READ_ONLY,
    "save_photo": REPLACING,
    "record_video": REPLACING,
    # clipboard
    "get_clipboard": READ_ONLY,
    "get_clipboard_image": READ_ONLY,
    "set_clipboard": REPLACING,
    "copy_files_to_clipboard": REPLACING,
    "copy_image_to_clipboard": REPLACING,
    "clear_clipboard": REPLACING,
    "wait_for_clipboard_change": READ_ONLY,
    # defaults
    "list_preference_keys": READ_ONLY,
    "read_preference": READ_ONLY,
    "write_preference": REPLACING,
    "delete_preference": DESTRUCTIVE,
    # dialog
    "show_alert": ADDITIVE,
    "ask_confirmation": ADDITIVE,
    "ask_text": ADDITIVE,
    "ask_choice": ADDITIVE,
    "ask_for_files": ADDITIVE,
    "ask_for_folder": ADDITIVE,
    # dock
    "get_dock_settings": READ_ONLY,
    "list_dock_items": READ_ONLY,
    "set_dock_settings": REPLACING,
    "set_hot_corner": REPLACING,
    "remove_app_from_dock": REPLACING,
    "remove_folder_from_dock": REPLACING,
    "remove_dock_spacers": REPLACING,
    "restart_dock": REPLACING,
    "add_app_to_dock": REPLACING,
    "add_folder_to_dock": REPLACING,
    "add_dock_spacer": ADDITIVE,
    # document
    "read_document_text": READ_ONLY_ONLINE,
    "convert_document": OPEN_ENDED,
    # events
    "wait_for_event": READ_ONLY,
    # finder
    "get_finder_info": READ_ONLY_ONLINE,
    "get_file_thumbnail": READ_ONLY,
    "wait_for_folder_change": READ_ONLY,
    "find_largest_files": READ_ONLY,
    "get_finder_settings": READ_ONLY,
    "get_finder_selection": READ_ONLY,
    "reveal_in_finder": ADDITIVE,
    "quick_look": ADDITIVE,
    "add_file_tags": ADDITIVE,
    "make_alias": ADDITIVE,
    "set_file_tags": REPLACING,
    "remove_file_tags": REPLACING,
    "set_file_icon": REPLACING,
    "remove_file_icon": REPLACING,
    "compress_to_zip": DESTRUCTIVE,
    "set_finder_settings": REPLACING,
    "set_desktop_view": REPLACING,
    "restart_finder": REPLACING,
    "move_to_trash": DESTRUCTIVE,
    "extract_zip": DESTRUCTIVE,
    # hotkeys
    "wait_for_shortcut": READ_ONLY,
    # image
    "get_image_info": READ_ONLY,
    "get_image_metadata": READ_ONLY,
    "get_image_colors": READ_ONLY,
    "remove_image_metadata": REPLACING,
    "set_image_date": REPLACING,
    "set_image_location": REPLACING,
    "convert_image": DESTRUCTIVE,
    "resize_image": DESTRUCTIVE,
    "crop_image": DESTRUCTIVE,
    "rotate_image": DESTRUCTIVE,
    "flip_image": DESTRUCTIVE,
    "straighten_image": DESTRUCTIVE,
    "enhance_image": DESTRUCTIVE,
    "apply_image_effect": DESTRUCTIVE,
    "blur_faces_in_image": DESTRUCTIVE,
    "blur_image_background": DESTRUCTIVE,
    "replace_image_background": DESTRUCTIVE,
    "watermark_image": DESTRUCTIVE,
    "make_contact_sheet": REPLACING,
    "make_qr_code": REPLACING,
    # keyboard
    "get_keyboard_status": READ_ONLY,
    "set_keyboard_layout": REPLACING,
    "get_keyboard_settings": READ_ONLY,
    "get_app_shortcuts": READ_ONLY,
    "press_keys": OPEN_ENDED,
    "type_text": OPEN_ENDED,
    "wait_for_key_press": READ_ONLY,
    "set_keyboard_backlight": REPLACING,
    "set_keyboard_settings": REPLACING,
    "remap_key": REPLACING,
    "clear_key_remappings": REPLACING,
    "set_app_shortcut": REPLACING,
    "set_system_shortcut": REPLACING,
    # keychain
    "list_keychain_accounts": READ_ONLY,
    "get_keychain_password": READ_ONLY,
    "set_keychain_password": REPLACING,
    "delete_keychain_password": DESTRUCTIVE,
    # language
    "detect_language": READ_ONLY,
    "analyze_sentiment": READ_ONLY,
    "compare_texts": READ_ONLY,
    "embed_text": READ_ONLY,
    "find_entities": READ_ONLY,
    "extract_keywords": READ_ONLY,
    # launch
    "open_file_or_url": OPEN_ENDED,
    # maps
    "geocode_address": READ_ONLY_ONLINE,
    "reverse_geocode": READ_ONLY_ONLINE,
    "show_in_maps": ADDITIVE,
    "show_directions_in_maps": ADDITIVE,
    # mouse
    "get_mouse_settings": READ_ONLY,
    "set_mouse_settings": REPLACING,
    "move_pointer": ADDITIVE,
    "scroll": ADDITIVE,
    "click": OPEN_ENDED,
    "drag": OPEN_ENDED,
    "click_text": OPEN_ENDED,
    "wait_for_click": READ_ONLY,
    # music
    "get_now_playing": READ_ONLY,
    "control_music": ADDITIVE,
    "set_music_volume": REPLACING,
    "seek_music": REPLACING,
    # network
    "get_network_status": READ_ONLY,
    "list_network_interfaces": READ_ONLY,
    "get_bandwidth": READ_ONLY,
    "run_speed_test": READ_ONLY_ONLINE,
    "set_wifi_power": REPLACING,
    "list_vpns": READ_ONLY,
    "connect_vpn": OPEN_ENDED,
    "disconnect_vpn": OPEN_ENDED,
    # notifications
    "send_notification": ADDITIVE,
    "check_notification_permission": READ_ONLY,
    # pdf
    "get_pdf_info": READ_ONLY,
    "read_pdf_text": READ_ONLY,
    "find_in_pdf": READ_ONLY,
    "render_pdf_page": READ_ONLY,
    "list_pdf_bookmarks": READ_ONLY,
    "list_pdf_form_fields": READ_ONLY,
    "merge_pdfs": DESTRUCTIVE,
    "extract_pdf_pages": DESTRUCTIVE,
    "rotate_pdf_pages": DESTRUCTIVE,
    "encrypt_pdf": REPLACING,
    "decrypt_pdf": REPLACING,
    "ocr_pdf": DESTRUCTIVE,
    "watermark_pdf": DESTRUCTIVE,
    "compress_pdf": DESTRUCTIVE,
    "grayscale_pdf": REPLACING,
    "images_to_pdf": REPLACING,
    "extract_pdf_images": REPLACING,
    "fill_pdf_form": REPLACING,
    "sign_pdf": DESTRUCTIVE,
    "add_text_to_pdf": DESTRUCTIVE,
    "set_pdf_bookmarks": REPLACING,
    "redact_pdf": REPLACING,
    "erase_from_pdf": DESTRUCTIVE,
    "replace_in_pdf": DESTRUCTIVE,
    # power
    "get_power_status": READ_ONLY,
    "get_sleep_blockers": READ_ONLY,
    "keep_awake": REPLACING,
    "allow_sleep": REPLACING,
    "sleep_mac": DESTRUCTIVE,
    "sleep_display": REPLACING,
    # printer
    "list_printers": READ_ONLY,
    "set_default_printer": REPLACING,
    "print_file": ADDITIVE,
    "list_print_jobs": READ_ONLY,
    "cancel_print_job": DESTRUCTIVE,
    # schedule
    "list_scheduled_jobs": READ_ONLY,
    "get_scheduled_job": READ_ONLY,
    "schedule_script": OPEN_ENDED,
    "run_scheduled_job_now": OPEN_ENDED,
    "resume_scheduled_job": OPEN_ENDED,
    "pause_scheduled_job": REPLACING,
    "remove_scheduled_job": DESTRUCTIVE,
    # screen
    "take_screenshot": READ_ONLY,
    "find_text_on_screen": READ_ONLY,
    "wait_for_text_on_screen": READ_ONLY,
    "get_screen_color": READ_ONLY,
    "get_displays": READ_ONLY,
    "get_display_modes": READ_ONLY,
    "get_display_settings": READ_ONLY,
    "get_screenshot_settings": READ_ONLY,
    "save_screenshot": REPLACING,
    "record_screen": REPLACING,
    "set_display_mode": REPLACING,
    "set_main_display": DESTRUCTIVE,
    "mirror_display": DESTRUCTIVE,
    "stop_mirroring": REPLACING,
    "set_display_brightness": REPLACING,
    "set_wallpaper": REPLACING,
    "set_display_settings": REPLACING,
    "set_screenshot_settings": REPLACING,
    "start_screensaver": REPLACING,
    "lock_screen": REPLACING,
    # settings
    "list_setting_names": READ_ONLY,
    "export_settings": READ_ONLY,
    "apply_settings": REPLACING,
    # shortcuts
    "list_shortcuts": READ_ONLY,
    "run_shortcut": OPEN_ENDED,
    # sound
    "get_sound_settings": READ_ONLY,
    "play_sound": ADDITIVE,
    "play_alert_beep": ADDITIVE,
    "set_sound_settings": REPLACING,
    # speech
    "list_voices": READ_ONLY,
    "speak": ADDITIVE,
    "save_speech": REPLACING,
    # spotlight
    "search_files": READ_ONLY,
    "search_files_by_name": READ_ONLY,
    "get_file_metadata": READ_ONLY,
    # system: what the Mac is
    "get_system_info": READ_ONLY,
    "get_security_status": READ_ONLY,
    "list_fonts": READ_ONLY,
    "list_usb_devices": READ_ONLY,
    "list_available_updates": READ_ONLY_ONLINE,
    # system: how it's doing
    "get_system_status": READ_ONLY,
    "get_gpu_usage": READ_ONLY,
    "wait_for_idle": READ_ONLY,
    "wait_for_user_activity": READ_ONLY,
    # system: disks
    "list_volumes": READ_ONLY,
    "get_disk_health": READ_ONLY,
    "mount_disk_image": ADDITIVE,
    "eject_volume": DESTRUCTIVE,
    "unmount_disk_image": DESTRUCTIVE,
    # system: processes
    "list_processes": READ_ONLY,
    "get_process": READ_ONLY,
    "list_open_files": READ_ONLY,
    "find_processes_using": READ_ONLY,
    "list_ports": READ_ONLY,
    "find_port_owner": READ_ONLY,
    "list_connections": READ_ONLY,
    "get_network_usage": READ_ONLY,
    "get_energy_usage": READ_ONLY,
    "kill_process": DESTRUCTIVE,
    # system: settings
    "get_system_settings": READ_ONLY,
    "set_system_settings": REPLACING,
    "set_menu_bar_settings": REPLACING,
    # system: diagnostics
    "list_crash_reports": READ_ONLY,
    "read_system_log": READ_ONLY,
    "list_startup_items": READ_ONLY,
    # time_machine
    "get_backup_status": READ_ONLY,
    "start_backup": ADDITIVE,
    "stop_backup": REPLACING,
    "check_backup_exclusion": READ_ONLY,
    "set_backup_exclusion": REPLACING,
    # trackpad
    "get_trackpad_settings": READ_ONLY,
    "set_trackpad_settings": REPLACING,
    # ui
    "get_ui_elements": READ_ONLY,
    "find_ui_elements": READ_ONLY,
    "wait_for_ui_element": READ_ONLY,
    "get_focused_ui_element": READ_ONLY,
    "get_ui_element_at": READ_ONLY,
    "read_ui_element_text": READ_ONLY,
    "list_menu_items": READ_ONLY,
    "focus_ui_element": ADDITIVE,
    "set_ui_element_value": REPLACING,
    "press_ui_element": OPEN_ENDED,
    "click_ui_element": OPEN_ENDED,
    "perform_ui_action": OPEN_ENDED,
    "click_menu_item": OPEN_ENDED,
    # video
    "get_video_info": READ_ONLY,
    "get_video_frame": READ_ONLY,
    "save_video_frames": REPLACING,
    "video_to_gif": REPLACING,
    "mute_video": REPLACING,
    "images_to_video": REPLACING,
    "convert_video": DESTRUCTIVE,
    "trim_video": DESTRUCTIVE,
    "join_videos": DESTRUCTIVE,
    "change_video_speed": DESTRUCTIVE,
    "rotate_video": DESTRUCTIVE,
    "crop_video": DESTRUCTIVE,
    "add_audio_to_video": DESTRUCTIVE,
    "add_video_language_track": DESTRUCTIVE,
    "reverse_video": DESTRUCTIVE,
    # vision
    "read_text_in_image": READ_ONLY,
    "find_text_lines_in_image": READ_ONLY,
    "list_text_languages": READ_ONLY,
    "find_barcodes": READ_ONLY,
    "classify_image": READ_ONLY,
    "find_faces": READ_ONLY,
    "find_animals": READ_ONLY,
    "compare_images": READ_ONLY,
    "find_duplicate_images": READ_ONLY,
    "pick_best_shot": READ_ONLY,
    "get_horizon_tilt": READ_ONLY,
    "score_image_aesthetics": READ_ONLY,
    "detect_body_poses": READ_ONLY,
    "detect_hand_poses": READ_ONLY,
    "remove_image_subject": DESTRUCTIVE,
    "scan_document_photo": DESTRUCTIVE,
    "smart_crop_image": DESTRUCTIVE,
    # volume
    "get_volume": READ_ONLY,
    "set_volume": REPLACING,
    "set_muted": REPLACING,
    # windows
    "list_windows": READ_ONLY,
    "get_front_window": READ_ONLY,
    "wait_for_window": READ_ONLY,
    "get_window_settings": READ_ONLY,
    "take_window_screenshot": READ_ONLY,
    "save_window_screenshot": REPLACING,
    "focus_window": ADDITIVE,
    "move_window": REPLACING,
    "snap_window": REPLACING,
    "set_window_state": DESTRUCTIVE,
    "tile_windows": REPLACING,
    "set_window_settings": REPLACING,
    "close_window": DESTRUCTIVE,
}

TOOLS = set(ANNOTATIONS)


async def test_server_introduces_itself(client: Client) -> None:
    info = client.server_info

    assert info is not None
    assert info.name == "mcp-server-macos"
    assert info.title == "macOS"
    assert info.version == mcp_server_macos.__version__
    assert client.instructions


async def test_tools_are_the_expected_ones(client: Client) -> None:
    listed = await client.list_tools()

    assert {tool.name for tool in listed.tools} == TOOLS
    assert len(listed.tools) == len(TOOLS), "a tool is listed twice"


async def test_tools_do_what_they_are_listed_to_do(client: Client) -> None:
    for tool in (await client.list_tools()).tools:
        assert tool.annotations == ANNOTATIONS[tool.name], tool.name


async def test_every_tool_is_described(client: Client) -> None:
    for tool in (await client.list_tools()).tools:
        assert re.fullmatch(r"[a-z][a-z0-9]*(_[a-z0-9]+)*", tool.name), "{}: not snake_case".format(tool.name)
        assert tool.title, "{}: no title".format(tool.name)
        assert tool.description and len(tool.description) > 20, "{}: no description".format(tool.name)

        # The hints a client decides with: each tool says whether it only reads, and none is left
        # for the client to assume (it would assume the worst: destructive, open to the world).
        assert tool.annotations is not None, "{}: no annotations".format(tool.name)
        assert tool.annotations.read_only_hint is not None, "{}: readOnlyHint is unset".format(tool.name)
        assert tool.annotations.open_world_hint is not None, "{}: openWorldHint is unset".format(tool.name)
        if not tool.annotations.read_only_hint:
            assert tool.annotations.destructive_hint is not None, "{}: destructiveHint is unset".format(tool.name)
            assert tool.annotations.idempotent_hint is not None, "{}: idempotentHint is unset".format(tool.name)

        for name, argument in tool.input_schema.get("properties", {}).items():
            assert argument.get("description"), "{}: the argument {} isn't described".format(tool.name, name)


async def test_unknown_tool_is_an_error(client: Client) -> None:
    result = await client.call_tool("no_such_tool", {})

    assert result.is_error
    assert "no_such_tool" in text(result)


def test_servers_are_independent() -> None:
    # Nothing is registered on a shared, module-level server: each call builds its own.
    first, second = create_server(), create_server()

    assert first is not second
    assert isinstance(first, MCPServer)
