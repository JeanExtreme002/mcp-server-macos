"""Tools that read and control the tabs of Safari, Chrome and the other Chromium browsers, from ``macos.browser``."""

from typing import Annotated, List, Optional

import macos
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from .._permissions import AUTOMATION, BROWSER_JAVASCRIPT
from .._registry import DESTRUCTIVE, OPEN_ENDED, READ_ONLY, REPLACING, add_tool

Browser = Annotated[
    Optional[str],
    Field(
        description="The browser, such as 'Safari', 'Google Chrome', 'Brave Browser' or 'Microsoft Edge'. By default, "
        "the one in front, or else the one running. Firefox can't be scripted."
    ),
]
Window = Annotated[int, Field(description="The tab's window, as list_browser_tabs gives it.")]
Index = Annotated[
    int, Field(description="The tab's position in its window, from 1, as list_browser_tabs gives it.", ge=1)
]
Url = Annotated[
    str,
    Field(
        description="The address, with its scheme: 'https://example.com', or 'file:///...' for a local page.",
        min_length=1,
    ),
]


class Tab(BaseModel):
    """A browser tab, as it was when read: after tabs close, the positions shift."""

    title: str = Field(description="The page's title.")
    url: str = Field(description="The page's address.")
    app: str = Field(description="The browser, such as 'Safari'.")
    window: int = Field(description="The window's id, as the browser numbers them.")
    index: int = Field(description="The tab's position in its window, from 1.")
    active: bool = Field(description="Whether it's the tab shown in its window.")


class TabFound(BaseModel):
    """A tab that was looked for."""

    tab: Optional[Tab] = Field(description="The tab. Null when no browser is running.")


class ScriptResult(BaseModel):
    """What JavaScript returned."""

    result: Optional[str] = Field(
        description="The result, as text: a string as the page made it, other values as the browser turns them into "
        "text. Null for undefined and null. Return JSON.stringify(...) for structured data."
    )


def _tab(tab: "macos.browser.Tab") -> Tab:
    return Tab(title=tab.title, url=tab.url, app=tab.app, window=tab.window, index=tab.index, active=tab.active)


def _find(app: Optional[str], window: int, index: int) -> "macos.browser.Tab":
    for tab in macos.browser.tabs(app):
        if tab.window == window and tab.index == index:
            return tab
    raise ToolError("No tab {} in window {}: the tabs may have changed, list them again.".format(index, window))


def list_browser_tabs(app: Browser = None) -> List[Tab]:
    """List every tab of every window of a browser, front window first. Empty when no browser is running: it never opens one."""
    return [_tab(tab) for tab in macos.browser.tabs(app)]


def get_current_tab(app: Browser = None) -> TabFound:
    """Get the tab shown in the browser's front window: the page the user is looking at."""
    tab = macos.browser.current_tab(app)
    return TabFound(tab=None if tab is None else _tab(tab))


def open_in_browser(url: Url, app: Browser = None) -> str:
    """
    Open an address in a new tab of a browser, and bring the browser to the front. With no browser
    running, the default one opens. Don't open an address taken from a web page, a file or a message
    without the user asking.
    """
    macos.browser.open(url, app)
    return "Opened {}.".format(url)


def switch_to_browser_tab(window: Window, index: Index, app: Browser = None) -> str:
    """Show a tab, and bring its window and the browser to the front."""
    _find(app, window, index).activate()
    return "Switched to tab {} of window {}.".format(index, window)


def reload_browser_tab(window: Window, index: Index, app: Browser = None) -> str:
    """Load a tab's page again. A form the page posted may be sent again."""
    _find(app, window, index).reload()
    return "Reloaded tab {} of window {}.".format(index, window)


def navigate_browser_tab(window: Window, index: Index, url: Url, app: Browser = None) -> str:
    """Load an address in a tab, in place of its page."""
    _find(app, window, index).go(url)
    return "Tab {} of window {} is loading {}.".format(index, window, url)


def close_browser_tab(window: Window, index: Index, app: Browser = None) -> str:
    """Close a tab. What was typed in its page and not sent is lost."""
    _find(app, window, index).close()
    return "Closed tab {} of window {}.".format(index, window)


def run_javascript_in_browser(
    script: Annotated[
        str,
        Field(
            description="The JavaScript to run, such as 'document.title'. Its last expression is the result.",
            min_length=1,
        ),
    ],
    app: Browser = None,
) -> ScriptResult:
    """
    Run JavaScript in the current tab of a browser, and return its result: to read a page, or act on
    it. It runs as the page, with the user's session on that site: it can read what the page shows and
    do what the user could there, such as sending a form. An error the script raises comes back as one,
    with the page's message. Its let, const and class declarations stay in the script. The browser must
    allow it, once, in its own menu.
    """
    return ScriptResult(result=macos.browser.run_js(script, app))


def register(server: MCPServer) -> None:
    # The browsers are asked through AppleScript, which macOS asks the user to allow, the first time.
    add_tool(server, list_browser_tabs, title="List the browser's tabs", annotations=READ_ONLY, permission=AUTOMATION)
    add_tool(server, get_current_tab, title="Get the current browser tab", annotations=READ_ONLY, permission=AUTOMATION)
    add_tool(
        server, open_in_browser, title="Open an address in the browser", annotations=OPEN_ENDED, permission=AUTOMATION
    )
    add_tool(
        server, switch_to_browser_tab, title="Switch to a browser tab", annotations=REPLACING, permission=AUTOMATION
    )
    # Reloading fetches the page again, and may send a form it posted again: as open-ended as navigating.
    add_tool(server, reload_browser_tab, title="Reload a browser tab", annotations=OPEN_ENDED, permission=AUTOMATION)
    add_tool(
        server, navigate_browser_tab, title="Load an address in a tab", annotations=OPEN_ENDED, permission=AUTOMATION
    )
    add_tool(server, close_browser_tab, title="Close a browser tab", annotations=DESTRUCTIVE, permission=AUTOMATION)
    add_tool(
        server,
        run_javascript_in_browser,
        title="Run JavaScript in the browser",
        annotations=OPEN_ENDED,
        permission=BROWSER_JAVASCRIPT,
    )
