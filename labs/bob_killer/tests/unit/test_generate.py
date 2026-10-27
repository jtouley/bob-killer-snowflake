"""generate/: the Generator protocol, the dbt generator (§4) and the docs generator (§4.6).

Expected properties come from tests/oracle/dbt_mapping.json (the §4 table) and from the IR,
never from literals. Golden hash manifests (D32) are drift guards only and live elsewhere.
"""

from __future__ import annotations

import csv
import fnmatch
import io
import json
import re
from collections.abc import Callable, Iterator, Mapping
from functools import cache
from pathlib import Path, PurePosixPath
from typing import Any

import jinja2
import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.unit.conftest import Json, sample_cells, sample_ir, sample_target

MAPPING: Json = json.loads((Path(__file__).parents[1] / "oracle" / "dbt_mapping.json").read_text())
STEP_KINDS: list[str] = json.loads(
    (Path(__file__).parents[1] / "oracle" / "ir_step_kinds.json").read_text()
)["step_kinds"]


def _load_generators() -> None:
    import bob_killer.generate.dbt  # noqa: F401  (registers "dbt")
    import bob_killer.generate.docs  # noqa: F401  (registers "docs")


@cache
def project() -> Mapping[str, str]:
    from bob_killer.generate.base import run_generators

    _load_generators()
    ir = sample_ir()
    return run_generators(ir, sample_target(), sample_cells(ir)).by_path()


def files_matching(pattern: str) -> dict[str, str]:
    return {p: c for p, c in project().items() if fnmatch.fnmatchcase(p, pattern)}


# --- dbt Jinja, rendered with recording stubs (what dbt parse would resolve) ------------------------


class Recorder:
    def __init__(self) -> None:
        self.refs: set[str] = set()
        self.sources: set[tuple[str, str]] = set()

    def env(self) -> jinja2.Environment:
        env = jinja2.Environment(undefined=jinja2.StrictUndefined)

        def ref(name: str) -> str:
            self.refs.add(name)
            return f"REF_{name}"

        def source(src: str, table: str) -> str:
            self.sources.add((src, table))
            return f"SRC_{table}"

        def stub(*_: Any, **__: Any) -> str:
            return "X"

        env.globals.update(ref=ref, source=source, var=stub, config=stub)
        env.globals.update(dict.fromkeys(project_macros(), stub))
        return env

    def render(self, text: str) -> str:
        return self.env().from_string(text).render()


def project_macros() -> set[str]:
    """Every macro the generated project defines; any other call in a model is undefined."""
    text = "\n".join(files_matching("dbt/macros/*.sql").values())
    return set(re.findall(r"\{% macro (\w+)\(", text))


def model_sql() -> dict[str, str]:
    return {
        PurePosixPath(p).stem: c
        for p, c in files_matching("dbt/models/*").items()
        if p.endswith(".sql")
    }


def seed_names() -> set[str]:
    return {PurePosixPath(p).stem for p in files_matching("dbt/seeds/*.csv")}


def yaml_files() -> dict[str, Any]:
    return {p: yaml.safe_load(c) for p, c in project().items() if p.endswith((".yml", ".yaml"))}


def yaml_entries(section: str) -> dict[str, Json]:
    """Entries of the schema files (dbt_project.yml holds the same keys as config maps)."""
    lists = [doc.get(section) for doc in yaml_files().values()]
    return {e["name"]: e for entries in lists if isinstance(entries, list) for e in entries}


# --- the §4 table, row by row ---------------------------------------------------------------------


def _base() -> dict[str, str]:
    ir, target = sample_ir(), sample_target()
    stem = re.sub(r"[^a-z0-9]+", "_", PurePosixPath(ir.source.file).stem.lower()).strip("_")
    return {
        "project": f"bk_{ir.source.sha256[:12]}",
        "sha256": ir.source.sha256,
        "run_id": target.run_id,
        "deploy_schema": target.deploy_schema,
        "role": target.role,
        "warehouse": target.warehouse,
        "database": target.database,
        "workbook": stem,
    }


def _sheet_id(origin: str) -> str:
    from bob_killer.contracts.ir import cell_range

    name = cell_range(origin).sheet
    return next(s.id for s in sample_ir().sheets if s.name == name)


def instances(row: Json) -> list[dict[str, str]]:
    ir, base = sample_ir(), _base()
    one = [base]
    table: dict[str, Callable[[], list[dict[str, str]]]] = {
        "inputs": lambda: [{**base, "id": n.id} for n in ir.inputs],
        "lookups": lambda: [{**base, "id": n.id} for n in ir.lookups],
        "parameters": lambda: [
            {**base, "id": p.id, "default_hex": p.default.h or ""} for p in ir.parameters
        ],
        "step": lambda: [
            {
                **base,
                "id": s.id,
                "sheet": _sheet_id(s.origin[0]),
                "over": getattr(s, "over", ""),
                "lookup": getattr(s, "lookup", ""),
                "procedure": getattr(s, "procedure", ""),
            }
            for s in ir.steps
            if s.kind == row.get("kind")
        ],
        "outputs": lambda: [
            {**base, "id": o.id, "step": o.step, "label": o.label} for o in ir.outputs
        ],
        "descriptions": lambda: [{**base, "node_id": n.id} for n in ir.nodes()],
        "unsupported": lambda: [
            {**base, "kind": u.kind, "reason": u.reason} for u in ir.unsupported
        ],
    }
    return table.get(row["ir_node"], lambda: one)()


def fill(value: Any, slots: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        return re.sub(r"\{(\w+)\}", lambda m: slots[m.group(1)], value)
    if isinstance(value, list):
        return [fill(v, slots) for v in value]
    if isinstance(value, dict):
        return {k: fill(v, slots) for k, v in value.items()}
    return value


def walk(doc: Any, path: list[Any]) -> Any:
    for step in path:
        if isinstance(step, str):
            doc = doc[step]
        elif "name" in step:
            doc = next(item for item in doc if item.get("name") == step["name"])
        else:
            doc = next(item for item in doc if step["key"] in item)[step["key"]]
    return doc


ROWS = MAPPING["rows"]


@pytest.mark.parametrize(
    "row", ROWS, ids=[f"{r['ir_node']}:{r.get('kind', r['artifact'])}" for r in ROWS]
)
def test_ir_node_maps_to_its_dbt_artifact(row: Json) -> None:
    slot_sets = instances(row)
    assert slot_sets, f"the sample IR has no {row['ir_node']} node"
    for slots in slot_sets:
        spec = fill(row, slots)
        matched: dict[str, str] = {}
        for pattern in spec["files"]:
            found = files_matching(pattern)
            assert found, pattern
            matched |= found
        text = "\n".join(matched.values())
        for needle in spec.get("contains", []):
            assert needle in text, needle
        for needle in spec.get("excludes", []):
            assert needle not in text, needle
        absent_in = "\n".join(files_matching(spec.get("absent_from", "")).values())
        for needle in spec.get("absent", []):
            assert needle not in absent_in, needle
        for check in spec.get("yaml", []):
            value = walk(yaml.safe_load(project()[check["file"]]), check["path"])
            if "equals" in check:
                assert value == check["equals"], check
            if "includes" in check:
                assert check["includes"] in value, check
            if "all_values" in check:
                assert value and set(value.values()) == {check["all_values"]}, check


# --- protocol and registry ------------------------------------------------------------------------


def test_generators_are_registered() -> None:
    from bob_killer import registry
    from bob_killer.generate.base import Generator

    _load_generators()
    for name in MAPPING["generators"]:
        assert isinstance(registry.generators.get(name), Generator), name


class StubGenerator:
    def __init__(self, path: str) -> None:
        from bob_killer.registry import Registry

        self.path = path
        self.step_handlers: Registry[object] = Registry("stub handlers")

    def generate(self, ir: Any, target: Any, cells: Any) -> Any:
        from bob_killer.contracts.ir import GeneratedFile, GeneratedProject

        return GeneratedProject(files=(GeneratedFile.of(self.path, ir.source.sha256),))


def test_run_generators_iterates_the_registry_in_name_order() -> None:
    from bob_killer.generate.base import run_generators
    from bob_killer.registry import Registry

    reg: Registry[object] = Registry("generators")
    paths = ["zeta/out.txt", "alpha/out.txt"]
    for name, path in zip(["b", "a"], paths, strict=True):
        reg.add(name, StubGenerator(path))
    ir = sample_ir()
    out = run_generators(ir, sample_target(), {}, generators=reg)
    assert [f.path for f in out.files] == sorted(paths)
    assert {f.content for f in out.files} == {ir.source.sha256}


def test_run_generators_rejects_a_path_written_twice() -> None:
    from bob_killer.generate.base import run_generators
    from bob_killer.registry import Registry

    reg: Registry[object] = Registry("generators")
    reg.add("a", StubGenerator("same.txt"))
    reg.add("b", StubGenerator("same.txt"))
    with pytest.raises(ValueError, match="same.txt"):
        run_generators(sample_ir(), sample_target(), {}, generators=reg)


@pytest.mark.parametrize("generator", MAPPING["generators"])
@pytest.mark.parametrize("kind", STEP_KINDS)
def test_every_step_kind_has_a_handler(generator: str, kind: str) -> None:
    from bob_killer import registry

    _load_generators()
    handlers = registry.generators.get(generator).step_handlers  # type: ignore[attr-defined]
    assert kind in handlers
    assert set(handlers.names()) == set(registry.step_kinds.names())


def test_generation_is_deterministic() -> None:
    from bob_killer.generate.base import run_generators

    _load_generators()
    ir = sample_ir()
    again = run_generators(ir, sample_target(), sample_cells(ir)).by_path()
    assert again == dict(project())


def _review(where: str) -> Callable[[Json], None]:
    def mutate(data: Json) -> None:
        if where == "output":
            data["outputs"][0]["name_status"] = "needs_review"
        else:
            step = next(s for s in data["steps"] if s["id"] == data["outputs"][0]["step"])
            step["name_status"] = "needs_review"

    return mutate


@pytest.mark.parametrize("where", ["output", "output step"])
def test_generation_fails_while_an_output_facing_name_needs_review(where: str) -> None:
    from bob_killer.generate.base import NamesNeedReview, run_generators

    _load_generators()
    ir = sample_ir(_review(where))
    with pytest.raises(NamesNeedReview, match=ir.outputs[0].id):
        run_generators(ir, sample_target(), sample_cells(ir))


# --- expression renderer (D20) --------------------------------------------------------------------


def _exprs() -> st.SearchStrategy[Any]:
    from bob_killer.contracts.ir import (
        UNARY_OPERATORS,
        CallExpr,
        CellExpr,
        CellValue,
        ExcelError,
        LiteralExpr,
        Operator,
        OpExpr,
        ParamExpr,
        RangeExpr,
    )

    ir = sample_ir()
    cells = [c for n in (*ir.inputs, *ir.lookups, *ir.steps) for c in n.cells()]
    ranges = [r for n in (*ir.inputs, *ir.lookups) for r in n.ranges()]
    values = st.one_of(
        st.floats(allow_nan=False, allow_infinity=False).map(CellValue.number),
        st.text().map(CellValue.text),
        st.booleans().map(CellValue.boolean),
        st.sampled_from(list(ExcelError)).map(CellValue.error),
        st.just(CellValue.blank()),
    )
    leaves = st.one_of(
        st.sampled_from(cells).map(lambda c: CellExpr(sheet=c.sheet, row=c.row, col=c.col)),
        st.sampled_from([p.id for p in ir.parameters]).map(lambda p: ParamExpr(id=p)),
        values.map(lambda v: LiteralExpr(value=v)),
    )
    range_leaf = st.sampled_from(ranges).map(
        lambda r: RangeExpr(
            sheet=r.sheet, row=r.row, col=r.col, last_row=r.last_row, last_col=r.last_col
        )
    )

    def grow(children: st.SearchStrategy[Any]) -> st.SearchStrategy[Any]:
        unary = st.tuples(st.sampled_from(sorted(UNARY_OPERATORS)), children).map(
            lambda t: OpExpr(op=t[0], args=(t[1],))
        )
        binary = st.tuples(
            st.sampled_from([o for o in Operator if o not in UNARY_OPERATORS]), children, children
        ).map(lambda t: OpExpr(op=t[0], args=(t[1], t[2])))
        calls = st.tuples(
            st.sampled_from(["SUM", "IF", "VLOOKUP", "ROUND", "STDEV.S"]),
            st.lists(st.one_of(children, range_leaf), max_size=3),
        ).map(lambda t: CallExpr(name=t[0], args=tuple(t[1])))
        return st.one_of(unary, binary, calls)

    return st.recursive(leaves, grow, max_leaves=12)


STRING_LITERAL = re.compile(r"'(?:[^'\\]|\\.)*'")


@settings(max_examples=200, deadline=None)
@given(data=st.data())
def test_non_exact_nodes_always_render_as_udf_calls(data: st.DataObject) -> None:
    from bob_killer.contracts.ir import CallExpr, OpExpr, iter_expr
    from bob_killer.generate.dbt.generator import sql_renderer

    expr = data.draw(_exprs())
    sql = sql_renderer(sample_ir()).scalar(expr)
    bare = STRING_LITERAL.sub("''", sql)
    for operator in MAPPING["bare_arithmetic"]:
        assert operator not in bare, (operator, sql)
    nodes = list(iter_expr(expr))
    assert bare.count("bk_fn(") == sum(isinstance(n, CallExpr) for n in nodes)
    assert bare.count("bk_op(") == sum(isinstance(n, OpExpr) for n in nodes)
    Recorder().render(sql)


def test_only_the_sql_exact_set_renders_without_a_udf() -> None:
    from bob_killer.contracts.ir import iter_expr
    from bob_killer.generate.dbt.generator import sql_renderer

    renderer = sql_renderer(sample_ir())
    for step in sample_ir().steps:
        for root in step.exprs():
            for node in iter_expr(root):
                if node.type in MAPPING["sql_exact_expr_types"]:
                    sql = renderer.scalar(node)
                    for macro in MAPPING["udf_macros"]:
                        assert macro not in sql, sql


# --- whole-project properties ---------------------------------------------------------------------


def test_every_generated_yaml_parses() -> None:
    docs = yaml_files()
    assert docs
    for path, doc in docs.items():
        assert isinstance(doc, dict), path


def _render_all() -> tuple[dict[str, Recorder], Recorder]:
    """One recorder per model (its refs and sources), one for every YAML description."""
    per_model = {}
    for name, sql in model_sql().items():
        rec = Recorder()
        rec.render(sql)
        per_model[name] = rec
    described = Recorder()
    for section in ("models", "seeds", "sources"):
        for entry in yaml_entries(section).values():
            texts = [entry.get("description", "")]
            texts += [c.get("description", "") for c in entry.get("columns") or []]
            for t in texts:
                described.render(t)
    return per_model, described


def test_every_ref_resolves_inside_the_project() -> None:
    per_model, _ = _render_all()
    known = set(per_model) | seed_names()
    declared = {
        (src["name"], table["name"])
        for src in yaml_entries("sources").values()
        for table in src.get("tables") or []
    }
    for name, rec in per_model.items():
        assert rec.refs <= known, (name, rec.refs - known)
        assert rec.sources <= declared, (name, rec.sources - declared)
    for name in yaml_entries("models"):
        assert name in per_model, name
    for name in yaml_entries("seeds"):
        assert name in seed_names(), name
    for entry in yaml_entries("models").values():
        for test in entry.get("data_tests") or []:
            for args in test.values() if isinstance(test, dict) else []:
                for target in (args.get("arguments") or {}).values():
                    assert target in known, target


def test_models_read_only_inputs_lookup_seeds_and_other_models() -> None:
    per_model, _ = _render_all()
    seeds = seed_names()
    for name, rec in per_model.items():
        assert {t for _, t in rec.sources} <= set(MAPPING["model_sources"]), name
        for ref in rec.refs & seeds:
            assert ref.startswith(MAPPING["lookup_seed_prefix"]), (name, ref)


def test_oracle_seed_has_only_test_children() -> None:
    per_model, _ = _render_all()
    oracle = MAPPING["oracle_seed"]
    assert oracle in seed_names()
    for name, rec in per_model.items():
        assert oracle not in rec.refs, name
    test_args = [
        target
        for entry in yaml_entries("models").values()
        for test in entry.get("data_tests") or []
        if isinstance(test, dict)
        for args in test.values()
        for target in (args.get("arguments") or {}).values()
    ]
    assert oracle in test_args


def test_every_model_seed_and_column_is_described() -> None:
    models = yaml_entries("models")
    assert set(models) == set(model_sql())
    assert set(yaml_entries("seeds")) == seed_names()
    for name, entry in (models | yaml_entries("seeds")).items():
        assert entry.get("description"), name
        assert entry.get("columns"), name
        for col in entry["columns"]:
            assert col.get("description"), (name, col.get("name"))


def test_every_cell_model_carries_the_cell_key_test() -> None:
    cell_models = {
        PurePosixPath(p).stem
        for d in MAPPING["cell_model_dirs"]
        for p in files_matching(f"{d}*.sql")
    }
    assert cell_models
    models = yaml_entries("models")
    for name in cell_models:
        tests = [
            next(iter(t)) if isinstance(t, dict) else t
            for t in models[name].get("data_tests") or []
        ]
        assert MAPPING["cell_test"] in tests, name


def test_descriptions_render_as_plain_text_in_dbt() -> None:
    _render_all()  # raises on any Jinja that user text injected into SQL or YAML


def _csv_rows(path: str) -> Iterator[dict[str, str]]:
    yield from csv.DictReader(io.StringIO(project()[path]))


def _seed_cells() -> dict[str, set[Any]]:
    from bob_killer.contracts.ir import VbaProcedureStep, VbaStatus

    ir = sample_ir()
    generated = [
        s
        for s in ir.steps
        if not isinstance(s, VbaProcedureStep) or s.status is VbaStatus.TRANSLATED_VERIFIED
    ]
    seeds = {
        f"dbt/seeds/{MAPPING['lookup_seed_prefix']}{n.id}.csv": set(n.cells()) for n in ir.lookups
    }
    seeds[f"dbt/seeds/{MAPPING['oracle_seed']}.csv"] = {c for s in generated for c in s.cells()}
    return seeds


@pytest.mark.parametrize("path", sorted(_seed_cells()))
def test_seed_rows_decode_to_the_cell_values(path: str) -> None:
    from bob_killer.contracts.ir import CellRef, CellValue

    cells = sample_cells(sample_ir())
    rows = list(_csv_rows(path))
    assert list(rows[0]) == MAPPING["oracle_header"]
    seen = set()
    for row in rows:
        ref = CellRef(sheet=row["sheet"], row=int(row["row"]), col=int(row["col"]))
        assert CellValue.model_validate_json(row["wire_json"]) == cells[ref], ref
        seen.add(ref)
    assert seen == _seed_cells()[path]
    assert len(rows) == len(seen)


def test_seeds_are_text_columns_only() -> None:
    for name, entry in yaml_entries("seeds").items():
        types = entry["config"]["column_types"]
        assert set(types) == set(MAPPING["oracle_header"]), name


# --- docs (§4.6) ----------------------------------------------------------------------------------


def test_docs_page_lists_every_ir_node() -> None:
    ir = sample_ir()
    (page,) = files_matching(f"docs/{_base()['workbook']}.md").values()
    expected = [n.id for n in ir.nodes()] + [o.id for o in ir.outputs]
    expected += [s.name for s in ir.sheets] + [u.reason for u in ir.unsupported]
    expected += [v.procedure for v in ir.vba] + [w for v in ir.vba for w in v.writes]
    expected += [s.formula for s in ir.steps if hasattr(s, "formula")]
    expected += [s.fingerprint for s in ir.steps if hasattr(s, "fingerprint")]
    for needle in expected:
        assert needle in page, needle


def test_dbt_docs_blocks_reuse_the_docs_page_text() -> None:
    (page,) = files_matching(f"docs/{_base()['workbook']}.md").values()
    blocks = re.findall(
        r"\{% docs (bk_\w+) %\}\n(.*?)\n\{% enddocs %\}",
        project()["dbt/models/overview.md"],
        re.DOTALL,
    )
    assert {name for name, _ in blocks} == {f"bk_{n.id}" for n in sample_ir().nodes()}
    for name, body in blocks:
        shown = Recorder().render(body)  # dbt renders a docs block as Jinja
        assert shown.strip() and shown in page, name


# --- the UDF calling convention (hosts/snowflake/udfs.py) and lazy IF ------------------------------


def _render() -> Any:
    from bob_killer.generate.dbt import render

    return render


@settings(max_examples=200, deadline=None)
@given(data=st.data())
def test_every_udf_call_takes_its_arguments_as_one_array(data: st.DataObject) -> None:
    from bob_killer.contracts.ir import CallExpr, OpExpr, iter_expr
    from bob_killer.generate.dbt.generator import sql_renderer

    expr = data.draw(_exprs())
    bare = STRING_LITERAL.sub("''", sql_renderer(sample_ir()).scalar(expr))
    calls = sum(isinstance(n, CallExpr | OpExpr) for n in iter_expr(expr))
    assert bare.count("}}(" + _render().ARGS + "(") == calls


def test_a_one_cell_reference_argument_is_a_one_element_array() -> None:
    from bob_killer.contracts.ir import CallExpr, CellExpr
    from bob_killer.generate.dbt.generator import sql_renderer

    renderer = sql_renderer(sample_ir())
    ref = next(c for s in sample_ir().steps for c in s.cells())
    cell = CellExpr(sheet=ref.sheet, row=ref.row, col=ref.col)
    args = _render().ARGS
    sql = renderer.scalar(CallExpr(name="SUM", args=(cell,)))
    assert sql.endswith(f"({args}({args}({renderer.scalar(cell)})))")


def test_a_range_argument_carries_its_column_count() -> None:
    from bob_killer.contracts.ir import RANGE_CELLS, RANGE_COLUMNS, RangeExpr
    from bob_killer.generate.dbt.generator import sql_renderer

    rng = next(r for s in sample_ir().steps for r in s.ranges())
    expr = RangeExpr(
        sheet=rng.sheet, row=rng.row, col=rng.col, last_row=rng.last_row, last_col=rng.last_col
    )
    sql = sql_renderer(sample_ir()).scalar(expr)
    assert sql.startswith(f"OBJECT_CONSTRUCT('{RANGE_COLUMNS}', {rng.width}, '{RANGE_CELLS}', ")


def test_if_binds_its_choice_once_and_renders_each_branch_once() -> None:
    from bob_killer.contracts.ir import CallExpr, CellValue, LiteralExpr
    from bob_killer.generate.dbt.generator import sql_renderer

    render = _render()
    renderer = sql_renderer(sample_ir())
    test, yes, no = (LiteralExpr(value=CellValue.text(t)) for t in ("test", "yes", "no"))
    marks = tuple(LiteralExpr(value=CellValue.number(m)) for m in render.IF_BRANCHES)
    sql = renderer.scalar(CallExpr(name="IF", args=(test, yes, no)))
    choose = renderer.scalar(CallExpr(name="IF", args=(test, *marks)))
    once = [choose, *(renderer.scalar(b) for b in (yes, no))]
    assert [sql.count(part) for part in once] == [len([part]) for part in once]
    assert sql.count("bk_fn(") == sql.count(choose)
    then = [sql.index(f"THEN {renderer.scalar(b)}") for b in (yes, no)]
    assert then == sorted(then)


def test_every_step_cell_value_is_unwrapped_and_shows_blank_as_zero() -> None:
    from bob_killer.generate.dbt.generator import sql_renderer

    renderer = sql_renderer(sample_ir())
    files = project()
    text = "\n".join(v for k, v in files.items() if k.startswith("dbt/models/intermediate/"))
    for step in sample_ir().steps:
        if step.kind == "scalar_expr":
            assert _render().cell_value(renderer.scalar(step.expr)) in text, step.id


# --- the generate stage (generate/stage.py) and its source columns --------------------------------


class RecordingIO:
    """A GenerateIO over one golden's lift and cache; it records what the stage writes."""

    def __init__(self, golden_id: str, *, reviewed: bool = True) -> None:
        from bob_killer.extract import extract_workbook
        from bob_killer.hosts.snowflake.reviews import lifted
        from bob_killer.ir.cells import cached_values
        from bob_killer.ir.reviews import top_choice_reviews
        from tests.conftest import golden_workbook

        data = golden_workbook(golden_id)
        self.ir = lifted(data)
        self.values = cached_values(extract_workbook(data))
        review = top_choice_reviews(self.ir, reviewer="r", reason="why")
        self.review = review.reviews if reviewed else ()
        self.projects: list[Any] = []
        self.rows: list[Any] = []

    def load_ir(self, run_id: str) -> Any:
        return self.ir

    def cell_values(self, run_id: str) -> Any:
        return self.values

    def reviews(self, ir: Any) -> Any:
        return self.review

    def target(self, run_id: str) -> Any:
        return sample_target().model_copy(update={"run_id": run_id})

    def write_project(self, run_id: str, project: Any) -> None:
        self.projects.append(project)

    def write_input_cells(self, run_id: str, rows: Any) -> None:
        self.rows.append(rows)


RUN_ID = "ab" * 16


@pytest.mark.parametrize("golden_id", ["mt_dot_budget", "sgec_current"])
def test_generate_stage_writes_every_generated_file_and_the_input_cells(golden_id: str) -> None:
    from bob_killer.generate.base import run_generators
    from bob_killer.generate.stage import generate_stage
    from bob_killer.ir.reviews import apply_reviews

    io = RecordingIO(golden_id)
    generate_stage(io)(RUN_ID)
    expected = run_generators(apply_reviews(io.ir, io.review), io.target(RUN_ID), io.values)
    assert io.projects == [expected]
    ((rows),) = io.rows
    cells = [(n.id, ref) for n in io.ir.inputs for ref in n.cells()]
    got = [(r.node_id, r.sheet, r.cell_row, r.cell_col, r.value, r.run_id) for r in rows]
    want = [(nid, ref.sheet, ref.row, ref.col, io.values[ref], RUN_ID) for nid, ref in cells]
    assert got == want


def test_generate_stage_fails_while_names_await_review() -> None:
    from bob_killer.generate.base import NamesNeedReview
    from bob_killer.generate.stage import generate_stage

    io = RecordingIO("mt_dot_budget", reviewed=False)
    with pytest.raises(NamesNeedReview):
        generate_stage(io)(RUN_ID)
    assert io.projects == io.rows == []


def test_generate_stage_registers_once_and_only_when_asked() -> None:
    from bob_killer import registry
    from bob_killer.generate import stage

    assert stage.STAGE_NAME not in registry.stages
    io = RecordingIO("mt_dot_budget")
    stage.register_stages(io)
    stage.register_stages(io)
    assert registry.stages.names() == (stage.STAGE_NAME,)


def test_staging_models_read_the_input_cells_by_their_contract_columns() -> None:
    from bob_killer.contracts.workbook import WbInputCell

    files = project()
    staging = [v for k, v in files.items() if k.startswith("dbt/models/staging/stg_input__")]
    assert staging
    for text in staging:
        for name in WbInputCell.model_fields:
            if name != "node_id":
                assert f"bk_ident('{name.upper()}')" in text, name


@pytest.mark.parametrize("golden_id", ["mt_dot_budget", "sgec_current"])
def test_a_range_over_step_cells_reads_each_owning_model_once(golden_id: str) -> None:
    """One select per model that owns cells of the range, not one per owning step."""
    from bob_killer.contracts.ir import Input, RangeExpr, iter_expr
    from bob_killer.generate.dbt.generator import sql_renderer

    io = RecordingIO(golden_id)
    renderer = sql_renderer(io.ir)
    checked = 0
    for step in io.ir.steps:
        for e in iter_expr(step.expr):
            if not isinstance(e, RangeExpr):
                continue
            owners = {renderer.owner_of(c) for c in e.as_range().cells()}
            models = {renderer.model_of[o.id] for o in owners if not isinstance(o, Input)}
            sql = renderer.scalar(e)
            assert sql.count("SELECT m.") == len(models), step.origin
            checked += len(models)
    assert checked


@pytest.mark.parametrize("golden_id", ["mt_dot_budget", "sgec_current"])
def test_no_model_calls_more_udfs_than_one_snowflake_query_runs(golden_id: str) -> None:
    from bob_killer.generate.base import run_generators
    from bob_killer.generate.dbt.generator import MAX_UDF_CALLS
    from bob_killer.ir.reviews import apply_reviews

    io = RecordingIO(golden_id)
    files = run_generators(apply_reviews(io.ir, io.review), io.target(RUN_ID), io.values)
    models = {p: t for p, t in files.by_path().items() if p.startswith("dbt/models/")}
    for path, text in models.items():
        bare = STRING_LITERAL.sub("''", text)
        assert bare.count("bk_fn(") + bare.count("bk_op(") <= MAX_UDF_CALLS, path
