# Contributing

Bug reports, ideas and pull requests are welcome on
[GitHub](https://github.com/JeanExtreme002/mcp-server-macos).

## Setup

```bash
git clone https://github.com/JeanExtreme002/mcp-server-macos.git
cd mcp-server-macos
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

The `Makefile` wraps every command below: run `make help` to list the targets,
for example `make check` (lint, type check and unit tests).

To try the server by hand, the [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector)
lists and calls its tools from a browser:

```bash
npx @modelcontextprotocol/inspector .venv/bin/mcp-server-macos
```

## How the package is laid out

```
mcp_server_macos/
├── server.py          create_server(), and main(): the mcp-server-macos command
├── _registry.py       add_tool(): how every tool is registered
├── _permissions.py    the privacy permissions a tool may need, and what happens when one is missing
└── tools/
    ├── __init__.py    MODULES: the list of tool modules, which are also the toolsets
    ├── notifications.py
    ├── system/        a package, where pymacos's module is too large for one file
    └── ...            one module per module of pymacos
```

The server holds no logic of its own about macOS: a tool turns its arguments into a call to
[pymacos](https://macos.readthedocs.io) and the result into something a model reads. A bug in what
happens on the Mac is fixed in pymacos, and so is a missing feature.

## Adding a tool

1. Find the module in `mcp_server_macos/tools` named after the pymacos module the tool calls
   (`tools/system.py` for `macos.system`), or create it, and then add it to `MODULES` in
   `tools/__init__.py`.
2. Write the tool as a plain function:
   - Its **name** is the tool's name: a verb and what it acts on, in `snake_case` (`get_system_info`,
     `send_notification`).
   - Its **docstring** is the tool's description. It's read by a model, not by a programmer: say what
     the tool does and what the model needs to know to use it well, not how it's implemented.
   - Its **arguments** are annotated, each with a description:
     `Annotated[str, Field(description="...")]`. Keep to types JSON has.
   - Its **result** is a `pydantic.BaseModel` whose fields are described, when it's data, or a short
     sentence, when the tool only acts. Convert what JSON lacks (a `timedelta` to seconds, a `Path` to
     text), and put the unit in the field's name (`memory_bytes`, `uptime_seconds`).
   - Don't catch the errors of pymacos: `add_tool` reports them to the model, with their message.
3. Register it in the module's `register(server)`, with `add_tool` and a title, and say what applies
   of these about it:
   - `annotations`: what it does to the Mac, which a client uses to decide when to ask the user first.
     One of `READ_ONLY` (changes nothing), `READ_ONLY_ONLINE` (changes nothing, and asks a server on
     the internet), `ADDITIVE` (adds or shows something), `REPLACING` (sets something to a given
     value), `DESTRUCTIVE` (deletes, or can't be taken back) and `OPEN_ENDED` (opens or runs what may
     itself do anything), from `_registry.py`. When in doubt between two, take the more cautious one.
     Three questions settle most of it, asked of every argument the tool takes, not only of its usual
     use:
     - Can it be called twice and change more the second time? Then it isn't idempotent: neither
       `READ_ONLY` nor `REPLACING`. A tool that writes to a path that may be its source is one (it
       rotates, crops or re-encodes again), and so is one that toggles, adds or skips.
     - Can any argument make it reach beyond this Mac (a URL, a page's resources, Apple's servers)?
       Then it's open-world: `READ_ONLY_ONLINE` or `OPEN_ENDED`.
     - Can it lose what was there (a file written over, a state the user had) or run what can do
       anything (a script, an app, a link)? Then it's `DESTRUCTIVE` or `OPEN_ENDED`, whatever it does
       most of the time.
   - `main_thread=True`, for the few features macOS only allows on the main thread (the geocoder, the
     camera...): pymacos raises `MainThreadError` for them elsewhere, and its docs say which they are.
     The tool then runs on the server's own thread, which answers nothing else meanwhile.
   - `permission`: the privacy permission of macOS it needs, if any, from `_permissions.py`
     (`SCREEN_RECORDING`, `ACCESSIBILITY`...). The pymacos docs list
     [which feature needs which](https://macos.readthedocs.io/en/latest/permissions.html). When the
     permission is missing, the server asks macOS to show its prompt and runs the tool again if that
     granted it; otherwise the model is told what the user has to allow, and where.
4. Test it (below), and add it to `ANNOTATIONS` in `tests/unit/test_server.py`, with what it does to the
   Mac. The README doesn't list the tools: a client shows them, with their descriptions.
5. If no tool uses one of the functions of the pymacos module, say why in `EXCLUDED`, in
   `tests/pymacos_api.py` (see *Covering pymacos* below).

## Toolsets

Each module of `mcp_server_macos/tools` is a toolset, named after it. A new module needs nothing more
than being in `MODULES` to become one.

The command starts with a few toolsets (`CORE`, in `mcp_server_macos/_on_demand.py`), so a client isn't
sent every tool before its first question. Two tools reach the others: `find_tools` searches every tool,
enabled or not, and `enable_toolsets` adds toolsets while the server runs, telling the client its list
changed. A tool added that way is defined exactly as it is with every toolset, schemas and annotations
included: a test checks it for every tool. `enable_toolsets`' description names every tool, by toolset,
so a model reading it sees what exists. A client that defers the tools itself, showing the model their
names and loading what it searches for (`CLIENTS_THAT_DEFER`: Claude Code), gets every toolset from the
start instead: it costs it the names only, and from the core the model saw no name telling it a tool
existed. `--toolsets system,notifications` (or the
`MCP_SERVER_MACOS_TOOLSETS` environment variable) starts with others, and `--toolsets all` with every one,
as `create_server()` does from Python.

## Tests

```bash
make test               # unit and live tests
make test-unit          # unit tests only (these also run on Linux): pytest tests/unit
make test-live          # live tests only: pytest tests/live
pytest tests/unit/test_system.py tests/live/test_system.py   # one module
```

The tests are in two folders, with one file per module (`test_system.py` tests
`mcp_server_macos.tools.system`):

- `tests/unit`: fake pymacos (with `monkeypatch`), and run anywhere.
- `tests/live`: call the tools against the real system, and are skipped outside macOS. What the tools
  do really happens on your Mac: a notification shows up, the clipboard is used (its text is put back)
  and the Mac is kept awake for a moment, a small disk image is made, mounted and unmounted, and a
  `sleep` process is started and ended, a sound is played at no volume, a preferences domain and a
  Keychain item of the tests' own are written and removed, Calculator is opened in the background and
  quit (unless it was open), three dialogs show for a second each, a folder of the tests' own is left
  out of the Time Machine backups and put back, and documents, images, PDFs, videos and sounds are
  made, converted and edited in a temporary folder, where Finder's tags, aliases, icons and zips are
  tried too, and screenshots saved. The microphone isn't recorded, no key is pressed nor click made,
  no window is moved or closed, the camera doesn't turn on, and nothing goes to the Trash. They only use the tools that
  leave things as they were: nothing is put to sleep, locked, said out loud, turned off, installed or run, and
  no setting is changed.

Both call the tools as a client does, through the protocol, with the `client` fixture of
`tests/conftest.py`: that tests the schema and the error reporting along with the function. The tests
are async, run by the pytest plugin of anyio (`pytestmark = pytest.mark.anyio`).

## Covering pymacos

The server means to offer what pymacos does, module by module. `make api-coverage` (or
`python -m tests.pymacos_api`) prints, for each module of pymacos, how many of its functions the
server uses.

A module that has a toolset is held to it by a test: each of its public functions is used by a tool,
or is in `EXCLUDED` (in `tests/pymacos_api.py`) with the reason none does, such as a function that
never returns. So when pymacos gains a function in a module the server covers, the test fails until a
tool uses it. The modules still being worked on are in `IN_PROGRESS`, in the same file.

## Lint and type check

```bash
flake8 mcp_server_macos tests
mypy mcp_server_macos tests
```

## Pull requests

- Use [Conventional Commits](https://www.conventionalcommits.org) for the title
  (`feat: ...`, `fix: ...`, `docs: ...`). The type is one of `feat`, `fix`,
  `perf`, `refactor`, `revert`, `docs`, `ci`, `build`, `chore`, `test` or
  `style`, and the subject starts with a lowercase letter and doesn't end with
  a period. A check enforces it.
- Add a test for every bug fix and new tool.
- Keep the dependencies to the MCP SDK and pymacos.

## Compatibility

mcp-server-macos follows [Semantic Versioning](https://semver.org). What it promises is what a client
sees: the tools' names, their arguments and their results.

- Until 1.0.0, a minor release may break them, and its notes say how. From 1.0.0 on, only a major
  release does.
- A new argument is optional, so existing calls keep their meaning. A result may gain a field, never
  lose or rename one.
- To rename or remove a tool, keep the old one for at least one minor release, with a description that
  says what to use instead.
- The dependencies are ranges in `pyproject.toml`, up to the next major release of each. CI tests the
  newest versions in the range (weekly too, with nothing pushed) and the oldest: raise a lower bound
  in the pull request that starts needing a newer pymacos or MCP SDK.

## Releases

The release notes on [GitHub Releases](https://github.com/JeanExtreme002/mcp-server-macos/releases)
are the changelog: there's no `CHANGELOG.md` to keep in step with them.

1. Merge the changes the release ships.
2. Open a pull request titled `chore: bump version to X.Y.Z` that only changes the version, following
   the rules above, and merge it. The version is written in two files, which a test keeps equal:
   `__version__` in `mcp_server_macos/__init__.py`, and `server.json` (twice: the server's and the
   package's).
3. On GitHub, create a release whose tag is `vX.Y.Z`, made from `main`. The notes list the changes
   under *New*, *Changed* (worth a look if you rely on them) and *Fixed*.

Publishing the release starts the `Publish to PyPI` workflow: it refuses a
tag that doesn't match `__version__` or isn't on `main`, builds the package
once, runs the whole suite (live tests included) against that build, and only
then uploads it. Once the package is on PyPI, it lists the release in the
[MCP Registry](https://registry.modelcontextprotocol.io), from `server.json`, and attaches
`mcp-server-macos.mcpb` to the release: the bundle Claude Desktop installs in one click, built by
`scripts/build_mcpb.py`. It holds no code of the server, only a `pyproject.toml` asking for this
version from PyPI, which is why it's built after the upload. `make clean` removes what the script
leaves in `build/` and `dist/`.
