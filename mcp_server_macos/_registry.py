"""
How a tool gets into the server: one function, :func:`add_tool`, that every tool module uses.

It keeps the tools alike where it matters to a client: the name is the function's, the description its
docstring, the annotations always present, and the errors of pymacos always reported the same way,
a missing permission included.
"""

import functools
import inspect
from typing import Any, Callable, Dict, Optional, TypeVar

import macos
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import _permissions
from ._permissions import Permission

# How long a tool may wait for something to happen, in seconds: a call that never returns is of no
# use to a client.
LONGEST_WAIT = 600.0

_Function = TypeVar("_Function", bound=Callable[..., Any])

# What a tool does to the Mac, told to the client so it can decide what to ask the user before a call.
# The open-world hint says whether a tool reaches beyond this Mac: few do.

#: Reads something, changes nothing.
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)

#: Reads something from a server on the internet (Apple's, for the software updates), changes nothing.
READ_ONLY_ONLINE = ToolAnnotations(read_only_hint=True, open_world_hint=True)

#: Adds or shows something, without replacing or deleting anything.
ADDITIVE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)

#: Sets something to a given value, replacing the one it had: calling it again changes nothing more.
REPLACING = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False)

#: Deletes something, or does what can't be taken back.
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False)

#: Opens or runs something that may itself do anything, on this Mac or beyond it: a file that may be
#: a script, a URL, a shortcut. What it does can't be told beforehand, so it's marked as the worst.
OPEN_ENDED = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=True)


def translate_errors(function: _Function, permission: Optional[Permission] = None) -> _Function:
    """
    Make the failures of pymacos readable by the model that called the tool.

    The server reports a :class:`ToolError` to the client with its message, and anything else as a crash,
    without one (the text of an unexpected exception may hold what shouldn't leave this machine). So the
    errors pymacos raises on purpose become a :class:`ToolError`: when macOS fails or refuses
    (:class:`macos.MacOSError`: a missing permission, a feature this system lacks...) and when an argument
    is invalid (:class:`ValueError`), a file is missing or can't be opened (:class:`OSError`:
    :class:`FileNotFoundError`, :class:`PermissionError`...) or something asked for by name isn't
    there (:class:`LookupError`). The message starts with the exception's name,
    which says what kind of failure it was.

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
        except (macos.MacOSError, ValueError, OSError, LookupError) as error:
            if isinstance(error, (KeyError, IndexError)) and not isinstance(error, macos.MacOSError):
                raise  # a missing key or index is a bug in the code, not something that wasn't found on the Mac
            raise ToolError("{}: {}".format(type(error).__name__, error)) from error

    return wrapper  # type: ignore[return-value]


def on_main_thread(function: Callable[..., Any]) -> Callable[..., Any]:
    """
    Make ``function`` run on the thread the server runs on, which is the process's main thread.

    The server runs a plain function on a worker thread, to stay free for other calls meanwhile, and
    a coroutine function on its own thread. A few features of macOS only work on the main thread (the
    geocoder, the camera...), and pymacos refuses them elsewhere: this turns the function into a
    coroutine function, which is called where they work. While it runs, the server answers nothing else.
    """

    @functools.wraps(function)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        return function(*args, **kwargs)

    return wrapper


def add_tool(
    server: MCPServer,
    function: Callable[..., Any],
    *,
    title: str,
    annotations: ToolAnnotations,
    permission: Optional[Permission] = None,
    main_thread: bool = False,
) -> None:
    """
    Register ``function`` as a tool of ``server``.

    The tool is named after the function and described by its docstring, which is therefore written for
    the model: what the tool does, and what it needs to know to use it well. The arguments and the result
    are described by the function's annotations.

    ``annotations`` says what the tool does to the Mac: one of :data:`READ_ONLY`, :data:`ADDITIVE`,
    :data:`REPLACING`, :data:`DESTRUCTIVE` and :data:`OPEN_ENDED`. ``permission`` is the privacy permission of macOS the
    tool needs, if any, from :mod:`mcp_server_macos._permissions`: see :func:`translate_errors` for what
    happens when it's missing. ``main_thread`` is for a tool that uses what macOS only allows on the
    main thread: see :func:`on_main_thread`.
    """
    description = inspect.getdoc(function)
    if not description:
        raise ValueError("the tool {!r} has no docstring to describe it".format(function.__name__))

    tool = translate_errors(function, permission)
    server.add_tool(
        on_main_thread(tool) if main_thread else tool,
        name=function.__name__,
        title=title,
        description=description,
        annotations=annotations,
    )
    tidy(server, function.__name__)


def tidy(server: MCPServer, name: str) -> None:
    """
    The schemas of tool ``name`` as the client is sent them: without the title pydantic gives every
    argument and every model, an annotation that never changes what validates, and an eighth of what the
    tools cost a client. The SDK validates arguments and results with its own models, not with these.
    """
    registered = server._tool_manager.get_tool(name)
    if registered is None:  # pragma: no cover - the SDK keeps what it was given
        raise RuntimeError("the tool {!r} wasn't registered".format(name))
    registered.parameters = without_titles(registered.parameters)
    if registered.fn_metadata.output_schema is not None:
        registered.fn_metadata.output_schema = without_titles(registered.fn_metadata.output_schema)


# The keywords of a JSON Schema whose value maps names to schemas: a "title" there is a name (an argument
# called title), not the annotation.
_NAMED_SCHEMAS = ("properties", "patternProperties", "$defs", "definitions")


def without_titles(schema: Any) -> Any:
    """``schema`` (a JSON Schema) without its ``title`` annotations, at any depth, other keywords kept."""
    if isinstance(schema, list):
        return [without_titles(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    kept: Dict[str, Any] = {}
    for keyword, value in schema.items():
        if keyword == "title" and isinstance(value, str):
            continue
        if keyword in _NAMED_SCHEMAS and isinstance(value, dict):
            kept[keyword] = {name: without_titles(named) for name, named in value.items()}
        else:
            kept[keyword] = without_titles(value)
    return kept
