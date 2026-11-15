"""The tools of mcp_server_macos.tools.browser, with macos.browser faked: no browser is touched."""

from typing import Any, Dict, List, Optional

import macos
import pytest
from mcp import Client

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio


class Tab:
    """A tab, as macos.browser gives it, which records what it's asked to do."""

    def __init__(self, window: int, index: int, title: str, url: str, active: bool = False) -> None:
        self.title, self.url, self.app = title, url, "Safari"
        self.window, self.index, self.active = window, index, active
        self.asked: List[Any] = []

    def activate(self) -> None:
        self.asked.append("activate")

    def close(self) -> None:
        self.asked.append("close")

    def reload(self) -> None:
        self.asked.append("reload")

    def go(self, url: str) -> None:
        self.asked.append(("go", url))


def listed(tab: Tab) -> Dict[str, Any]:
    return {"title": tab.title, "url": tab.url, "app": "Safari", "window": tab.window, "index": tab.index, "active": tab.active}


@pytest.fixture
def tabs(monkeypatch: pytest.MonkeyPatch) -> List[Tab]:
    """Two windows of Safari, and the browsers asked for."""
    found = [
        Tab(7, 1, "pymacos", "https://github.com/JeanExtreme002/pymacos", active=True),
        Tab(7, 2, "Docs", "https://macos.readthedocs.io"),
        Tab(9, 1, "Python", "https://python.org", active=True),
    ]
    monkeypatch.setattr(macos.browser, "tabs", lambda app=None: list(found))
    monkeypatch.setattr(macos.browser, "current_tab", lambda app=None: found[0])
    return found


async def test_list_browser_tabs(client: Client, tabs: List[Tab]) -> None:
    result = await client.call_tool("list_browser_tabs", {})

    assert not result.is_error
    assert result.structured_content == {"result": [listed(tab) for tab in tabs]}


async def test_list_browser_tabs_of_a_browser(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.browser, "tabs", recorder.function("tabs", []))

    result = await client.call_tool("list_browser_tabs", {"app": "Google Chrome"})

    assert result.structured_content == {"result": []}
    assert recorder.calls == [("tabs", ("Google Chrome",), {})]


@pytest.mark.parametrize("current", [True, False])
async def test_get_current_tab(client: Client, tabs: List[Tab], monkeypatch: pytest.MonkeyPatch, current: bool) -> None:
    if not current:
        monkeypatch.setattr(macos.browser, "current_tab", lambda app=None: None)

    result = await client.call_tool("get_current_tab", {})

    assert result.structured_content == {"tab": listed(tabs[0]) if current else None}


async def test_open_in_browser(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.browser, "open", recorder.function("open"))

    result = await client.call_tool("open_in_browser", {"url": "https://python.org", "app": "Safari"})

    assert not result.is_error
    assert text(result) == "Opened https://python.org."
    assert recorder.calls == [("open", ("https://python.org", "Safari"), {})]


async def test_open_in_browser_refuses_an_address_without_a_scheme(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    error = ValueError("url must have a scheme, such as https://, not 'example.com'")
    monkeypatch.setattr(macos.browser, "open", Recorder().function("open", error=error))

    result = await client.call_tool("open_in_browser", {"url": "example.com"})

    assert result.is_error
    assert "url must have a scheme" in text(result)


@pytest.mark.parametrize(
    "tool, arguments, asked, said",
    [
        ("switch_to_browser_tab", {}, "activate", "Switched to tab 2 of window 7."),
        ("reload_browser_tab", {}, "reload", "Reloaded tab 2 of window 7."),
        ("close_browser_tab", {}, "close", "Closed tab 2 of window 7."),
        (
            "navigate_browser_tab",
            {"url": "https://example.com"},
            ("go", "https://example.com"),
            "Tab 2 of window 7 is loading https://example.com.",
        ),
    ],
)
async def test_tab_is_found_by_window_and_position(
    client: Client, tabs: List[Tab], tool: str, arguments: Dict[str, Any], asked: Any, said: str
) -> None:
    result = await client.call_tool(tool, {"window": 7, "index": 2, **arguments})

    assert not result.is_error, text(result)
    assert text(result) == said
    assert [tab.asked for tab in tabs] == [[], [asked], []]


@pytest.mark.parametrize("window, index", [(7, 3), (8, 1), (9, 2)])
async def test_tab_that_is_not_there_is_not_touched(client: Client, tabs: List[Tab], window: int, index: int) -> None:
    result = await client.call_tool("close_browser_tab", {"window": window, "index": index})

    assert result.is_error
    assert "No tab {} in window {}".format(index, window) in text(result)
    assert all(tab.asked == [] for tab in tabs)


@pytest.mark.parametrize("returned", ["pymacos", "", None])
async def test_run_javascript_in_browser(client: Client, monkeypatch: pytest.MonkeyPatch, returned: Optional[str]) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.browser, "run_js", recorder.function("run_js", returned))

    result = await client.call_tool("run_javascript_in_browser", {"script": "document.title"})

    assert not result.is_error
    assert result.structured_content == {"result": returned}
    assert recorder.calls == [("run_js", ("document.title", None), {})]


async def test_javascript_the_browser_does_not_allow_says_where_to_allow_it(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    error = macos.PermissionDeniedError("Safari doesn't allow JavaScript from scripts")
    monkeypatch.setattr(macos.browser, "run_js", Recorder().function("run_js", error=error))

    result = await client.call_tool("run_javascript_in_browser", {"script": "1"})

    assert result.is_error
    assert "Ask them to allow the browser in its own menu" in text(result)
    assert "Develop › Allow JavaScript from Apple Events" in text(result)
    # Not the Automation of System Settings, which isn't what's missing.
    assert "System Settings › Privacy & Security › Automation" not in text(result)


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("open_in_browser", {}),
        ("open_in_browser", {"url": ""}),
        ("close_browser_tab", {"window": 7}),
        ("close_browser_tab", {"index": 1}),
        ("close_browser_tab", {"window": 7, "index": 0}),
        ("navigate_browser_tab", {"window": 7, "index": 1}),
        ("run_javascript_in_browser", {}),
        ("run_javascript_in_browser", {"script": ""}),
    ],
)
async def test_browser_is_not_touched_without_knowing_what(
    client: Client, tabs: List[Tab], monkeypatch: pytest.MonkeyPatch, tool: str, arguments: Dict[str, Any]
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.browser, "open", recorder.function("open"))
    monkeypatch.setattr(macos.browser, "run_js", recorder.function("run_js"))

    result = await client.call_tool(tool, arguments)

    assert result.is_error
    assert recorder.calls == []
    assert all(tab.asked == [] for tab in tabs)
