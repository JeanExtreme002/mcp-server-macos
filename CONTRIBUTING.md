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
    ├── system.py
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
3. Register it in the module's `register(server)`, with `add_tool` and a title, and say two things
   about it:
   - `annotations`: what it does to the Mac, which a client uses to decide when to ask the user first.
     One of `READ_ONLY` (changes nothing), `ADDITIVE` (adds or shows something), `REPLACING` (sets
     something to a given value) and `DESTRUCTIVE` (deletes, or can't be taken back), from
     `_registry.py`. When in doubt between two, take the more cautious one.
   - `permission`: the privacy permission of macOS it needs, if any, from `_permissions.py`
     (`SCREEN_RECORDING`, `ACCESSIBILITY`...). The pymacos docs list
     [which feature needs which](https://macos.readthedocs.io/en/latest/permissions.html). When the
     permission is missing, the server asks macOS to show its prompt and runs the tool again if that
     granted it; otherwise the model is told what the user has to allow, and where.
4. Test it (below), and add its name to `TOOLS` in `tests/unit/test_server.py`. The README doesn't list
   the tools: a client shows them, with their descriptions.

## Toolsets

Each module of `mcp_server_macos/tools` is a toolset, named after it. The server offers them all by
default, and only the ones named when started with `--toolsets system,notifications` (or with the
`MCP_SERVER_MACOS_TOOLSETS` environment variable), for a client or a user that doesn't want every tool
listed. A new module needs nothing more than being in `MODULES` to become one.

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
  do really happens on your Mac: a notification shows up, for example.

Both call the tools as a client does, through the protocol, with the `client` fixture of
`tests/conftest.py`: that tests the schema and the error reporting along with the function. The tests
are async, run by the pytest plugin of anyio (`pytestmark = pytest.mark.anyio`).

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
[MCP Registry](https://registry.modelcontextprotocol.io), from `server.json`.
