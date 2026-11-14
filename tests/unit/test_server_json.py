"""
server.json: what the MCP Registry lists of the server, published along with each release.

The registry refuses a listing that disagrees with the package on PyPI, after the package is uploaded,
when it's too late to fix the release. These tests find the disagreement before.
"""

import importlib.metadata
import json
import pathlib
import re
from typing import Any, Dict

import pytest

import mcp_server_macos

ROOT = pathlib.Path(__file__).parent.parent.parent


@pytest.fixture(scope="module")
def listing() -> Dict[str, Any]:
    listed: Dict[str, Any] = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    return listed


def test_versions_are_the_package_version(listing: Dict[str, Any]) -> None:
    # Bumped together with __version__ (see Releases in CONTRIBUTING.md).
    (package,) = listing["packages"]

    assert listing["version"] == mcp_server_macos.__version__
    assert package["version"] == mcp_server_macos.__version__


def test_package_is_the_one_on_pypi(listing: Dict[str, Any]) -> None:
    (package,) = listing["packages"]

    assert package["registryType"] == "pypi"
    assert package["identifier"] == importlib.metadata.metadata("mcp-server-macos")["Name"]
    assert package["transport"] == {"type": "stdio"}


def test_readme_claims_the_name(listing: Dict[str, Any]) -> None:
    # The registry looks for this marker in the package's description on PyPI, which is the README:
    # it's how the package says the listing is its own.
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "<!-- mcp-name: {} -->".format(listing["name"]) in readme
    assert len(re.findall(r"mcp-name:", readme)) == 1


def test_name_is_in_the_namespace_of_the_repository(listing: Dict[str, Any]) -> None:
    # The publish workflow logs in with GitHub's OIDC token, which only gives the right to publish
    # names under io.github.<owner of the repository>/.
    owner = re.fullmatch(r"https://github\.com/([^/]+)/[^/]+", listing["repository"]["url"])

    assert owner is not None, listing["repository"]["url"]
    assert listing["name"].startswith("io.github.{}/".format(owner.group(1)))


def test_description_fits_the_registry(listing: Dict[str, Any]) -> None:
    # The schema's limits. The description says what the server is for, not which tools it has.
    assert 1 <= len(listing["description"]) <= 100
    assert 1 <= len(listing["title"]) <= 100
