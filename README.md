# mcp-server-macos

An [MCP](https://modelcontextprotocol.io) server that lets an AI assistant use your Mac, built on
[pymacos](https://github.com/JeanExtreme002/pymacos).

<table>
    <tr>
        <th>tests</th>
        <td>
            <a href="https://github.com/JeanExtreme002/mcp-server-macos/actions/workflows/lint.yml"><img
                alt="GitHub Actions build status (Lint)"
                src="https://github.com/JeanExtreme002/mcp-server-macos/actions/workflows/lint.yml/badge.svg"></a>
            <a href="https://github.com/JeanExtreme002/mcp-server-macos/actions/workflows/test.yml"><img
                alt="GitHub Actions build status (Test on macOS and Linux)"
                src="https://github.com/JeanExtreme002/mcp-server-macos/actions/workflows/test.yml/badge.svg"></a>
            <a href="https://github.com/JeanExtreme002/mcp-server-macos/actions/workflows/build.yml"><img
                alt="GitHub Actions build status (Build: the package built, installed and tested)"
                src="https://github.com/JeanExtreme002/mcp-server-macos/actions/workflows/build.yml/badge.svg"></a>
        </td>
    </tr>
    <tr>
        <th>package</th>
        <td>
            <a href="https://pypi.org/project/mcp-server-macos/"><img
                alt="Newest PyPI version"
                src="https://img.shields.io/pypi/v/mcp-server-macos.svg"></a>
            <a href="https://pypi.org/project/mcp-server-macos/"><img
                alt="Supported Python versions"
                src="https://img.shields.io/pypi/pyversions/mcp-server-macos.svg?color=8A2BE2"></a>
            <a href="https://github.com/JeanExtreme002/mcp-server-macos/blob/main/LICENSE"><img
                alt="License"
                src="https://img.shields.io/pypi/l/mcp-server-macos.svg"></a>
        </td>
    </tr>
</table>

> **Early days.** The server works, with two tools to start with. More of pymacos is on its way.

## Tools

| Tool | What it does | Changes something? |
|---|---|---|
| `get_system_info` | The macOS version and build, the Mac's model, processor, memory and name, and how long it has been running. | No |
| `send_notification` | Shows a notification, with an optional title, subtitle and sound. | Shows a notification |

Every tool tells the client whether it only reads or changes something (the MCP tool annotations), so
the client can ask you before a call that does.

## Requirements

- macOS. The server starts on other systems, but every tool answers that it needs macOS.
- Python 3.10 or newer.

## Installation

The server is launched by your MCP client, which talks to it over stdin and stdout. With
[uv](https://docs.astral.sh/uv/), there's nothing to install first: `uvx mcp-server-macos` downloads
and runs it.

### Claude Code

```bash
claude mcp add macos -- uvx mcp-server-macos
```

### Claude Desktop, and other clients configured with JSON

Add the server to the client's configuration (for Claude Desktop, *Settings › Developer › Edit Config*):

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

### With pip

```bash
pip install mcp-server-macos
```

Then use `mcp-server-macos` as the command, with no arguments (or `python -m mcp_server_macos`). If
the client doesn't find it, give the command's full path, which `which mcp-server-macos` prints.

## Permissions

macOS grants privacy permissions to the app that runs the server (Claude Desktop, your terminal, your
IDE), not to the server. When a tool lacks one, its error says which.

`send_notification` posts through Script Editor: when notifications are turned off for it in
*System Settings › Notifications*, the tool reports an error instead of sending one that macOS would drop.

## Contributing

Bug reports, ideas and pull requests are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md), which
explains how to add a tool. To report a vulnerability, see [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE)
