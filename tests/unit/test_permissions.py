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
    assert permission.where.startswith("System Settings › ")
    assert permission.name in permission.instructions()
    assert permission.where in permission.instructions()
    assert APP in permission.instructions()
    assert ("restart that app" in permission.instructions()) is permission.restart


@pytest.mark.parametrize("permission", EVERY, ids=lambda permission: permission.name)
def test_permission_asks_pymacos_for_its_prompt(permission: Permission, monkeypatch: pytest.MonkeyPatch) -> None:
    if permission.name not in PROMPTS:
        # macOS asks by itself, or has no prompt: there's nothing to call.
        assert permission.request is None
        assert _permissions.ask(permission) is False
        return

    module, function = PROMPTS[permission.name].split(".")
    assert callable(getattr(getattr(macos, module), function)), "pymacos has no macos.{}".format(PROMPTS[permission.name])

    for answer in (True, False):
        monkeypatch.setattr(getattr(macos, module), function, lambda answer=answer: answer)
        assert _permissions.ask(permission) is answer


def test_no_permission_has_nothing_to_ask() -> None:
    assert _permissions.ask(None) is False


def test_permissions_cannot_be_changed() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        _permissions.CAMERA.name = "Microphone"  # type: ignore[misc]
