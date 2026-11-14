<h1 align="center">🍎 mcp-server-macos</h1>

<p align="center">
  <b>Let your AI assistant use your Mac.</b><br>
  <i>An MCP server for Claude, Cursor and any other MCP client, built on <a href="https://github.com/JeanExtreme002/pymacos">pymacos</a>.</i>
</p>

<p align="center">
  <a href="https://modelcontextprotocol.io"><img src="https://img.shields.io/badge/MCP-server-blue.svg" alt="MCP server" /></a>
  <a href="https://github.com/JeanExtreme002/mcp-server-macos/actions/workflows/test.yml"><img src="https://github.com/JeanExtreme002/mcp-server-macos/actions/workflows/test.yml/badge.svg" alt="Tests on macOS and Linux" /></a>
  <a href="https://pypi.org/project/mcp-server-macos/"><img src="https://img.shields.io/pypi/v/mcp-server-macos.svg" alt="Newest PyPI version" /></a>
  <a href="https://pypi.org/project/mcp-server-macos/"><img src="https://img.shields.io/pypi/pyversions/mcp-server-macos.svg?color=8A2BE2" alt="Supported Python versions" /></a>
  <img src="https://img.shields.io/badge/platform-macOS-lightgrey.svg" alt="Platform: macOS" />
  <a href="https://pypi.org/project/mcp-server-macos/"><img src="https://img.shields.io/pypi/status/mcp-server-macos.svg" alt="Development status" /></a>
  <a href="https://github.com/JeanExtreme002/mcp-server-macos/blob/main/LICENSE"><img src="https://img.shields.io/pypi/l/mcp-server-macos.svg" alt="License" /></a>
</p>

Add one line to your client, and your assistant gets tools that act on the Mac it's running on.
Two tools today, with the rest of pymacos on its way.

## Get started

With [uv](https://docs.astral.sh/uv/) installed, there's nothing to set up first.

In Claude Code:

```bash
claude mcp add macos -- uvx mcp-server-macos
```

In Cursor, one click:

<a href="https://cursor.com/en/install-mcp?name=macos&amp;config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJtY3Atc2VydmVyLW1hY29zIl19"><img src="https://cursor.com/deeplink/mcp-install-dark.svg" alt="Add mcp-server-macos to Cursor" height="32" /></a>

In Claude Desktop and other clients configured with JSON:

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

Prefer pip? Run `pip install mcp-server-macos` and use `mcp-server-macos` as the command, with no
arguments.

Requires macOS and Python 3.10 or newer.

## See it in action

> *"Run the tests and let me know when they're done. I'm getting coffee."*
>
> The tests run, and a notification shows up on your Mac: **Tests finished: 212 passed.**

> *"Is this Mac good enough to run that model locally?"*
>
> It looks: a MacBook Pro with an Apple M2 Pro and 16 GB of memory, on macOS 15.6. Then it answers
> for your machine, not for Macs in general.

## Tools

| Tool | What your assistant can do with it |
|---|---|
| `get_system_info` | Know the Mac it's on: the macOS version, the model, the processor, the memory, the computer's name and how long it has been running. |
| `send_notification` | Show you a notification, with a title, a subtitle and a sound if it wants one. |

Is there a tool you want next? [Open an issue](https://github.com/JeanExtreme002/mcp-server-macos/issues)
and say what you'd ask your assistant to do with it. That's what decides the order.

## Why this one

- It stands on [pymacos](https://github.com/JeanExtreme002/pymacos), a library for controlling macOS
  from Python that is tested against a real Mac on every change. The server adds no tricks of its own.
- What the assistant writes is never pasted into a shell command or a script, so a quote or a `$(...)`
  in a message is just text.
- When macOS refuses something because a permission is missing, the assistant is told which one,
  instead of believing it worked.
- It opens no network port. It only talks to the app that launched it.

## Permissions

macOS gives privacy permissions to the app that runs the server (Claude Desktop, your terminal, your
editor), not to the server itself.

Notifications are posted through Script Editor. If they're turned off for it in
*System Settings › Notifications*, `send_notification` says so instead of sending one you'd never see.

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
