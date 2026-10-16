"""The docs target (§4.6): one Markdown page per workbook, from IR labels and descriptions.

Deterministic templates only; no LLM writes docs. The node text comes from the shared partial
``_node.md.j2``, which the dbt generator reuses for ``overview.md`` (the dbt docs archive).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from bob_killer import registry
from bob_killer.contracts.ir import GeneratedProject, TargetConfig, WorkbookIR
from bob_killer.generate.base import CellValues, node_views, project, template_env, workbook_slug
from bob_killer.registry import Registry

StepDetail = Callable[[Any], str]
step_handlers: Registry[StepDetail] = Registry("docs step handlers")
step_handlers.add("scalar_expr", lambda s: "One scalar cell.")
step_handlers.add(
    "column_expr", lambda s: f"Vectorized over input `{s.over}`, {s.ranges()[0].height} rows."
)
step_handlers.add("aggregate", lambda s: "Aggregates its ranges in Excel order.")
step_handlers.add("lookup", lambda s: f"Looks up in `{s.lookup}`.")
step_handlers.add("conditional", lambda s: "Chooses a branch by its condition.")
step_handlers.add(
    "vba_procedure",
    lambda s: (
        f"VBA `{s.module}.{s.procedure}`, {s.status.value}; assigns "
        + ", ".join(f"{a.cell.sheet}!R{a.cell.row}C{a.cell.col}" for a in s.assignments)
        + "."
    ),
)


class DocsGenerator:
    step_handlers = step_handlers

    def generate(self, ir: WorkbookIR, target: TargetConfig, cells: CellValues) -> GeneratedProject:
        env = template_env("bob_killer.generate.docs")
        details = {s.id: step_handlers.get(s.kind)(s) for s in ir.steps}
        page = env.get_template("workbook.md.j2").render(
            ir=ir, views=node_views(ir), details=details
        )
        return project({f"docs/{workbook_slug(ir)}.md": page})


registry.generators.add("docs", DocsGenerator())
