"""
Tools to see and use what an app shows (its buttons, text fields, links, checkboxes and menus) without a
screenshot, through the Accessibility tree, from ``macos.ui``.
"""

import threading
from collections import OrderedDict
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field, model_serializer

from .._permissions import ACCESSIBILITY
from .._registry import ADDITIVE, LONGEST_WAIT, OPEN_ENDED, READ_ONLY, REPLACING, add_tool

App = Annotated[
    Optional[str],
    Field(description="The app, by name, bundle identifier or path. The one in front by default."),
]
ElementId = Annotated[
    int,
    Field(description="The element's id, from get_ui_elements or find_ui_elements.", ge=1),
]

#: How many elements the ids reach back to: the oldest are forgotten, as the app has changed since anyway.
_REMEMBERED = 5000


class _Seen:
    """The elements given to the model, by the id it was told: an id is never given twice in a server's life."""

    def __init__(self) -> None:
        self._elements: "OrderedDict[int, Any]" = OrderedDict()
        self._next = 1
        self._lock = threading.Lock()

    def add(self, element: Any) -> int:
        with self._lock:
            number, self._next = self._next, self._next + 1
            self._elements[number] = element
            while len(self._elements) > _REMEMBERED:
                self._elements.popitem(last=False)
            return number

    def get(self, number: int) -> Any:
        with self._lock:
            element = self._elements.get(number)
        if element is None:
            raise LookupError(
                "no element has the id {}: it's from before the server started, or long ago. Call "
                "get_ui_elements or find_ui_elements for the ids of what the app shows now".format(number)
            )
        return element


_seen = _Seen()


class _Compact(BaseModel):
    """A model whose empty fields (null, false, an empty list) are left out of what the client is sent."""

    @model_serializer(mode="wrap")
    def _without_empty(self, handler: Any) -> Dict[str, Any]:
        dumped: Dict[str, Any] = handler(self)
        return {key: value for key, value in dumped.items() if not _empty(value)}


def _empty(value: Any) -> bool:
    # By identity for False: 0 is a position, or a slider's value, and 0 == False.
    return value is None or value is False or (isinstance(value, (list, str)) and not value)


class UIElement(_Compact):
    """Something an app shows, in points from the main display's top-left. Empty fields are left out."""

    id: int = Field(description="For the other ui tools.")
    role: str = Field(description="'button', 'text field', 'link', 'check box', 'menu item'...")
    name: Optional[str] = Field(default=None, description="Its label or text.")
    value: Union[str, float, bool, None] = Field(default=None, description="A field's text, a slider's position...")
    x: Optional[int] = Field(default=None, description="Its middle, where a click lands.")
    y: Optional[int] = Field(default=None, description="Its middle.")
    width: Optional[int] = Field(default=None, description="Width.")
    height: Optional[int] = Field(default=None, description="Height.")
    checked: Optional[bool] = Field(default=None, description="Whether a checkbox or switch is on.")
    disabled: bool = Field(default=False, description="Dimmed: can't be used now.")
    focused: bool = Field(default=False, description="Has the keyboard focus.")
    selected: bool = Field(default=False, description="Chosen: a row, a tab.")
    actions: List[str] = Field(default_factory=list, description="More actions, for perform_ui_action.")


class UIElements(BaseModel):
    """What an app shows."""

    app: str = Field(description="The app's name.")
    elements: List[UIElement] = Field(description="Top to bottom.")
    note: Optional[str] = Field(default=None, description="About the list, when there's something to say.")


class UIElementFound(BaseModel):
    """An element, or none."""

    element: Optional[UIElement] = Field(description="Null when there's none.")


class MenuItem(_Compact):
    """An item of an app's menus."""

    path: str = Field(description="For click_menu_item: 'File > Export > PDF…'.")
    shortcut: Optional[str] = Field(default=None, description="As press_keys takes it: 'cmd+shift+s'.")
    disabled: bool = Field(default=False, description="Dimmed: can't be chosen now.")
    checked: bool = Field(default=False, description="Shows a check mark.")


# Actions every control has, which press_ui_element does or which mean nothing to a model.
_PLAIN_ACTIONS = frozenset({"AXPress", "AXScrollToVisible", "AXRaise"})


def _role(element: Any) -> str:
    """The plainest name for what it is: its subrole when it has one that says more ('search field')."""
    subrole = element.subrole
    return _spoken(subrole if subrole and subrole not in ("AXUnknown", "AXStandardWindow") else element.role)


def _spoken(role: str) -> str:
    """``'AXPopUpButton'`` as ``'pop up button'``, as find_ui_elements takes it too."""
    name = role[2:] if role.startswith("AX") else role
    return "".join(
        " " + letter.lower() if letter.isupper() and index and not name[index - 1].isupper() else letter.lower()
        for index, letter in enumerate(name)
    )


def _described(element: Any) -> UIElement:
    # Left out when the app doesn't say where it is (the focused element of a few apps): 0, 0 would be a place.
    center_x, center_y = element.center or (None, None)
    width, height = element.frame[2:] if element.frame else (None, None)
    value = element.value
    if isinstance(value, str) and (not value.strip() or value.strip() == element.name):
        value = None
    if element.checked is not None:
        value = None  # said by checked
    return UIElement(
        id=_seen.add(element),
        role=_role(element),
        name=element.name,
        value=value,
        x=center_x,
        y=center_y,
        width=width,
        height=height,
        checked=element.checked,
        disabled=not element.enabled,
        focused=element.focused,
        selected=element.selected,
        actions=[action for action in element.actions if action not in _PLAIN_ACTIONS],
    )


def _found(element: Any) -> UIElementFound:
    return UIElementFound(element=_described(element) if element is not None else None)


def _listed(app: Optional[str], found: List[Any], limit: int, empty: str) -> UIElements:
    name = found[0].app if found else (app or "")
    note = None
    if not found:
        note = empty
    elif len(found) > limit:
        note = "Only the first {} of {} elements are listed: find_ui_elements looks for one by name.".format(
            limit, len(found)
        )
    return UIElements(app=name, elements=[_described(element) for element in found[:limit]], note=note)


def get_ui_elements(
    app: App = None,
    include_text: Annotated[
        bool,
        Field(description="Also list text, headings and images, not only controls."),
    ] = False,
    max_elements: Annotated[int, Field(description="The most elements to list.", ge=1, le=2000)] = 300,
) -> UIElements:
    """
    List what an app shows (buttons, fields, links, checkboxes, tabs, menus), each with an id for the other
    ui tools: to see an app before acting on it, rather than a screenshot. Only what's visible: the window
    in front and its panels, or only the menu, dialog or sheet that's open. Reads web pages too. Games and
    a few apps show little: take a screenshot then.
    """
    found = macos.ui.elements(app, controls_only=not include_text)
    return _listed(app, found, max_elements, "Nothing to use was found: the app may not show its controls to "
                   "Accessibility (take_screenshot sees it), or it has no window open.")


def find_ui_elements(
    name: Annotated[
        Optional[str],
        Field(description="A part of its name or text, in any case."),
    ] = None,
    role: Annotated[
        Optional[str],
        Field(description="'button', 'text field', 'link', 'search field'..."),
    ] = None,
    app: App = None,
) -> UIElements:
    """
    Find elements on screen by name, role or both: the 'Send' button, the search field. Exact names come
    first ('Save' before "Don't Save"), then top to bottom. Finds text too.
    """
    found = macos.ui.find(app, name=name, role=role)
    return _listed(app, found, 200, "None is on screen: get_ui_elements lists what is.")


def wait_for_ui_element(
    name: Annotated[Optional[str], Field(description="A part of its name or text.")] = None,
    role: Annotated[Optional[str], Field(description="'button', 'text field'...")] = None,
    app: App = None,
    timeout_seconds: Annotated[
        float, Field(description="At most, in seconds.", gt=0, le=LONGEST_WAIT)
    ] = 10.0,
) -> UIElementFound:
    """Wait until an element shows up (a page loaded, a dialog opened) and return it; null after the timeout."""
    if name is None and role is None:
        raise ValueError("give a name, a role, or both")
    return _found(macos.ui.wait_for(app, name=name, role=role, timeout=timeout_seconds))


def get_focused_ui_element() -> UIElementFound:
    """Get the element keystrokes go to now, in whichever app."""
    return _found(macos.ui.focused())


def get_ui_element_at(
    x: Annotated[float, Field(description="In points from the main display's left.")],
    y: Annotated[float, Field(description="In points from its top.")],
) -> UIElementFound:
    """Get the element a click at this point would reach, in whichever app."""
    return _found(macos.ui.at(x, y))


def press_ui_element(id: ElementId) -> str:
    """
    Press an element as a click would (a button, a link, a checkbox, a tab), without moving the pointer.
    What it does is the app's: a button may send, delete or buy.
    """
    element = _seen.get(id)
    element.press()
    return "Pressed {}.".format(_said(element))


def click_ui_element(
    id: ElementId,
    button: Annotated[Literal["left", "right"], Field(description="'right' opens a context menu.")] = "left",
    count: Annotated[int, Field(description="2 double-clicks: opens a file in a list.", ge=1, le=3)] = 1,
) -> str:
    """Click an element with the mouse: for a double or right click, or what press_ui_element can't press."""
    element = _seen.get(id)
    element.click(button=button, count=count)
    return "Clicked {}.".format(_said(element))


def set_ui_element_value(
    id: ElementId,
    value: Annotated[
        Union[str, float, bool],
        Field(description="A field's text (replacing it), a slider's number."),
    ],
) -> str:
    """Set a field's text or a slider's position. If refused or unnoticed, focus_ui_element and type_text instead."""
    element = _seen.get(id)
    element.set_value(value)
    return "Set {}.".format(_said(element))


def focus_ui_element(id: ElementId) -> str:
    """Give an element the keyboard focus, its app brought to the front, for type_text or press_keys."""
    element = _seen.get(id)
    element.focus()
    return "Focused {}.".format(_said(element))


def perform_ui_action(
    id: ElementId,
    action: Annotated[
        str,
        Field(
            description="One of its actions: 'AXShowMenu', 'AXIncrement', 'AXDecrement'...",
            min_length=1,
        ),
    ],
) -> str:
    """Do one of an element's actions, as its actions field lists them."""
    element = _seen.get(id)
    element.perform(action)
    return "Did {} on {}.".format(action, _said(element))


def read_ui_element_text(id: ElementId) -> str:
    """Read all the text an element holds, scrolled out of view included: a long text area, a message."""
    return str(_seen.get(id).text())


def list_menu_items(
    app: App = None,
    menu: Annotated[
        Optional[str],
        Field(description="Only this menu, such as 'File'. Every one by default."),
    ] = None,
) -> List[MenuItem]:
    """List an app's menu items and their shortcuts: what it can do, beyond what's on screen."""
    items = macos.ui.menu_items(app)
    if menu is not None:
        wanted = menu.casefold().strip()
        chosen = [item for item in items if item.path[0].casefold() == wanted]
        if not chosen:  # the menus there are, from the walk just done: another would cost as much again
            menus = list(dict.fromkeys(item.path[0] for item in items))
            raise LookupError("no menu {!r}: the menus are {}".format(menu, ", ".join(menus)))
        items = chosen
    return [
        MenuItem(path=" > ".join(item.path), shortcut=item.shortcut, disabled=not item.enabled, checked=item.checked)
        for item in items
    ]


def click_menu_item(
    path: Annotated[
        str,
        Field(
            description="Menu, then item, by '>': 'Format > Font > Bold'. '...' stands for '…'; any case.",
            min_length=3,
        ),
    ],
    app: App = None,
) -> str:
    """Choose an app's menu item, bringing the app to the front. What it does is the app's: it may delete or quit."""
    macos.ui.click_menu_item(path, app=app)
    return "Chose {}.".format(path)


def _said(element: Any) -> str:
    """The element as a sentence names it: "the button 'Send'"."""
    role = _role(element)
    return "the {} {!r}".format(role, element.name) if element.name else "the {}".format(role)


def register(server: MCPServer) -> None:
    # Everything here reads or acts through the Accessibility API, which needs its permission.
    for reader, title in (
        (get_ui_elements, "List what an app shows"),
        (find_ui_elements, "Find an element on screen"),
        (wait_for_ui_element, "Wait for an element"),
        (get_focused_ui_element, "Get the focused element"),
        (get_ui_element_at, "Get the element at a point"),
        (read_ui_element_text, "Read an element's text"),
        (list_menu_items, "List an app's menu items"),
    ):
        add_tool(server, reader, title=title, annotations=READ_ONLY, permission=ACCESSIBILITY)
    # Giving an element the focus changes nothing in it, and doing it again leaves the focus there.
    add_tool(server, focus_ui_element, title="Focus an element", annotations=ADDITIVE, permission=ACCESSIBILITY)
    # A text field's text is replaced by the one given: set again, it's the same.
    add_tool(
        server, set_ui_element_value, title="Set an element's value", annotations=REPLACING, permission=ACCESSIBILITY
    )
    # A press, a click, an action or a menu item does whatever the app does with it: send, delete, buy, quit.
    for actor, title in (
        (press_ui_element, "Press an element"),
        (click_ui_element, "Click an element"),
        (perform_ui_action, "Perform an element's action"),
        (click_menu_item, "Choose a menu item"),
    ):
        add_tool(server, actor, title=title, annotations=OPEN_ENDED, permission=ACCESSIBILITY)
