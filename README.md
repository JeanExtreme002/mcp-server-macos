<h1 align="center">🍎 mcp-server-macos</h1>

<p align="center">
  <b>Let your AI assistant use your Mac.</b><br>
  <i>An MCP server for Claude, Cursor and any other MCP client, built on <a href="https://github.com/JeanExtreme002/pymacos">pymacos</a>.</i>
</p>

<p align="center">
  <a href="https://modelcontextprotocol.io"><img src="https://img.shields.io/badge/MCP-server-blue.svg" alt="MCP server" /></a>
  <a href="https://github.com/JeanExtreme002/mcp-server-macos/actions/workflows/test.yml"><img src="https://img.shields.io/github/actions/workflow/status/JeanExtreme002/mcp-server-macos/test.yml?branch=main&amp;label=CI" alt="CI: tests on macOS and Linux" /></a>
  <a href="https://pypi.org/project/mcp-server-macos/"><img src="https://img.shields.io/pypi/v/mcp-server-macos.svg" alt="Newest PyPI version" /></a>
  <a href="https://pypi.org/project/mcp-server-macos/"><img src="https://img.shields.io/badge/python-3.10+-8A2BE2.svg" alt="Python 3.10 or newer" /></a>
  <img src="https://img.shields.io/badge/platform-macOS-lightgrey.svg" alt="Platform: macOS" />
  <a href="https://pypi.org/project/mcp-server-macos/"><img src="https://img.shields.io/pypi/status/mcp-server-macos.svg" alt="Development status" /></a>
  <a href="https://github.com/JeanExtreme002/mcp-server-macos/blob/main/LICENSE"><img src="https://img.shields.io/pypi/l/mcp-server-macos.svg" alt="License" /></a>
</p>

Add it to your client in a minute, and your assistant stops explaining how to do things on your Mac
and starts doing them.

## Get started

With [uv](https://docs.astral.sh/uv/) installed, there's nothing to set up first.

In **Claude Code**:

```bash
claude mcp add macos -- uvx mcp-server-macos
```

In **Cursor**, one click:

<a href="https://cursor.com/en/install-mcp?name=macos&amp;config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJtY3Atc2VydmVyLW1hY29zIl19"><img src="https://cursor.com/deeplink/mcp-install-dark.svg" alt="Add mcp-server-macos to Cursor" height="32" /></a>

In **Claude Desktop** and other clients configured with JSON:

```json
{
  "mcpServers": {
    "macos": {
      "command": "uvx",
      "args": ["mcp-server-macos"]
    }
  }
}
```

No uv? `pip install mcp-server-macos`, then use `mcp-server-macos` as the command.

Requires macOS and Python 3.10 or newer.

## Permissions

macOS gives privacy permissions to the app that runs the server (Claude Desktop, your terminal, your
editor), not to the server itself.

When a tool needs a permission that's missing, it tells the assistant which one, instead of failing
silently.

## Contributing

Bug reports, ideas and pull requests are welcome.
[CONTRIBUTING.md](https://github.com/JeanExtreme002/mcp-server-macos/blob/main/CONTRIBUTING.md) explains
the setup and how to add a tool, which takes one function and its tests. To report a vulnerability, see
[SECURITY.md](https://github.com/JeanExtreme002/mcp-server-macos/blob/main/SECURITY.md).

If the project is useful to you, a star helps other people find it.

## License

Released under the [MIT License](https://github.com/JeanExtreme002/mcp-server-macos/blob/main/LICENSE),
free for personal and commercial use.

<sub>Not affiliated with or endorsed by Apple Inc. macOS is a trademark of Apple Inc.</sub>
