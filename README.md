<h1 align="center">🍎 mcp-server-macos</h1>

<!-- mcp-name: io.github.JeanExtreme002/mcp-server-macos -->

<p align="center">
  <b>Let your AI assistant use your Mac.</b><br>

Add it in a minute, and your assistant stops explaining what to do on your Mac and starts doing it.
Over 350 tools, for most of what a Mac does: ask in plain words, and it acts.

> *"Connect my AirPods and turn the volume down to 30%."*<br>
> *"Merge these three PDFs, then sign the last page."*<br>
> *"In Mail, archive the newsletter at the top of my inbox."*<br>
> *"Which app is eating my battery?"*<br>
> *"Turn this HEIC photo into a JPEG and remove its background."*<br>
> *"Every morning at 9, run my backup script."*

## Get started

With [uv](https://docs.astral.sh/uv/) installed, there's nothing to set up first.

In **Claude Desktop**, one click: download `mcp-server-macos.mcpb` from the
[latest release](https://github.com/JeanExtreme002/mcp-server-macos/releases/latest) and open it.

In **Claude Code**:

```bash
claude mcp add macos -- uvx mcp-server-macos
```

In **Cursor**, one click:

<a href="https://cursor.com/en/install-mcp?name=macos&amp;config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJtY3Atc2VydmVyLW1hY29zIl19"><img src="https://cursor.com/deeplink/mcp-install-dark.svg" alt="Add mcp-server-macos to Cursor" height="32" /></a>

In any other client configured with JSON:

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

## What it does

| | |
|---|---|
| **Your apps** | See what an app shows (buttons, fields, links, menus) and use it, without a screenshot. Open, quit, hide and uninstall apps; move, resize, snap and tile windows. |
| **Files and documents** | PDFs: read, merge, split, rotate, sign, redact, encrypt. Images and HEIC: convert, resize, crop, read metadata. Videos: convert, trim, join, turn into GIFs; audio files too. Word, RTF and HTML to text or PDF. Finder tags, the Trash, zips, Spotlight search. |
| **Understanding** | Read text in images and on screen, find QR codes and faces, say what a photo shows, remove its background. Detect a text's language, sentiment and entities. All offline, with Apple's own models. |
| **The screen** | Screenshots and recordings, the displays and their resolution, brightness, Night Shift, the wallpaper. |
| **Input** | Type text, press shortcuts, click, drag and scroll; the keyboard layout, the mouse and the trackpad. |
| **The Mac itself** | Battery, disks, processes, ports, logs, updates, crash reports. Wi-Fi, Bluetooth, VPNs, audio devices, volume, Dark Mode, the Dock, printers, Time Machine. |
| **Talking to you** | Notifications, dialogs that ask you something, Touch ID, speech, the clipboard. |
| **Automation** | Run your Shortcuts, schedule scripts with launchd, read and write app preferences, the Keychain, Apple Music and Spotify, browser tabs. |

It starts light, so the tools don't fill your assistant's context before the first question: it
turns on the groups of tools a task needs. To have every tool listed from the start, add
`--toolsets all`: do it if your client doesn't show the tools your assistant turns on.

## Built to be trusted

- **No shell, no scripts.** Every tool does one thing, through the APIs of macOS: your assistant
  can't run arbitrary commands through this server.
- **Your client asks before what matters.** Each tool says whether it only reads, changes a setting,
  or can delete or send something, so your client can ask you before the last ones.
- **No telemetry.** Nothing leaves your Mac unless a tool's job is to reach the internet (a speed
  test, an address to look up).
- **Two dependencies**: the MCP SDK and [pymacos](https://github.com/JeanExtreme002/pymacos), which
  needs none.
- **Tested against macOS itself**: besides the unit tests, CI runs live tests on macOS runners, for
  the tools that can run there without disturbing anything.

## Permissions

macOS gives privacy permissions to the app that runs the server (Claude Desktop, your terminal, your
editor), not to the server itself. Most tools need none. The others ask for theirs the first time:

- **Accessibility**: using apps, windows, the keyboard and the mouse.
- **Screen Recording**: screenshots and reading text on screen.
- **Automation** of an app (System Events, Finder, your browser, Music): asked by macOS for that app.
- **Camera**, **Microphone**, **Bluetooth**, **Location**: for the tools that use them.

When a permission is missing, the tool tells your assistant which one and where to allow it, instead
of failing silently.

## Limitations

- **macOS only**, and some tools need a recent macOS (they say so when they can't run).
- **Some apps show little to Accessibility** (games, a few cross-platform apps): your assistant can
  still see them with a screenshot and use the mouse.

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
