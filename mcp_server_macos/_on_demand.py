"""
Toolsets enabled on demand: the server starts with a few, and the model adds the others as a task needs
them, rather than every client being sent every tool before its first question.

Two tools do it. ``find_tools`` searches every tool of every toolset, enabled or not. ``enable_toolsets``
adds toolsets to the server, and tells the client its list of tools changed: the tools then show up as
they would have from the start, each with its own schema and annotations, so a client still asks before
the ones that change or delete something.
"""

import inspect
import re
from typing import TYPE_CHECKING, Annotated, Any, Dict, List, Literal, Optional

from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.mcpserver import Context, MCPServer
from pydantic import BaseModel, Field

from . import tools
from ._registry import READ_ONLY, tidy

#: The toolsets the command starts with: light, and of use in almost any task (telling the user
#: something, asking them, the clipboard). The others are a call to ``enable_toolsets`` away.
CORE = ("clipboard", "dialog", "notifications")

# The toolsets' names as a Literal, so the schema lists them: built from the toolsets, which mypy can't
# follow, so it's told a str.
if TYPE_CHECKING:
    ToolsetName = str
else:
    ToolsetName = Literal[tuple(tools.TOOLSETS)]

#: The clients that defer a server's tools themselves: they show the model each tool's name, and load what
#: it searches for. Every toolset is listed for them from the start, which costs them the names only, as
#: the model looks for a tool by what it's called: from the core, it saw no name telling it a tool exists
#: (asked to decrypt a PDF, it wrote a script, every time, where with every toolset it found decrypt_pdf).
CLIENTS_THAT_DEFER = ("claude-code",)


def summary(name: str) -> str:
    """What toolset ``name`` is for, in a line: its module's docstring, without the pymacos module it's from."""
    words = " ".join((tools.TOOLSETS[name].__doc__ or name).split())
    words = re.sub(r",? from ``macos\.\w+``", "", words)
    return words.split(". ")[0].rstrip(".,: ")


class ToolFound(BaseModel):
    """A tool, enabled or not."""

    name: str = Field(description="Its name, to call it once its toolset is enabled.")
    toolset: str = Field(description="The toolset it's in: enable_toolsets adds it.")
    enabled: bool = Field(description="Whether it can be called now. Otherwise, enable its toolset first.")
    title: Optional[str] = Field(description="Its title.")
    description: str = Field(description="What it does: the first lines of its description.")


class Enabled(BaseModel):
    """The toolsets enabled."""

    toolsets: List[str] = Field(description="Every toolset enabled now.")
    added: List[str] = Field(description="The tools this call added: callable now.")
    if_missing: str = Field(description="What to do if the tools added don't show up in the list of tools.")


# For a client that doesn't refresh its list of tools when told: the model is told how to get them, so
# the user is asked to change a setting rather than left without the tools, and without a reason.
IF_MISSING = (
    "If these tools don't show up in your list of tools, the client doesn't refresh it when the server "
    "says it changed: ask the user to start the server with --toolsets all (every tool listed from the "
    "start), or with --toolsets naming the toolsets they need, then restart the client."
)


class OnDemand:
    """The toolsets of one server: those enabled, and the two tools that find and enable the others."""

    def __init__(self, server: MCPServer, enabled: List[str], *, follow_client: bool = False) -> None:
        self.server = server
        self.enabled = list(enabled)
        # Whether the toolsets were left to the server (the command's default), rather than named: then a
        # client in CLIENTS_THAT_DEFER gets them all.
        self.follow_client = follow_client
        self._catalog: Optional[Dict[str, List[Any]]] = None

    def for_client(self, name: Optional[str]) -> None:
        """Before the client is sent the tools: every toolset for a client that defers them itself."""
        if self.follow_client and name in CLIENTS_THAT_DEFER:
            self.follow_client = False
            missing = [toolset for toolset in tools.TOOLSETS if toolset not in self.enabled]
            if missing:
                tools.register(self.server, missing)
                self.enabled += missing

    def catalog(self) -> Dict[str, List[Any]]:
        """Every toolset's tools, by toolset: built once, on a server of its own that nobody is sent."""
        if self._catalog is None:
            catalog = {}
            for name in tools.TOOLSETS:
                aside = MCPServer(name="catalog")
                tools.register(aside, [name])
                catalog[name] = aside._tool_manager.list_tools()
            self._catalog = catalog
        return self._catalog

    def register(self) -> None:
        """Add ``find_tools`` and ``enable_toolsets`` to the server, and say it may change its tools."""
        # Added as they are, not through add_tool: they don't call pymacos, so there's nothing of its to
        # translate, and enable_toolsets is a coroutine, which add_tool's wrapper would call on a worker.
        # Every tool's name, by toolset: a client that finds tools by searching their descriptions (Claude
        # Code does) finds "decrypt_pdf" for "decrypt a PDF" here, where the toolset's summary may not say it.
        groups = "\n".join(
            "- {}: {}. Tools: {}".format(name, summary(name), ", ".join(tool.name for tool in self.catalog()[name]))
            for name in tools.TOOLSETS
        )
        for function, title, description in (
            (self.find_tools, "Find a tool", inspect.getdoc(self.find_tools)),
            (
                self.enable_toolsets,
                "Enable toolsets",
                "{}\n\nThe toolsets:\n{}".format(inspect.getdoc(self.enable_toolsets), groups),
            ),
        ):
            self.server.add_tool(
                function, name=function.__name__, title=title, description=description, annotations=READ_ONLY
            )
            tidy(self.server, function.__name__)
        # Clients on the protocol versions before 2026-07-28 are told of a change only if the server said,
        # as it started, that it may make one. (From that version on, the SDK says so by itself.)
        lowlevel = self.server._lowlevel_server
        options = lowlevel.create_initialization_options
        setattr(
            lowlevel, "create_initialization_options", lambda *args, **kwargs: options(NotificationOptions(tools_changed=True))
        )

    def find_tools(
        self,
        query: Annotated[
            str,
            Field(
                description="What the tool should do, in a few words, such as 'encrypt a pdf' or 'take a screenshot'.",
                min_length=1,
            ),
        ],
        toolset: Annotated[
            Optional[ToolsetName], Field(description="Only this toolset's tools: all of them, whatever the query.")
        ] = None,
        limit: Annotated[int, Field(description="The most tools to return.", ge=1, le=50)] = 15,
    ) -> List[ToolFound]:
        """
        Search every tool this server has, enabled or not: the best matches first. A tool that isn't
        enabled yet is called once its toolset is, with enable_toolsets.
        """
        words = [word for word in re.findall(r"[a-z0-9]+", query.lower()) if len(word) > 1]
        scored = []
        for name, found in self.catalog().items():
            if toolset is not None and name != toolset:
                continue
            for tool in found:
                text = " ".join((tool.name.replace("_", " "), tool.title or "", tool.description or "", name)).lower()
                score = sum(3 if word in tool.name else 1 for word in words if word in text)
                if score or toolset is not None:
                    scored.append((score, name, tool))
        scored.sort(key=lambda item: -item[0])
        return [
            ToolFound(
                name=tool.name,
                toolset=name,
                enabled=name in self.enabled,
                title=tool.title,
                description=" ".join((tool.description or "").split())[:300],
            )
            for _, name, tool in scored[:limit]
        ]

    async def enable_toolsets(
        self,
        names: Annotated[List[ToolsetName], Field(description="The toolsets to add, such as ['pdf'].", min_length=1)],
        ctx: Context,
    ) -> Enabled:
        """
        Add toolsets to this server: their tools are listed, and callable, from now on, as the others.
        Enable only what the task needs: each toolset makes the list of tools longer.
        """
        added: List[str] = []
        for name in dict.fromkeys(names):
            if name in self.enabled:
                continue
            before = {tool.name for tool in self.server._tool_manager.list_tools()}
            tools.register(self.server, [name])
            self.enabled.append(name)
            added += [tool.name for tool in self.server._tool_manager.list_tools() if tool.name not in before]
        if added:
            # Both ways, as the client's protocol version decides which one it hears: a listen stream (from
            # 2026-07-28 on), or the notification of the versions before, which the SDK drops on the newer.
            await ctx.notify_tools_changed()
            await ctx.request_context.session.send_tool_list_changed()
        return Enabled(
            toolsets=[name for name in tools.TOOLSETS if name in self.enabled], added=added, if_missing=IF_MISSING
        )
