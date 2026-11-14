# Security Policy

## Supported Versions

Security fixes go into the latest release on PyPI. Please upgrade
(`pip install --upgrade mcp-server-macos`) before reporting, to check the issue still
exists.

## Reporting a Vulnerability

**Please do not open a public issue for a suspected vulnerability.** Use one
of the channels below instead, so the impact can be assessed and a fix
prepared before the details become public.

- **Preferred:** open a [private security advisory] on GitHub. This creates a
  private thread visible only to the maintainers and the reporter, supports
  CVE assignment, and lets us agree on a disclosure timeline.
- **Alternative:** email `contact@jeanloui.dev` with the subject
  `[mcp-server-macos security]`.

When reporting, please include:

- The mcp-server-macos version (`mcp-server-macos --version`), the pymacos version, the macOS
  version, Mac (Apple Silicon or Intel) and Python version.
- The MCP client, and the tool call (name and arguments) that reproduces the issue.
- The impact you observed and any prerequisites.

## Scope

mcp-server-macos runs on your Mac, as you, launched by an MCP client. It gives the model behind that
client tools that act on the Mac, through [pymacos](https://github.com/JeanExtreme002/pymacos). It
listens on no network port: it talks to the client that launched it over stdin and stdout.

In scope:

- **A tool doing more than it says:** a call that reads, changes or runs something its description,
  arguments and annotations don't cover, for example an argument interpreted as a path, a command or
  code.
- **Wrong annotations:** a tool that changes or deletes something while declaring itself read-only or
  non-destructive, which clients rely on to decide when to ask you first.
- **Leaks:** something a tool wasn't asked for reaching the client, for example through the message of
  an unexpected error, or the server writing a secret to its log.
- **Reachability:** the server accepting calls from anything but the client that launched it.

Out of scope:

- A model calling a tool as it's documented, because a prompt (or a web page, a file, an email the
  model read) told it to. The tools are meant to act on your Mac: which calls run unasked is for the
  client and for you to decide. Reports of a tool whose description or annotations make that decision
  harder than it should be are welcome, as a regular issue.
- Vulnerabilities in pymacos (report them [there](https://github.com/JeanExtreme002/pymacos/security)),
  in the MCP SDK, in the MCP client, in macOS itself or in the system commands pymacos runs.
- macOS privacy prompts and permissions. These are documented requirements, not defects.
- Using the server on a Mac or data you are not authorized to access.

[private security advisory]: https://github.com/JeanExtreme002/mcp-server-macos/security/advisories/new
