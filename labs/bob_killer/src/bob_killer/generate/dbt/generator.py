"""The dbt generator: a Workbook IR -> a dbt project for dbt Projects on Snowflake (§4).

Files land under ``dbt/``. One model per vectorized step and one per sheet and topological level
of scalar steps (D26). Steps are rendered by a ``Registry[StepHandler]`` keyed by step kind, so a
new kind needs one handler here (core IR rules). Models read only ``WB_INPUT_CELLS``, the ``lkp_*``
seeds, ``stg_parameters`` and other models; ``bk_oracle`` has only test children (D22).
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import jinja2
import yaml

from bob_killer.contracts.ir import (
    CellRef,
    CellValue,
    GeneratedProject,
    ParamExpr,
    Step,
    TargetConfig,
    WorkbookIR,
    iter_expr,
)
from bob_killer.generate.base import (
    CellValues,
    dbt_text,
    node_views,
    project,
    template_env,
    workbook_slug,
)
from bob_killer.generate.dbt.render import Scope, SqlRenderer, ident, sql_string
from bob_killer.ir.analysis import generated_steps, levels
from bob_killer.registry import Registry

PARAMETERS_MODEL = "stg_parameters"
ORACLE_SEED = "bk_oracle"
SEED_COLUMNS = ("sheet", "row", "col", "wire_json")
CELL_COLUMNS = {
    "sheet": "Excel sheet name.",
    "row": "Excel row, 1-based.",
    "col": "Excel column, 1-based.",
    "node_id": "IR node that computes the cell.",
    "value": "The cell value as a CellValue wire object (D21).",
}
SEED_COLUMN_DOCS = {
    "sheet": "Excel sheet name.",
    "row": "Excel row, 1-based, as text.",
    "col": "Excel column, 1-based, as text.",
    "wire_json": "The cell value as CellValue wire JSON text; a number is float.hex() text (D21).",
}
MART_COLUMNS = {
    **{k: v for k, v in CELL_COLUMNS.items() if k != "node_id"},
    "value_number": "The number for display only (BK_WIRE_DECODE_NUMBER); never used for parity.",
    "value_text": "The text of a text value.",
    "value_boolean": "The boolean of a boolean value.",
    "value_error": "The Excel error of an error value.",
}
CELL_TEST = "bk_unique_cell"
PARITY_TEST = "bk_exact_parity"
PARITY_TAG = "bk_parity"
FACT_MODEL = "fct_formula_cells"
MACROS = ("bk_fn", "bk_op", "bk_param", "bk_wire", "bk_ident")


@dataclass(frozen=True)
class Layout:
    """Where every IR node lives in the project."""

    ir: WorkbookIR
    levels: dict[str, int]
    sheet_ids: dict[str, str]
    model_of: dict[str, str] = field(default_factory=dict)


class StepHandler(Protocol):
    tags: tuple[str, ...]
    shared: bool  # True when several steps share one model (D26 levels)

    def model_name(self, step: Any, layout: Layout) -> str: ...

    def render(self, model: str, steps: Sequence[Any], ctx: Context) -> str: ...


@dataclass(frozen=True)
class Context:
    env: jinja2.Environment
    renderer: SqlRenderer
    layout: Layout

    def depends(self, steps: Iterable[Step]) -> tuple[str, ...]:
        uses = any(isinstance(e, ParamExpr) for s in steps for r in s.exprs() for e in iter_expr(r))
        return (PARAMETERS_MODEL,) if uses else ()

    def cells(self, model: str, rows: list[dict[str, str]], steps: Sequence[Step]) -> str:
        return self.env.get_template("int_cells.sql.j2").render(
            model=model, rows=rows, depends=self.depends(steps)
        )

    def row(self, ref: CellRef, node_id: str, value: str) -> dict[str, str]:
        return {
            "sheet": sql_string(ref.sheet),
            "row": str(ref.row),
            "col": str(ref.col),
            "node_id": sql_string(node_id),
            "value": value,
        }


def _origin_ref(step: Step) -> CellRef:
    rng = step.ranges()[0]
    return CellRef(sheet=rng.sheet, row=rng.row, col=rng.col)


class SingleCellHandler:
    """aggregate, lookup, conditional: one model per step with one cell row."""

    tags: tuple[str, ...] = ()
    shared = False

    def model_name(self, step: Any, layout: Layout) -> str:
        return f"int_{step.id}"

    def render(self, model: str, steps: Sequence[Any], ctx: Context) -> str:
        rows = [ctx.row(_origin_ref(s), s.id, ctx.renderer.scalar(s.expr)) for s in steps]
        return ctx.cells(model, rows, steps)


class ScalarLevelHandler(SingleCellHandler):
    """scalar_expr: grouped into one model per sheet and topological level (D26)."""

    shared = True

    def model_name(self, step: Any, layout: Layout) -> str:
        sheet = layout.sheet_ids[step.ranges()[0].sheet]
        return f"int_{sheet}__l{layout.levels[step.id]}"


class ColumnHandler:
    """column_expr: row-wise over its input, one row per cell of its origin column."""

    tags: tuple[str, ...] = ()
    shared = False

    def model_name(self, step: Any, layout: Layout) -> str:
        return f"int_{step.id}"

    def render(self, model: str, steps: Sequence[Any], ctx: Context) -> str:
        (step,) = steps
        rng = step.ranges()[0]
        over = next(i for i in ctx.layout.ir.inputs if i.id == step.over)
        span = over.ranges()[0]
        if rng.row < span.row or rng.last_row > span.last_row:
            raise ValueError(f"{step.id}: its rows are outside input {over.id}")
        scope = Scope(anchor_row=rng.row, height=rng.height, over=over.id)
        return ctx.env.get_template("int_column.sql.j2").render(
            model=model,
            depends=ctx.depends(steps),
            sheet=sql_string(rng.sheet),
            col=str(rng.col),
            node_id=sql_string(step.id),
            value=ctx.renderer.render(step.expr, scope),
            over_model=ctx.layout.model_of[over.id],
            first_row=rng.row,
            last_row=rng.last_row,
        )


class VbaHandler:
    """vba_procedure: one model per verified translation, one row per assigned cell (§6)."""

    tags: tuple[str, ...] = ("vba",)
    shared = False

    def model_name(self, step: Any, layout: Layout) -> str:
        return f"int_vba__{step.procedure}"

    def render(self, model: str, steps: Sequence[Any], ctx: Context) -> str:
        rows = [
            ctx.row(a.cell, s.id, ctx.renderer.scalar(a.expr)) for s in steps for a in s.assignments
        ]
        return ctx.cells(model, rows, steps)


step_handlers: Registry[StepHandler] = Registry("dbt step handlers")
step_handlers.add("scalar_expr", ScalarLevelHandler())
step_handlers.add("column_expr", ColumnHandler())
step_handlers.add("aggregate", SingleCellHandler())
step_handlers.add("lookup", SingleCellHandler())
step_handlers.add("conditional", SingleCellHandler())
step_handlers.add("vba_procedure", VbaHandler())


def layout(ir: WorkbookIR) -> Layout:
    lay = Layout(ir=ir, levels=levels(ir), sheet_ids={s.name: s.id for s in ir.sheets})
    lay.model_of.update({i.id: f"stg_input__{i.id}" for i in ir.inputs})
    lay.model_of.update({lk.id: f"stg_lookup__{lk.id}" for lk in ir.lookups})
    taken = set(lay.model_of.values())
    kind_of: dict[str, str] = {}
    for step in generated_steps(ir):
        handler = step_handlers.get(step.kind)
        model = handler.model_name(step, lay)
        seen = kind_of.setdefault(model, step.kind)
        if model in taken or (model in lay.model_of.values() and not handler.shared):
            raise ValueError(f"{step.id}: model name {model} is already used")
        if seen != step.kind:
            raise ValueError(f"{step.id}: model name {model} is used by another step kind")
        lay.model_of[step.id] = model
    return lay


def sql_renderer(ir: WorkbookIR) -> SqlRenderer:
    return SqlRenderer(ir, layout(ir).model_of)


def _columns(docs: dict[str, str]) -> list[dict[str, str]]:
    return [{"name": name, "description": text} for name, text in docs.items()]


def _model(name: str, description: str, columns: dict[str, str], **extra: Any) -> dict[str, Any]:
    return {
        "name": name,
        "description": dbt_text(description),
        "columns": _columns(columns),
        **extra,
    }


class DbtGenerator:
    step_handlers = step_handlers

    def generate(self, ir: WorkbookIR, target: TargetConfig, cells: CellValues) -> GeneratedProject:
        return _Build(ir, target, cells).run()


class _Build:
    """One generation: collects files and the schema entries of each directory."""

    def __init__(self, ir: WorkbookIR, target: TargetConfig, cells: CellValues) -> None:
        self.env = template_env("bob_killer.generate.dbt")
        self.env.filters.update(sql=sql_string, yq=yaml_scalar, to_yaml=to_yaml)
        self.env.globals["ident"] = ident
        self.ir, self.target, self.cells = ir, target, cells
        self.layout = layout(ir)
        self.ctx = Context(self.env, SqlRenderer(ir, self.layout.model_of), self.layout)
        self.lines = {nid: _line(self.env, v) for nid, v in node_views(ir).items()}
        self.files: dict[str, str] = {}
        self.entries: dict[str, list[dict[str, Any]]] = {
            "staging": [],
            "intermediate": [],
            "marts": [],
            "seeds": [],
        }

    def put(self, path: str, template: str, **values: Any) -> None:
        self.files[f"dbt/{path}"] = self.env.get_template(template).render(**values)

    def run(self) -> GeneratedProject:
        name = f"bk_{self.ir.source.sha256[:12]}"
        self.put(
            "dbt_project.yml", "dbt_project.yml.j2", project=name, target=self.target, ir=self.ir
        )
        self.put("profiles.yml", "profiles.yml.j2", project=name, target=self.target)
        for macro in MACROS:
            self.put(f"macros/{macro}.sql", f"macros/{macro}.sql")
        for test in (PARITY_TEST, CELL_TEST):
            self.put(f"tests/generic/{test}.sql", f"tests/{test}.sql")
        self.inputs()
        self.lookups()
        self.parameters()
        models = self.intermediate()
        self.oracle()
        self.marts(models)
        self.put("models/sources.yml", "schema.yml.j2", section="sources", entries=[_sources()])
        for folder in ("staging", "intermediate", "marts"):
            self.put(
                f"models/{folder}/_{folder}.yml",
                "schema.yml.j2",
                section="models",
                entries=self.entries[folder],
            )
        self.put(
            "seeds/_seeds.yml", "schema.yml.j2", section="seeds", entries=self.entries["seeds"]
        )
        self.put(
            "models/overview.md",
            "overview.md.j2",
            ir=self.ir,
            views=list(node_views(self.ir).values()),
            lines=self.lines,
            workbook=workbook_slug(self.ir),
        )
        return project(self.files)

    def inputs(self) -> None:
        for inp in self.ir.inputs:
            rng, model = inp.ranges()[0], self.layout.model_of[inp.id]
            self.put(
                f"models/staging/{model}.sql",
                "stg_input.sql.j2",
                model=model,
                sheet=sql_string(rng.sheet),
                first_row=rng.row,
                last_row=rng.last_row,
                first_col=rng.col,
                last_col=rng.last_col,
                height=rng.height,
                columns=[{"name": c.name, "col": rng.col + i} for i, c in enumerate(inp.columns)],
            )
            docs = {"_row": "Excel row, 1-based.", "_col": "Excel column of the first IR column."}
            docs |= {c.name: f"{c.label} ({c.dtype.value}) as a wire object." for c in inp.columns}
            self.entries["staging"].append(_model(model, self.lines[inp.id], docs))

    def lookups(self) -> None:
        for lk in self.ir.lookups:
            seed, model = f"lkp_{lk.id}", self.layout.model_of[lk.id]
            values = [(ref, self.cells.get(ref, CellValue.blank())) for ref in lk.cells()]
            self.seed(seed, self.lines[lk.id], values)
            self.put(
                f"models/staging/{model}.sql",
                "stg_lookup.sql.j2",
                model=model,
                seed=seed,
                node_id=sql_string(lk.id),
            )
            self.entries["staging"].append(_model(model, self.lines[lk.id], CELL_COLUMNS))

    def parameters(self) -> None:
        ids = [p.id for p in self.ir.parameters]
        self.put(
            f"models/staging/{PARAMETERS_MODEL}.sql",
            "stg_parameters.sql.j2",
            model=PARAMETERS_MODEL,
            parameters=ids,
        )
        docs = {"parameter_id": "IR parameter id.", "value": CELL_COLUMNS["value"]}
        text = f"One row per promoted parameter: {', '.join(ids) or 'none'}."
        self.entries["staging"].append(_model(PARAMETERS_MODEL, text, docs))

    def intermediate(self) -> list[str]:
        groups: dict[str, list[Step]] = {}
        for step in generated_steps(self.ir):
            groups.setdefault(self.layout.model_of[step.id], []).append(step)
        for model, group in sorted(groups.items()):
            handler = step_handlers.get(group[0].kind)
            sql = handler.render(model, group, self.ctx)
            self.files[f"dbt/models/intermediate/{model}.sql"] = sql
            extra: dict[str, Any] = {"data_tests": [CELL_TEST]}
            if handler.tags:
                extra["config"] = {"tags": list(handler.tags)}
            text = " ".join(self.lines[s.id] for s in group)
            self.entries["intermediate"].append(_model(model, text, CELL_COLUMNS, **extra))
        return sorted(groups)

    def oracle(self) -> None:
        refs = [c for s in generated_steps(self.ir) for c in s.cells()]
        if missing := [r for r in refs if r not in self.cells]:
            raise ValueError(f"{ORACLE_SEED}: no cached value for {missing[0]} (L5)")
        text = "Excel's cached value of every denominator cell. Only tests reference it (D22)."
        self.seed(ORACLE_SEED, text, [(r, self.cells[r]) for r in refs])

    def seed(self, name: str, text: str, values: list[tuple[CellRef, CellValue]]) -> None:
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(SEED_COLUMNS)
        writer.writerows((r.sheet, r.row, r.col, v.wire()) for r, v in values)
        self.files[f"dbt/seeds/{name}.csv"] = buf.getvalue()
        config = {"column_types": dict.fromkeys(SEED_COLUMNS, "varchar")}
        self.entries["seeds"].append(_model(name, text, SEED_COLUMN_DOCS, config=config))

    def marts(self, models: list[str]) -> None:
        self.put(
            f"models/marts/{FACT_MODEL}.sql",
            "fct_formula_cells.sql.j2",
            model=FACT_MODEL,
            models=models,
        )
        parity = {
            PARITY_TEST: {
                "arguments": {"oracle": ORACLE_SEED},
                "config": {"tags": [PARITY_TAG], "store_failures": True},
            }
        }
        text = "Every computed formula cell of the workbook, one row per cell."
        self.entries["marts"].append(
            _model(FACT_MODEL, text, CELL_COLUMNS, data_tests=[CELL_TEST, parity])
        )
        for out in self.ir.outputs:
            model = f"mart_{out.id}"
            self.put(
                f"models/marts/{model}.sql",
                "mart.sql.j2",
                model=model,
                step=out.step,
                step_model=self.layout.model_of[out.step],
            )
            text = f"{out.label} ({out.format.value}) at {', '.join(out.origin)}. {out.description}"
            self.entries["marts"].append(
                _model(model, text.strip(), MART_COLUMNS, data_tests=[CELL_TEST])
            )


class _NoAliases(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def to_yaml(value: Any) -> str:
    return yaml.dump(value, Dumper=_NoAliases, sort_keys=False, allow_unicode=True, width=100)


def yaml_scalar(value: str) -> str:
    """A YAML scalar for templates: JSON text is a valid double-quoted YAML scalar."""
    return json.dumps(value)


def _line(env: jinja2.Environment, view: dict[str, str]) -> str:
    return env.get_template("_node.md.j2").render(n=view).strip()


def _sources() -> dict[str, Any]:
    return {
        "name": "bk",
        "database": "{{ target.database }}",
        "schema": "{{ var('bk_host_schema') }}",
        "description": "The host schema of the run: input cells and the bronze landing copy.",
        "tables": [
            {
                "name": "WB_INPUT_CELLS",
                "description": "Input and frozen volatile cells of WB_CELLS, by bk_run_id (D22).",
                "columns": _columns({"run_id": "Run id.", **CELL_COLUMNS}),
            },
            {
                "name": "BRONZE_ROWS",
                "description": "The bronze landing copy, for lineage; no model reads it (§4.3).",
                "columns": _columns({"run_id": "Run id."}),
            },
        ],
    }
