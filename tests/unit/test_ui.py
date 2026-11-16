"""The tools of mcp_server_macos.tools.ui, with macos.ui faked: nothing is pressed, typed or chosen."""

from typing import Any, Dict, List, Optional, Tuple

import macos
import pytest
from mcp import Client

from mcp_server_macos.tools import ui
from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio


class FakeElement:
    """An element of pymacos, as macos.ui gives it, whose methods are recorded."""

    def __init__(
        self,
        recorder: Recorder,
        role: str,
        name: Optional[str],
        *,
        subrole: Optional[str] = None,
        value: Any = None,
        frame: Optional[Tuple[int, int, int, int]] = (100, 200, 80, 24),
        checked: Optional[bool] = None,
        enabled: bool = True,
        focused: bool = False,
        selected: bool = False,
        actions: Tuple[str, ...] = ("AXPress",),
    ) -> None:
        self.role, self.subrole, self.name, self.value, self.frame = role, subrole, name, value, frame
        self.checked, self.enabled, self.focused, self.selected = checked, enabled, focused, selected
        self.actions, self.app, self.pid = list(actions), "Mail", 42
        for method in ("press", "click", "set_value", "focus", "perform"):
            setattr(self, method, self._recorded(recorder, method))
        self.text = recorder.function("text", "Dear Ada,\nThanks for the notes.")

    @property
    def center(self) -> Optional[Tuple[int, int]]:
        if self.frame is None:
            return None
        x, y, width, height = self.frame
        return (x + width // 2, y + height // 2)

    def _recorded(self, recorder: Recorder, method: str) -> Any:
        call = recorder.function(method)

        def recorded(*args: Any, **options: Any) -> None:
            call(self.name, *args, **options)

        return recorded


@pytest.fixture
def mac(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    recorder = Recorder()
    shown = [
        FakeElement(recorder, "AXButton", "Send", actions=("AXPress",)),
        FakeElement(recorder, "AXTextField", "To:", value="ada@example.com", focused=True),
        FakeElement(recorder, "AXTextField", "Search", subrole="AXSearchField", value=""),
        FakeElement(recorder, "AXCheckBox", "Remember me", value=1, checked=True),
        FakeElement(recorder, "AXPopUpButton", "Font", value="Helvetica", actions=("AXPress", "AXShowMenu")),
        FakeElement(recorder, "AXButton", "Archive", enabled=False),
        FakeElement(recorder, "AXSlider", "Volume", value=0, frame=(0, 0, 100, 20)),
    ]
    recorder.shown = shown  # type: ignore[attr-defined]

    def elements(app: Optional[str] = None, *, controls_only: bool = True) -> List[FakeElement]:
        recorder.calls.append(("elements", (app,), {"controls_only": controls_only}))
        return list(shown)

    def find(app: Optional[str] = None, *, name: Optional[str] = None, role: Optional[str] = None) -> List[Any]:
        recorder.calls.append(("find", (app,), {"name": name, "role": role}))
        return [element for element in shown if name and element.name and name.lower() in element.name.lower()]

    monkeypatch.setattr(macos.ui, "elements", elements)
    monkeypatch.setattr(macos.ui, "find", find)
    monkeypatch.setattr(macos.ui, "focused", lambda: shown[1])
    monkeypatch.setattr(macos.ui, "at", lambda x, y: shown[0] if (x, y) == (140, 212) else None)
    monkeypatch.setattr(macos.ui, "wait_for", recorder.function("wait_for", shown[0]))
    monkeypatch.setattr(macos.ui, "click_menu_item", recorder.function("click_menu_item"))
    return recorder


async def _listed(client: Client, tool: str, arguments: Dict[str, Any]) -> List[Dict[str, Any]]:
    result = await client.call_tool(tool, arguments)
    assert not result.is_error, text(result)
    assert result.structured_content is not None
    elements: List[Dict[str, Any]] = result.structured_content["elements"]
    return elements


async def test_get_ui_elements(client: Client, mac: Recorder) -> None:
    result = await client.call_tool("get_ui_elements", {"app": "Mail"})

    assert mac.calls == [("elements", ("Mail",), {"controls_only": True})]
    assert result.structured_content is not None and result.structured_content["app"] == "Mail"
    send, to, search, remember, font, archive, volume = result.structured_content["elements"]
    # What's empty is left out: the list costs the model only what each element has.
    assert send == {"id": send["id"], "role": "button", "name": "Send", "x": 140, "y": 212, "width": 80, "height": 24}
    assert to["value"] == "ada@example.com" and to["focused"] is True and to["role"] == "text field"
    assert search["role"] == "search field" and "value" not in search  # its subrole says more; no text
    assert remember["checked"] is True and "value" not in remember  # said by checked
    assert font["value"] == "Helvetica" and font["actions"] == ["AXShowMenu"]  # a press is press_ui_element's
    assert archive["disabled"] is True
    assert volume["value"] == 0 and volume["x"] == 50  # 0 is a value, and a position, not nothing
    ids = [element["id"] for element in result.structured_content["elements"]]
    assert len(set(ids)) == len(ids)


async def test_get_ui_elements_with_text_and_a_limit(client: Client, mac: Recorder) -> None:
    result = await client.call_tool("get_ui_elements", {"include_text": True, "max_elements": 2})

    assert mac.calls == [("elements", (None,), {"controls_only": False})]
    assert result.structured_content is not None
    assert len(result.structured_content["elements"]) == 2
    assert "Only the first 2 of 7" in result.structured_content["note"]


async def test_nothing_shown(client: Client, mac: Recorder) -> None:
    mac.shown.clear()  # type: ignore[attr-defined]

    result = await client.call_tool("get_ui_elements", {"app": "Game"})

    assert result.structured_content is not None
    assert result.structured_content["elements"] == [] and "take_screenshot" in result.structured_content["note"]


async def test_an_element_is_used_by_its_id(client: Client, mac: Recorder) -> None:
    send, to, *_ = await _listed(client, "get_ui_elements", {})
    font = (await _listed(client, "find_ui_elements", {"name": "font"}))[0]

    pressed = await client.call_tool("press_ui_element", {"id": send["id"]})
    clicked = await client.call_tool("click_ui_element", {"id": to["id"], "count": 2})
    typed = await client.call_tool("set_ui_element_value", {"id": to["id"], "value": "grace@example.com"})
    focused = await client.call_tool("focus_ui_element", {"id": to["id"]})
    shown = await client.call_tool("perform_ui_action", {"id": font["id"], "action": "AXShowMenu"})
    read = await client.call_tool("read_ui_element_text", {"id": to["id"]})

    assert text(pressed) == "Pressed the button 'Send'."
    assert text(clicked) == "Clicked the text field 'To:'."
    assert text(typed) == "Set the text field 'To:'."
    assert text(focused) == "Focused the text field 'To:'."
    assert text(shown) == "Did AXShowMenu on the pop up button 'Font'."
    assert text(read) == "Dear Ada,\nThanks for the notes."
    assert [call for call in mac.calls if call[0] not in ("elements", "find")] == [
        ("press", ("Send",), {}),
        ("click", ("To:",), {"button": "left", "count": 2}),
        ("set_value", ("To:", "grace@example.com"), {}),
        ("focus", ("To:",), {}),
        ("perform", ("Font", "AXShowMenu"), {}),
        ("text", (), {}),
    ]


async def test_an_id_no_element_has(client: Client, mac: Recorder) -> None:
    result = await client.call_tool("press_ui_element", {"id": 10**9})

    assert result.is_error and "LookupError: no element has the id 1000000000" in text(result)
    assert "get_ui_elements" in text(result)


async def test_the_oldest_ids_are_forgotten(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ui, "_REMEMBERED", 2)
    seen = ui._Seen()
    first, second, third = (seen.add(object()) for _ in range(3))

    assert (first, second, third) == (1, 2, 3)
    with pytest.raises(LookupError):
        seen.get(first)
    assert seen.get(third) is not None


async def test_find_ui_elements(client: Client, mac: Recorder) -> None:
    found = await _listed(client, "find_ui_elements", {"name": "send", "role": "button", "app": "Mail"})

    assert [element["name"] for element in found] == ["Send"]
    assert mac.calls == [("find", ("Mail",), {"name": "send", "role": "button"})]


async def test_wait_focused_and_at(client: Client, mac: Recorder) -> None:
    waited = await client.call_tool("wait_for_ui_element", {"name": "Send", "timeout_seconds": 5})
    focused = await client.call_tool("get_focused_ui_element", {})
    there = await client.call_tool("get_ui_element_at", {"x": 140, "y": 212})
    nothing = await client.call_tool("get_ui_element_at", {"x": 1, "y": 1})
    neither = await client.call_tool("wait_for_ui_element", {})

    assert waited.structured_content is not None and waited.structured_content["element"]["name"] == "Send"
    assert ("wait_for", (None,), {"name": "Send", "role": None, "timeout": 5.0}) in mac.calls
    assert focused.structured_content is not None and focused.structured_content["element"]["name"] == "To:"
    assert there.structured_content is not None and there.structured_content["element"]["role"] == "button"
    assert nothing.structured_content == {"element": None}
    assert neither.is_error and "give a name, a role, or both" in text(neither)


async def test_menus(client: Client, mac: Recorder, monkeypatch: pytest.MonkeyPatch) -> None:
    items = [
        macos.ui.MenuItem(("File", "Save…"), True, False, "cmd+s"),
        macos.ui.MenuItem(("File", "Export", "PDF…"), False, False, None),
        macos.ui.MenuItem(("View", "Show Sidebar"), True, True, "ctrl+cmd+s"),
    ]
    monkeypatch.setattr(macos.ui, "menu_items", lambda app=None: items)

    every = await client.call_tool("list_menu_items", {"app": "Preview"})
    view = await client.call_tool("list_menu_items", {"menu": "view"})
    missing = await client.call_tool("list_menu_items", {"menu": "Window"})
    chosen = await client.call_tool("click_menu_item", {"path": "File > Save...", "app": "Preview"})

    assert every.structured_content == {
        "result": [
            {"path": "File > Save…", "shortcut": "cmd+s"},
            {"path": "File > Export > PDF…", "disabled": True},
            {"path": "View > Show Sidebar", "shortcut": "ctrl+cmd+s", "checked": True},
        ]
    }
    assert view.structured_content == {
        "result": [{"path": "View > Show Sidebar", "shortcut": "ctrl+cmd+s", "checked": True}]
    }
    assert missing.is_error and "no menu 'Window': the menus are File, View" in text(missing)
    assert text(chosen) == "Chose File > Save...."
    assert ("click_menu_item", ("File > Save...",), {"app": "Preview"}) in mac.calls


async def test_a_missing_permission_is_told(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    def refused(app: Optional[str] = None, *, controls_only: bool = True) -> List[Any]:
        raise macos.PermissionDeniedError("Accessibility permission is missing")

    monkeypatch.setattr(macos.ui, "elements", refused)
    monkeypatch.setattr("mcp_server_macos._permissions.ask", lambda permission: False)

    result = await client.call_tool("get_ui_elements", {})

    assert result.is_error and "Accessibility" in text(result)


def test_roles_are_said_plainly() -> None:
    assert ui._spoken("AXPopUpButton") == "pop up button"
    assert ui._spoken("AXTextField") == "text field"
    assert ui._spoken("AXSearchField") == "search field"
