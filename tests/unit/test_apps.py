"""The tools of mcp_server_macos.tools.apps, with macos.apps faked."""

import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import macos
import pytest
from mcp import Client

from mcp_server_macos.tools import apps
from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio


class App:
    """A running app, as macos.apps gives it: what the tools read of it, and what they ask it to do."""

    def __init__(self, name: str, pid: int, active: bool = False, hidden: bool = False, obeys: bool = True) -> None:
        self.name: Optional[str] = name
        self.bundle_id: Optional[str] = "com.example.{}".format(name.lower())
        self.pid = pid
        self.path: Optional[str] = "/Applications/{}.app".format(name)
        self.is_active = active
        self.is_hidden = hidden
        self.obeys = obeys
        self.asked: List[Any] = []

    def activate(self) -> bool:
        self.asked.append("activate")
        return self.obeys

    # As recent versions of macOS do: the answer is no, and the app hides or shows all the same.
    def hide(self) -> bool:
        self.asked.append("hide")
        if self.obeys:
            self.is_hidden = True
        return False

    def unhide(self) -> bool:
        self.asked.append("unhide")
        if self.obeys:
            self.is_hidden = False
        return False

    def quit(self, *, force: bool = False, timeout: Optional[float] = None) -> bool:
        self.asked.append(("quit", force, timeout))
        return self.obeys


def listed(app: App) -> Dict[str, Any]:
    return {
        "name": app.name,
        "bundle_id": app.bundle_id,
        "pid": app.pid,
        "path": app.path,
        "is_active": app.is_active,
        "is_hidden": app.is_hidden,
    }


@pytest.fixture
def safari(monkeypatch: pytest.MonkeyPatch) -> App:
    """Safari, running, which macos.apps.get finds by any name but 'Nope'."""
    app = App("Safari", 420, active=True)
    monkeypatch.setattr(macos.apps, "get", lambda name: None if name == "Nope" else app)
    monkeypatch.setattr(apps, "HIDE_TIMEOUT", 1.0)  # an app that doesn't hide isn't waited for long
    return app


@pytest.mark.parametrize("arguments, background", [({}, False), ({"include_background": True}, True)])
async def test_list_running_apps(
    client: Client, monkeypatch: pytest.MonkeyPatch, arguments: Dict[str, Any], background: bool
) -> None:
    recorder = Recorder()
    apps = [App("Safari", 420, active=True), App("Notes", 421, hidden=True)]
    monkeypatch.setattr(macos.apps, "running", recorder.function("running", apps))

    result = await client.call_tool("list_running_apps", arguments)

    assert not result.is_error
    assert result.structured_content == {"result": [listed(app) for app in apps]}
    assert recorder.calls == [("running", (), {"include_background": background})]


@pytest.mark.parametrize("front", [App("Notes", 7), None])
async def test_get_frontmost_app(client: Client, monkeypatch: pytest.MonkeyPatch, front: Optional[App]) -> None:
    monkeypatch.setattr(macos.apps, "frontmost", lambda: front)

    result = await client.call_tool("get_frontmost_app", {})

    assert not result.is_error
    assert result.structured_content == {"app": None if front is None else listed(front)}


async def test_get_running_app(client: Client, safari: App) -> None:
    found = await client.call_tool("get_running_app", {"name": "com.apple.Safari"})
    missing = await client.call_tool("get_running_app", {"name": "Nope"})

    assert found.structured_content == {"app": listed(safari)}
    # Not an error: an app that isn't running is an answer.
    assert not missing.is_error
    assert missing.structured_content == {"app": None}


@pytest.mark.parametrize("arguments, background", [({}, False), ({"background": True}, True)])
async def test_open_app(
    client: Client, monkeypatch: pytest.MonkeyPatch, arguments: Dict[str, Any], background: bool
) -> None:
    recorder = Recorder()
    app = App("Safari", 420)
    monkeypatch.setattr(macos.apps, "open", recorder.function("open", app))

    result = await client.call_tool("open_app", {"name": "Safari", **arguments})

    assert not result.is_error
    assert result.structured_content == listed(app)
    assert recorder.calls == [("open", ("Safari",), {"background": background})]


@pytest.mark.parametrize(
    "error, expected",
    [
        (macos.AppNotFoundError("unable to find application 'Nope'"), "AppNotFoundError: unable to find"),
        (macos.AppLaunchTimeoutError("Slow did not show up within 10 seconds"), "AppLaunchTimeoutError"),
        (macos.CommandError(["open"], 1, "the application is damaged"), "the application is damaged"),
    ],
)
async def test_open_app_that_does_not_open(
    client: Client, monkeypatch: pytest.MonkeyPatch, error: Exception, expected: str
) -> None:
    monkeypatch.setattr(macos.apps, "open", Recorder().function("open", error=error))

    result = await client.call_tool("open_app", {"name": "Nope"})

    assert result.is_error
    assert expected in text(result)


@pytest.mark.parametrize(
    "tool, arguments, asked, said",
    [
        ("activate_app", {}, "activate", "Safari is in front."),
        ("set_app_hidden", {"hidden": True}, "hide", "Safari is hidden."),
        ("quit_app", {}, ("quit", False, 10.0), "Safari quit."),
        ("quit_app", {"force": True}, ("quit", True, 10.0), "Safari quit."),
    ],
)
async def test_running_app_is_told_what_to_do(
    client: Client, safari: App, tool: str, arguments: Dict[str, Any], asked: Any, said: str
) -> None:
    result = await client.call_tool(tool, {"name": "Safari", **arguments})

    assert not result.is_error, text(result)
    assert text(result) == said
    assert safari.asked == [asked]


@pytest.mark.parametrize(
    "tool, arguments, why",
    [
        ("activate_app", {}, "Safari didn't come to the front."),
        ("set_app_hidden", {"hidden": True}, "Safari couldn't be hidden."),
        ("quit_app", {}, "Safari is still running: it may be asking to save changes"),
    ],
)
async def test_running_app_that_does_not_obey_is_an_error(
    client: Client, safari: App, tool: str, arguments: Dict[str, Any], why: str
) -> None:
    # macOS says no without saying why: the tool must not say it worked.
    safari.obeys = False

    result = await client.call_tool(tool, {"name": "Safari", **arguments})

    assert result.is_error
    assert why in text(result)


async def test_hidden_app_is_shown_again(client: Client, safari: App) -> None:
    safari.is_hidden = True

    result = await client.call_tool("set_app_hidden", {"name": "Safari", "hidden": False})

    assert not result.is_error, text(result)
    assert text(result) == "Safari is shown."
    assert (safari.asked, safari.is_hidden) == (["unhide"], False)


async def test_hidden_app_that_does_not_show_is_an_error(client: Client, safari: App) -> None:
    safari.is_hidden = True
    safari.obeys = False

    result = await client.call_tool("set_app_hidden", {"name": "Safari", "hidden": False})

    assert result.is_error
    assert "Safari couldn't be shown." in text(result)


async def test_app_takes_a_moment_to_hide(client: Client, safari: App, monkeypatch: pytest.MonkeyPatch) -> None:
    # macOS hides it a moment after it's asked: the tool waits for that, and doesn't go by the answer.
    def hide() -> bool:
        threading.Timer(0.05, lambda: setattr(safari, "is_hidden", True)).start()
        return False

    monkeypatch.setattr(safari, "hide", hide)

    result = await client.call_tool("set_app_hidden", {"name": "Safari", "hidden": True})

    assert not result.is_error, text(result)
    assert safari.is_hidden


async def test_app_that_drops_the_first_request_is_asked_again(
    client: Client, safari: App, monkeypatch: pytest.MonkeyPatch
) -> None:
    # An app that's still opening ignores the request: the tool asks again until it's hidden.
    asked = []

    def hide() -> bool:
        asked.append("hide")
        if len(asked) >= 2:
            safari.is_hidden = True
        return False

    monkeypatch.setattr(safari, "hide", hide)

    result = await client.call_tool("set_app_hidden", {"name": "Safari", "hidden": True})

    assert not result.is_error, text(result)
    assert asked == ["hide", "hide"]


async def test_app_already_as_wanted_is_not_asked(client: Client, safari: App) -> None:
    safari.is_hidden = True

    result = await client.call_tool("set_app_hidden", {"name": "Safari", "hidden": True})

    assert not result.is_error
    assert safari.asked == []


@pytest.mark.parametrize(
    "tool, arguments", [("activate_app", {}), ("set_app_hidden", {"hidden": True}), ("quit_app", {"force": True})]
)
async def test_app_that_is_not_running_cannot_be_told_anything(
    client: Client, safari: App, tool: str, arguments: Dict[str, Any]
) -> None:
    result = await client.call_tool(tool, {"name": "Nope", **arguments})

    assert result.is_error
    assert "Nope isn't running." in text(result)
    assert safari.asked == []


@pytest.mark.parametrize(
    "arguments, expected",
    [
        ({}, ["Safari", "Safari Technology Preview", "Xcode"]),
        ({"search": "SAFARI"}, ["Safari", "Safari Technology Preview"]),
        ({"search": "code"}, ["Xcode"]),
        ({"search": "nope"}, []),
        ({"limit": 1}, ["Safari"]),
    ],
)
async def test_list_installed_apps(
    client: Client, monkeypatch: pytest.MonkeyPatch, arguments: Dict[str, Any], expected: List[str]
) -> None:
    installed = macos.apps.InstalledApp
    apps = [
        installed(name="Safari", bundle_id="com.apple.Safari", version="18.6", path=Path("/Applications/Safari.app")),
        installed(name="Safari Technology Preview", bundle_id=None, version=None, path=Path("/Applications/STP.app")),
        installed(name="Xcode", bundle_id="com.apple.dt.Xcode", version="16.2", path=Path("/Applications/Xcode.app")),
    ]
    monkeypatch.setattr(macos.apps, "installed", lambda: apps)

    result = await client.call_tool("list_installed_apps", arguments)

    assert not result.is_error
    assert result.structured_content is not None
    assert [app["name"] for app in result.structured_content["result"]] == expected
    if expected[:1] == ["Safari"]:
        assert result.structured_content["result"][0] == {
            "name": "Safari",
            "bundle_id": "com.apple.Safari",
            "version": "18.6",
            "path": "/Applications/Safari.app",
        }


async def test_get_default_app(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.apps, "default_for", recorder.function("default_for", "/System/Applications/Preview.app"))
    monkeypatch.setattr(macos.apps, "default_browser", recorder.function("default_browser", "/Applications/Safari.app"))

    by_kind = await client.call_tool("get_default_app", {"kind": ".pdf"})
    browser = await client.call_tool("get_default_app", {"kind": "Browser"})

    assert by_kind.structured_content == {"path": "/System/Applications/Preview.app"}
    assert browser.structured_content == {"path": "/Applications/Safari.app"}
    assert recorder.calls == [("default_for", (".pdf",), {}), ("default_browser", (), {})]


async def test_get_default_app_for_a_kind_nothing_opens(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(macos.apps, "default_for", lambda kind: None)

    result = await client.call_tool("get_default_app", {"kind": "xyz"})

    assert not result.is_error
    assert result.structured_content == {"path": None}


async def test_set_default_app(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.apps, "set_default_for", recorder.function("set_default_for"))

    result = await client.call_tool("set_default_app", {"kind": "md", "app": "Visual Studio Code"})

    assert not result.is_error
    assert text(result) == "Visual Studio Code now opens md files."
    assert recorder.calls == [("set_default_for", ("md", "Visual Studio Code"), {})]


async def test_set_default_app_that_the_user_declines(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    error = macos.MacOSError("the change was declined")
    monkeypatch.setattr(macos.apps, "set_default_for", Recorder().function("set_default_for", error=error))

    result = await client.call_tool("set_default_app", {"kind": "md", "app": "Xcode"})

    assert result.is_error
    assert "MacOSError: the change was declined" in text(result)


@pytest.mark.parametrize(
    "arguments, options",
    [
        ({}, {"destination": "/Applications", "replace": False, "app": None}),
        (
            {"replace": True, "app": "Tool", "destination": "/Users/me/Applications"},
            {"destination": "/Users/me/Applications", "replace": True, "app": "Tool"},
        ),
    ],
)
async def test_install_app_from_disk_image(
    client: Client, monkeypatch: pytest.MonkeyPatch, arguments: Dict[str, Any], options: Dict[str, Any]
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.apps, "install_from_dmg", recorder.function("install_from_dmg", "/Applications/Tool.app"))

    result = await client.call_tool("install_app_from_disk_image", {"image": "/Users/me/Downloads/Tool.dmg", **arguments})

    assert not result.is_error
    assert result.structured_content == {"path": "/Applications/Tool.app"}
    assert recorder.calls == [("install_from_dmg", ("/Users/me/Downloads/Tool.dmg",), options)]


async def test_install_app_that_is_already_there(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    error = FileExistsError("/Applications/Tool.app is already installed")
    monkeypatch.setattr(macos.apps, "install_from_dmg", Recorder().function("install_from_dmg", error=error))

    result = await client.call_tool("install_app_from_disk_image", {"image": "/Tool.dmg"})

    assert result.is_error
    assert "FileExistsError" in text(result)


@pytest.mark.parametrize(
    "arguments, options, moved",
    [
        ({}, {"dry_run": False, "include_name_matches": False}, True),
        ({"dry_run": True, "include_name_matches": True}, {"dry_run": True, "include_name_matches": True}, False),
    ],
)
async def test_uninstall_app(
    client: Client, monkeypatch: pytest.MonkeyPatch, arguments: Dict[str, Any], options: Dict[str, Any], moved: bool
) -> None:
    recorder = Recorder()
    paths = [Path("/Applications/Slack.app"), Path("/Users/me/Library/Caches/com.tinyspeck.slackmacgap")]
    monkeypatch.setattr(macos.apps, "uninstall", recorder.function("uninstall", paths))

    result = await client.call_tool("uninstall_app", {"name": "Slack", **arguments})

    assert not result.is_error
    assert result.structured_content == {
        "moved": moved,
        "paths": ["/Applications/Slack.app", "/Users/me/Library/Caches/com.tinyspeck.slackmacgap"],
    }
    assert recorder.calls == [("uninstall", ("Slack",), options)]


async def test_uninstall_app_that_is_running(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    error = macos.MacOSError("Slack is running: quit it first")
    monkeypatch.setattr(macos.apps, "uninstall", Recorder().function("uninstall", error=error))

    result = await client.call_tool("uninstall_app", {"name": "Slack"})

    assert result.is_error
    assert "MacOSError: Slack is running" in text(result)


async def test_login_items(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    items = [
        macos.apps.LoginItem(name="Rectangle", path="/Applications/Rectangle.app"),
        macos.apps.LoginItem(name="Old", path=None),
    ]
    monkeypatch.setattr(macos.apps, "login_items", lambda: items)
    monkeypatch.setattr(macos.apps, "add_login_item", recorder.function("add_login_item", items[0]))
    monkeypatch.setattr(macos.apps, "remove_login_item", recorder.function("remove_login_item", True))

    listed_items = await client.call_tool("list_login_items", {})
    added = await client.call_tool("add_login_item", {"app": "Rectangle"})
    removed = await client.call_tool("remove_login_item", {"app": "Old"})

    assert listed_items.structured_content == {
        "result": [{"name": "Rectangle", "path": "/Applications/Rectangle.app"}, {"name": "Old", "path": None}]
    }
    assert added.structured_content == {"name": "Rectangle", "path": "/Applications/Rectangle.app"}
    assert text(removed) == "Old no longer opens at login."
    assert recorder.calls == [("add_login_item", ("Rectangle",), {}), ("remove_login_item", ("Old",), {})]


async def test_remove_login_item_that_is_not_one(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(macos.apps, "remove_login_item", lambda app: False)

    result = await client.call_tool("remove_login_item", {"app": "Safari"})

    assert not result.is_error
    assert text(result) == "Safari wasn't a login item."


async def test_login_items_without_the_permission_say_what_to_allow(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    def login_items() -> Any:
        raise macos.PermissionDeniedError("not allowed to control System Events")

    monkeypatch.setattr(macos.apps, "login_items", login_items)

    result = await client.call_tool("list_login_items", {})

    assert result.is_error
    assert "System Settings › Privacy & Security › Automation" in text(result)


async def test_quarantine(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.apps, "is_quarantined", recorder.function("is_quarantined", True))
    monkeypatch.setattr(macos.apps, "unquarantine", recorder.function("unquarantine", 214))

    checked = await client.call_tool("check_quarantine", {"path": "/Applications/Tool.app"})
    removed = await client.call_tool("remove_quarantine", {"path": "/Applications/Tool.app"})

    assert checked.structured_content == {"quarantined": True}
    assert removed.structured_content == {"files": 214}
    assert recorder.calls == [
        ("is_quarantined", ("/Applications/Tool.app",), {}),
        ("unquarantine", ("/Applications/Tool.app",), {}),
    ]


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("get_running_app", {}),
        ("open_app", {"name": ""}),
        ("activate_app", {}),
        ("set_app_hidden", {"name": "Safari"}),
        ("quit_app", {"name": "Safari", "force": "please"}),
        ("list_installed_apps", {"limit": 0}),
        ("get_default_app", {}),
        ("set_default_app", {"kind": "md"}),
        ("set_default_app", {"kind": "", "app": "Xcode"}),
        ("install_app_from_disk_image", {}),
        ("install_app_from_disk_image", {"image": "/a.dmg", "destination": ""}),
        ("uninstall_app", {}),
        ("uninstall_app", {"name": ""}),
        ("add_login_item", {}),
        ("remove_login_item", {"app": ""}),
        ("check_quarantine", {}),
        ("remove_quarantine", {"path": ""}),
    ],
)
async def test_apps_are_not_touched_without_knowing_which(
    client: Client, monkeypatch: pytest.MonkeyPatch, tool: str, arguments: Dict[str, Any]
) -> None:
    recorder = Recorder()
    for name in macos.apps.__all__:
        if callable(getattr(macos.apps, name)) and not isinstance(getattr(macos.apps, name), type):
            monkeypatch.setattr(macos.apps, name, recorder.function(name))

    result = await client.call_tool(tool, arguments)

    assert result.is_error
    assert recorder.calls == []
