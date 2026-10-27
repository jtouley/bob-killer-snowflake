"""The BK_* UDFs in Snowflake give the Python runtime's result for every golden corpus case.

A corpus case is one function or operator call inside a golden formula cell that the golden probe
evaluates (tests/golden/conftest.py): its argument values and the Python runtime's result, both
as wire objects (D21). Expected values are the runtime's own results, computed here.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from snowflake.snowpark import Session

import bob_killer.runtime.functions  # noqa: F401  (registers the Excel functions)
from bob_killer.contracts.graph import Expr
from bob_killer.extract import extract_workbook
from bob_killer.graph.dag import build_graph
from bob_killer.hosts.snowflake import udfs
from bob_killer.registry import functions
from bob_killer.runtime import wire
from bob_killer.runtime.coercion import Arg, UnsupportedValue
from bob_killer.service.workspace import graph_input
from bob_killer.verify.config import values_equal
from tests.conftest import MVP_GOLDENS, golden_workbook
from tests.golden.conftest import Evaluator, Ineligible
from tests.live.conftest import write_evidence

CASES = "BK_UDF_CASES"
BATCH = 500


class Recorder(Evaluator):
    """The probe's evaluator, keeping every call it makes: (function, argument values, result)."""

    calls: list[tuple[str, list[Arg], Arg]]

    def call(self, name: str, args: tuple[Expr, ...], sheet: str) -> Arg:
        values = [self.eval(a, sheet) for a in args]
        result: Arg = functions.get(name)(*values)  # type: ignore[assignment]
        self.calls.append((name, values, result))
        return result


def corpus(golden_id: str) -> list[tuple[str, list[Any], Any]]:
    """Unique (function, wire args, wire result) of every call in the golden's evaluated cells."""
    raw = extract_workbook(golden_workbook(golden_id))
    ev = Recorder(raw)
    seen: dict[str, tuple[str, list[Any], Any]] = {}
    for node in build_graph(graph_input(raw)).nodes:
        if node.ast is None:
            continue
        ev.calls = []
        try:
            ev.result(node)
        except (Ineligible, UnsupportedValue, LookupError):
            continue
        for name, values, result in ev.calls:
            args = [wire.encode(v) for v in values]
            key = json.dumps([name, args], sort_keys=True)
            seen.setdefault(key, (name, args, wire.encode(result)))
    return list(seen.values())


def _load(session: Session, cases: list[tuple[str, list[Any], Any]]) -> None:
    session.sql(f"CREATE OR REPLACE TABLE {CASES} (id NUMBER, fn VARCHAR, args VARIANT)").collect()
    for start in range(0, len(cases), BATCH):
        chunk = cases[start : start + BATCH]
        values = ", ".join("(?, ?, ?)" for _ in chunk)
        params: list[Any] = []
        for i, (name, args, _) in enumerate(chunk, start):
            params += [i, name, json.dumps(args)]
        session.sql(
            f"INSERT INTO {CASES} SELECT column1, column2, PARSE_JSON(column3) FROM VALUES {values}",
            params=params,
        ).collect()


@pytest.mark.parametrize("golden_id", MVP_GOLDENS)
def test_udfs_match_the_python_runtime_on_the_golden_corpus(
    session: Session, host_schema: str, golden_id: str
) -> None:
    session.use_schema(host_schema)
    cases = corpus(golden_id)
    assert cases, f"{golden_id}: the probe evaluated no call"
    _load(session, cases)
    names = sorted({name for name, _, _ in cases})
    query = " UNION ALL ".join(
        f"SELECT id, {udfs.udf_name(n)}(args) AS got FROM {CASES} WHERE fn = ?" for n in names
    )
    got = {int(r["ID"]): json.loads(r["GOT"]) for r in session.sql(query, params=names).collect()}
    assert sorted(got) == list(range(len(cases)))
    mismatches = [
        (name, args, expected, got[i])
        for i, (name, args, expected) in enumerate(cases)
        if not _same(expected, got[i])
    ]
    write_evidence(
        "udfs_live",
        f"{golden_id} corpus",
        f"cases {len(cases)}, functions {len(names)} {names}, mismatches {len(mismatches)}\n"
        + "\n".join(json.dumps(m) for m in mismatches[:20]),
    )
    assert mismatches == []


def _same(expected: Any, got: Any) -> bool:
    a, b = wire.decode_arg(expected), wire.decode_arg(got)
    if isinstance(a, tuple) or isinstance(b, tuple):
        return json.dumps(expected, sort_keys=True) == json.dumps(got, sort_keys=True)
    return values_equal(a, b)
