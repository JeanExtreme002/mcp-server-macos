"""The permissions tools can declare: what each asks of pymacos, and of the user."""

import dataclasses
from typing import List

import macos
import pytest

from mcp_server_macos import _permissions
from mcp_server_macos._permissions import APP, Permission

EVERY: List[Permission] = [value for value in vars(_permissions).values() if isinstance(value, Permission)]

# The function of pymacos each permission's prompt is, by its path from the macos package.
PROMPTS = {
    "Screen Recording and Accessibility": "screen.request_permission keyboard.request_permission",
    "Screen Recording": "screen.request_permission",
    "Accessibility": "keyboard.request_permission",
    "Input Monitoring": "keyboard.request_listen_permission",
    "Camera": "camera.request_permission",
    "Microphone": "audio.request_permission",
}


def test_permissions_are_named_apart() -> None:
    names = [permission.name for permission in EVERY]

    assert len(names) == len(set(names))
    assert set(PROMPTS) <= set(names)


@pytest.mark.parametrize("permission", EVERY, ids=lambda permission: permission.name)
def test_permission_says_where_it_is_granted(permission: Permission) -> None:
    # In System Settings, but for what an app turns on in its own menu.
    in_an_app = permission is _permissions.BROWSER_JAVASCRIPT
    assert permission.where.startswith("its own menu: " if in_an_app else "System Settings › ")
    assert permission.name in permission.instructions()
    assert permission.where in permission.instructions()
    assert permission.app in permission.instructions()
    assert ("restart that app" in permission.instructions()) is permission.restart


@pytest.mark.parametrize("permission", EVERY, ids=lambda permission: permission.name)
def test_permission_asks_pymacos_for_its_prompt(permission: Permission, monkeypatch: pytest.MonkeyPatch) -> None:
    if permission.name not in PROMPTS:
        # macOS asks by itself, or has no prompt: there's nothing to call.
        assert permission.request is None
        assert _permissions.ask(permission) is False
        return

    # Some permissions are two, asked for one after the other: granted when both are.
    prompts = [path.split(".") for path in PROMPTS[permission.name].split()]
    for module, function in prompts:
        assert callable(getattr(getattr(macos, module), function)), "pymacos has no macos.{}.{}".format(
            module, function
        )

    for answer in (True, False):
        for module, function in prompts:
            monkeypatch.setattr(getattr(macos, module), function, lambda answer=answer: answer)
        assert _permissions.ask(permission) is answer


def test_both_prompts_show_even_when_the_first_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: List[str] = []

    def screen() -> bool:
        asked.append("screen")
        return False

    def accessibility() -> bool:
        asked.append("accessibility")
        return True

    monkeypatch.setattr(macos.screen, "request_permission", screen)
    monkeypatch.setattr(macos.keyboard, "request_permission", accessibility)

    assert _permissions.ask(_permissions.SCREEN_RECORDING_AND_ACCESSIBILITY) is False
    assert asked == ["screen", "accessibility"]


def test_permissions_are_granted_to_the_app_that_runs_the_server_except_notifications() -> None:
    # Notifications are posted through Script Editor, and a browser allows JavaScript itself: allowing
    # the MCP client wouldn't help.
    for permission in EVERY:
        if permission is _permissions.NOTIFICATIONS:
            assert permission.app.startswith("Script Editor")
            assert APP not in permission.instructions()
        elif permission is _permissions.BROWSER_JAVASCRIPT:
            assert permission.app == "the browser"
        else:
            assert permission.app == APP


def test_no_permission_has_nothing_to_ask() -> None:
    assert _permissions.ask(None) is False


def test_permissions_cannot_be_changed() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        _permissions.CAMERA.name = "Microphone"  # type: ignore[misc]
