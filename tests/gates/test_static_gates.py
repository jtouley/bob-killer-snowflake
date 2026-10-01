"""Cheat fixtures for working-tree gates: no_oracle_literals, no_silent_skips, exact_parity."""

from __future__ import annotations

import pytest
from bk_gates.core import load_gates
from tests.gates.conftest import Project

ALLOWLIST = (
    "# Allowlist\n\n| id | named cell / test | root-cause class | issue |\n"
    "|----|----|----|----|\n"
    "| A1 | Sheet1!B2 | summation order | https://github.com/jtouley/sandbox/issues/9 |\n"
    "| A2 | Sheet1!B3 | rounding |  |\n"
)
COMPARATOR = (
    "def values_equal(expected: object, actual: object) -> bool:\n"
    "    return type(expected) is type(actual) and expected == actual\n"
)
BASE = {"ALLOWLIST.md": ALLOWLIST, "src/bob_killer/verify/config.py": COMPARATOR}

CLEAN_FILES = {
    "tests/unit/test_ok.py": (
        "from tests.oracle_values import oracle\n\n\n"
        "def test_ok() -> None:\n    assert f() == oracle('sum')\n    assert f() is None\n"
        "    assert ok() is True\n    assert not missing()\n"
    ),
    "tests/unit/test_allowed.py": (
        "import pytest\n\n\n"
        "@pytest.mark.xfail(reason='summation order')  # allow: A1\n"
        "def test_x() -> None:\n    assert f() == g()\n"
    ),
    "tests/gates/test_gate_literals.py": "def test_g() -> None:\n    assert rc() == 1\n",
}

CHEATS: list[tuple[dict[str, str], str]] = [
    ({"tests/unit/test_c.py": "def test_c():\n    assert f() == 6.0\n"}, "no_oracle_literals/literal"),
    ({"tests/integration/test_c.py": "def test_c():\n    assert 'x' == f()\n"}, "no_oracle_literals/literal"),
    ({"tests/unit/test_c.py": "def test_c():\n    assert f() == -3\n"}, "no_oracle_literals/literal"),
    ({"tests/unit/test_c.py": "def test_c():\n    assert f() == [1, 2]\n"}, "no_oracle_literals/literal"),
    (
        {"tests/unit/test_c.py": "EXPECTED = 6.0\n\n\ndef test_c():\n    assert f() == EXPECTED\n"},
        "no_oracle_literals/literal",
    ),
    ({"tests/unit/test_c.py": "import pytest\n\n\n@pytest.mark.xfail\ndef test_c():\n    assert f()\n"}, "no_silent_skips/unallowed"),
    ({"tests/unit/test_c.py": "import pytest\n\n\ndef test_c():\n    pytest.skip('later')\n"}, "no_silent_skips/unallowed"),
    ({"tests/unit/test_c.py": "import pytest\n\n\ndef test_c():\n    assert f() == pytest.approx(g())\n"}, "no_silent_skips/unallowed"),
    ({"tests/unit/test_c.py": "from pytest import approx\n\n\ndef test_c():\n    assert f() == approx(g())\n"}, "no_silent_skips/unallowed"),
    ({"tests/unit/test_c.py": "import pytest as pt\n\n\n@pt.mark.skip\ndef test_c():\n    assert f()\n"}, "no_silent_skips/unallowed"),
    ({"tests/unit/test_c.py": "import math\n\n\ndef test_c():\n    assert math.isclose(f(), g())\n"}, "no_silent_skips/unallowed"),
    ({"tests/unit/test_c.py": "import pytest\n\n\n@pytest.mark.skip  # allow: NOPE\ndef test_c():\n    assert f()\n"}, "no_silent_skips/unknown-allow-id"),
    ({"tests/unit/test_c.py": "import pytest\n\n\n@pytest.mark.skip  # allow: A2\ndef test_c():\n    assert f()\n"}, "no_silent_skips/unknown-allow-id"),
    ({"src/bob_killer/verify/config.py": "def other() -> None:\n    pass\n"}, "exact_parity/missing-comparator"),
    (
        {"src/bob_killer/verify/config.py": COMPARATOR.replace("actual: object)", "actual: object, atol: float = 1e-9)")},
        "exact_parity/tolerance-param",
    ),
    (
        {"src/bob_killer/verify/config.py": COMPARATOR.replace("actual: object)", "actual: object, **kwargs: object)")},
        "exact_parity/tolerance-param",
    ),
    ({"src/bob_killer/verify/diff.py": "TOLERANCE = 1e-12\n"}, "exact_parity/tolerance-constant"),
    ({"src/bob_killer/verify/diff.py": "import math\n\n\ndef same(a: float, b: float) -> bool:\n    return math.isclose(a, b)\n"}, "exact_parity/approx-call"),
]

STATIC_GATES = ("no_oracle_literals", "no_silent_skips", "exact_parity")


def _rules(p: Project) -> set[str]:
    gates = load_gates()
    return {v.rule for name in STATIC_GATES for v in gates[name].check(p.context())}


def test_clean_project_passes(project: Project) -> None:
    project.write({**BASE, **CLEAN_FILES})
    assert _rules(project) == set()


@pytest.mark.parametrize(("files", "rule"), CHEATS, ids=[f"{i}-{r}" for i, (_, r) in enumerate(CHEATS)])
def test_cheat_is_rejected(project: Project, files: dict[str, str], rule: str) -> None:
    project.write({**BASE, **files})
    assert rule in _rules(project)
