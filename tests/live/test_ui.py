"""
The tools that read what apps show, against this Mac: read only. Nothing is pressed, typed, focused or
chosen, and the app in front stays in front.
"""

import macos
import pytest
from mcp import Client

from tests.helpers import text
from tests.live.helpers import call

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def accessibility() -> None:
    if not macos.windows.has_permission():
        pytest.skip("Accessibility isn't granted here")


async def test_what_finder_shows(client: Client) -> None:
    shown = await call(client, "get_ui_elements", {"app": "Finder", "include_text": True, "max_elements": 50})

    assert shown["app"] == "Finder" and len(shown["elements"]) <= 50
    for element in shown["elements"]:
        assert element["id"] >= 1 and element["role"] and element["width"] >= 0
    if shown["elements"]:
        first = shown["elements"][0]
        found = await call(client, "get_ui_element_at", {"x": first["x"], "y": first["y"]})
        assert found["element"] is None or found["element"]["role"]


async def test_finder_menus(client: Client) -> None:
    items = await call(client, "list_menu_items", {"app": "Finder"})

    assert items and all(" > " in item["path"] for item in items)
    assert any(item.get("shortcut", "").startswith("cmd") for item in items)
    first_menu = items[0]["path"].split(" > ")[0]
    only = await call(client, "list_menu_items", {"app": "Finder", "menu": first_menu})
    assert only and all(item["path"].startswith(first_menu + " > ") for item in only)


async def test_what_isnt_there(client: Client) -> None:
    missing_app = await client.call_tool("get_ui_elements", {"app": "zq-no-such-app-xj"})
    missing_id = await client.call_tool("read_ui_element_text", {"id": 999999999})
    waited = await call(
        client, "wait_for_ui_element", {"app": "Finder", "name": "zq-nowhere-xj", "timeout_seconds": 0.5}
    )

    assert missing_app.is_error and "AppNotFoundError" in text(missing_app)
    assert missing_id.is_error and "LookupError" in text(missing_id)
    assert waited == {"element": None}


async def test_the_focused_element(client: Client) -> None:
    found = await call(client, "get_focused_ui_element")

    assert found["element"] is None or found["element"]["role"]
