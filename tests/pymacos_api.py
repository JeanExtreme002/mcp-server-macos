"""
How much of pymacos the server covers: which of its functions a tool uses, and which none does.

The server means to offer what pymacos does, module by module. A module of pymacos is done when each
of its public functions is used by the server, or is in :data:`EXCLUDED` with the reason no tool uses
it. ``tests/unit/test_pymacos_api.py`` holds the modules that have a toolset to that, except the ones
in :data:`IN_PROGRESS`, so a function pymacos gains later doesn't go unnoticed.

Run it for the whole picture::

    python -m tests.pymacos_api
"""

import ast
import importlib
import pathlib
import pkgutil
from typing import Any, Dict, List, Set, Tuple

import macos

import mcp_server_macos
from mcp_server_macos import tools

#: The functions of pymacos that no tool uses, on purpose, and why.
EXCLUDED: Dict[str, str] = {
    "audio.outputs": "the devices of audio.devices() that play sound, which get_audio_status gives apart",
    "audio.inputs": "the devices of audio.devices() that record sound, which get_audio_status gives apart",
    "settings.batch": "a with block around other calls: apply_settings already restarts the Dock and Finder once",
    "auth.required": "a decorator for Python functions: authenticate_user asks the same question",
    "defaults.restored": "a with block around other calls: read_preference before and write_preference after do the same",
    "appearance.is_dark": "the same as mode() being 'dark', which get_appearance returns",
    "clipboard.watch": "yields copies for as long as it's iterated: a tool call returns once (wait_for_clipboard_change)",
}

#: The modules of pymacos that have a toolset, but not yet a tool for everything they do.
IN_PROGRESS: Set[str] = set()


def modules() -> List[str]:
    """The public modules of pymacos that have functions: ``"volume"`` for ``macos.volume``."""
    names = [module.name for module in pkgutil.iter_modules(macos.__path__) if not module.name.startswith("_")]
    return sorted(name for name in names if functions(name))


def functions(module: str) -> List[str]:
    """The public functions of a module of pymacos, as ``"volume.get"``: what its ``__all__`` names, classes aside."""
    loaded = importlib.import_module("macos.{}".format(module))
    return [
        "{}.{}".format(module, name)
        for name in getattr(loaded, "__all__", [])
        if callable(getattr(loaded, name)) and not isinstance(getattr(loaded, name), type)
    ]


def _resolve(path: str) -> Any:
    found: Any = macos
    for name in path.split("."):
        found = getattr(found, name)
    return found


def used() -> Set[int]:
    """
    The functions of pymacos the server's code names, as ``macos.volume.get`` or ``macos.notify``.

    By identity, not by name: ``macos.notify`` is ``macos.notifications.notify``, and using one is
    using the other.
    """
    found: Set[int] = set()
    for source in pathlib.Path(mcp_server_macos.__file__).parent.rglob("*.py"):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Attribute):
                continue
            parts: List[str] = []
            inner: ast.expr = node
            while isinstance(inner, ast.Attribute):
                parts.append(inner.attr)
                inner = inner.value
            if isinstance(inner, ast.Name) and inner.id == "macos":
                try:
                    found.add(id(_resolve(".".join(reversed(parts)))))
                except AttributeError:
                    pass  # not a name of pymacos: a longer chain, such as macos.power.Battery(...).percent
    return found


def coverage(module: str) -> Tuple[List[str], List[str], List[str]]:
    """The functions of a module of pymacos, apart: used by the server, excluded, and missing."""
    in_use = used()
    covered: List[str] = []
    excluded: List[str] = []
    missing: List[str] = []
    for function in functions(module):
        if id(_resolve(function)) in in_use:
            covered.append(function)
        elif function in EXCLUDED:
            excluded.append(function)
        else:
            missing.append(function)
    return covered, excluded, missing


def report() -> str:
    """One line per module of pymacos, and the totals."""
    lines = []
    total = done = 0
    for module in modules():
        covered, excluded, missing = coverage(module)
        handled = len(covered) + len(excluded)
        total += handled + len(missing)
        done += handled
        if module not in tools.TOOLSETS:
            state = "no toolset"
        elif missing:
            state = "in progress"
        else:
            state = "done"
        lines.append("{:<16}{:>4} of {:<4} {}".format(module, handled, handled + len(missing), state))
    lines.append("")
    lines.append("{} of {} functions of pymacos {} ({:.0%})".format(done, total, macos.__version__, done / total))
    return "\n".join(lines)


if __name__ == "__main__":
    print(report())
