"""
How a tool gets into the server: one function, :func:`add_tool`, that every tool module uses.

It keeps the tools alike where it matters to a client: the name is the function's, the description its
docstring, the annotations always present, and the errors of pymacos always reported the same way,
a missing permission included.
"""

import functools
import inspect
from typing import Any, Callable, Optional, TypeVar

import macos
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import _permissions
from ._permissions import Permission

_Function = TypeVar("_Function", bound=Callable[..., Any])

# What a tool does to the Mac, told to the client so it can decide what to ask the user before a call.
# None of the tools reaches beyond this Mac (the open-world hint).

#: Reads something, changes nothing.
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)

#: Adds or shows something, without replacing or deleting anything.
ADDITIVE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)

#: Sets something to a given value, replacing the one it had: calling it again changes nothing more.
REPLACING = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False)

#: Deletes something, or does what can't be taken back.
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False)


def translate_errors(function: _Function, permission: Optional[Permission] = None) -> _Function:
    """
    Make the failures of pymacos readable by the model that called the tool.

    The server reports a :class:`ToolError` to the client with its message, and anything else as a crash,
    without one (the text of an unexpected exception may hold what shouldn't leave this machine). So the
    errors pymacos raises on purpose become a :class:`ToolError`: when macOS fails or refuses
    (:class:`macos.MacOSError`: a missing permission, a feature this system lacks...) and when an argument
    is invalid (:class:`ValueError`). The message starts with the exception's name, which says what kind
    of failure it was.

    A missing permission (:class:`macos.PermissionDeniedError`) gets more than a message. With
    ``permission``, the one the tool needs, macOS is asked to show its prompt, and the tool runs again if
    that granted it. When it stays missing, the message says what the user has to allow and where, for
    the model to ask them. pymacos checks the permission before it acts, so running the tool again
    doesn't do anything twice.
    """

    @functools.wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            try:
                return function(*args, **kwargs)
            except macos.PermissionDeniedError:
                if not _permissions.ask(permission):
                    raise
                return function(*args, **kwargs)
        except macos.PermissionDeniedError as error:
            raise ToolError(_permissions.missing(error, permission)) from error
        except (macos.MacOSError, ValueError) as error:
            raise ToolError("{}: {}".format(type(error).__name__, error)) from error

    return wrapper  # type: ignore[return-value]


def add_tool(
    server: MCPServer,
    function: Callable[..., Any],
    *,
    title: str,
    annotations: ToolAnnotations,
    permission: Optional[Permission] = None,
) -> None:
    """
    Register ``function`` as a tool of ``server``.

    The tool is named after the function and described by its docstring, which is therefore written for
    the model: what the tool does, and what it needs to know to use it well. The arguments and the result
    are described by the function's annotations.

    ``annotations`` says what the tool does to the Mac: one of :data:`READ_ONLY`, :data:`ADDITIVE`,
    :data:`REPLACING` and :data:`DESTRUCTIVE`. ``permission`` is the privacy permission of macOS the
    tool needs, if any, from :mod:`mcp_server_macos._permissions`: see :func:`translate_errors` for what
    happens when it's missing.
    """
    description = inspect.getdoc(function)
    if not description:
        raise ValueError("the tool {!r} has no docstring to describe it".format(function.__name__))

    server.add_tool(
        translate_errors(function, permission),
        name=function.__name__,
        title=title,
        description=description,
        annotations=annotations,
    )
