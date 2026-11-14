"""
What the server covers of pymacos: a module with a toolset has a tool for each of its functions.

See tests/pymacos_api.py, which lists the exceptions and prints the whole picture.
"""

import macos
import pytest

from mcp_server_macos import tools
from tests import pymacos_api
from tests.pymacos_api import EXCLUDED, IN_PROGRESS


@pytest.mark.parametrize("module", sorted(set(tools.TOOLSETS) - IN_PROGRESS))
def test_module_with_a_toolset_is_covered(module: str) -> None:
    covered, excluded, missing = pymacos_api.coverage(module)

    assert covered, "no tool uses macos.{}".format(module)
    assert not missing, (
        "pymacos {} has functions that no tool uses: {}. Add a tool for each, or list it in EXCLUDED "
        "(tests/pymacos_api.py) with the reason it can't be one.".format(macos.__version__, ", ".join(missing))
    )


def test_toolsets_are_modules_of_pymacos() -> None:
    assert set(tools.TOOLSETS) <= set(pymacos_api.modules())


@pytest.mark.parametrize("module", sorted(IN_PROGRESS))
def test_module_in_progress_really_is(module: str) -> None:
    # Once nothing is missing, the module comes off the list, so it's held to it from then on.
    assert module in tools.TOOLSETS
    assert pymacos_api.coverage(module)[2], "macos.{} is covered: take it off IN_PROGRESS".format(module)


@pytest.mark.parametrize("function", sorted(EXCLUDED))
def test_excluded_function_exists_and_is_not_used(function: str) -> None:
    module = function.partition(".")[0]

    assert function in pymacos_api.functions(module), "pymacos has no macos.{}".format(function)
    assert function in pymacos_api.coverage(module)[1], "macos.{} is used by a tool: take it off EXCLUDED".format(function)
    assert len(EXCLUDED[function]) > 20, "say why macos.{} can't be a tool".format(function)


def test_report_counts_every_function() -> None:
    report = pymacos_api.report()

    assert "volume             5 of 5    done" in report
    assert "functions of pymacos {}".format(macos.__version__) in report
