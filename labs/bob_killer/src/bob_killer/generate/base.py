"""The Generator protocol, the generator loop and the shared template environment (§4.1, §4.6).

A generator reads the IR, the deployment target and the raw cell values it needs for seeds
(lookups and the oracle, §4.5). It never evaluates Excel semantics (§3.5). Core never branches
on the target: ``run_generators`` iterates ``registry.generators`` in name order.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any, Protocol, runtime_checkable

import jinja2

from bob_killer import registry
from bob_killer.contracts.ir import (
    CellRef,
    CellValue,
    GeneratedFile,
    GeneratedProject,
    NameStatus,
    TargetConfig,
    WorkbookIR,
)
from bob_killer.ir.analysis import expr_text, precedent_map
from bob_killer.registry import Registry

CellValues = Mapping[CellRef, CellValue]


@runtime_checkable
class Generator(Protocol):
    step_handlers: Registry[Any]

    def generate(
        self, ir: WorkbookIR, target: TargetConfig, cells: CellValues
    ) -> GeneratedProject: ...


class NamesNeedReview(ValueError):
    """Core decision 3 and D25: no generation while an output-facing name awaits review."""


def check_names(ir: WorkbookIR) -> None:
    steps = {s.id: s for s in ir.steps}
    pending = [
        o.id
        for o in ir.outputs
        if NameStatus.NEEDS_REVIEW in (o.name_status, steps[o.step].name_status)
    ]
    if pending:
        raise NamesNeedReview(f"output-facing names need review: {', '.join(pending)}")


def run_generators(
    ir: WorkbookIR,
    target: TargetConfig,
    cells: CellValues,
    *,
    generators: Registry[object] = registry.generators,
) -> GeneratedProject:
    check_names(ir)
    files: dict[str, GeneratedFile] = {}
    for name in sorted(generators.names()):
        generator = generators.get(name)
        if not isinstance(generator, Generator):
            raise TypeError(f"generators: {name!r} does not implement Generator")
        for f in generator.generate(ir, target, cells).files:
            if f.path in files:
                raise ValueError(f"generators: {f.path} is written twice")
            files[f.path] = f
    return GeneratedProject(files=tuple(files[p] for p in sorted(files)))


NodeView = dict[str, str]


def node_views(ir: WorkbookIR) -> dict[str, NodeView]:
    """One view per IR node, the input of the shared ``_node.md.j2`` partial (§4.6)."""
    kinds = {
        **{p.id: "parameter" for p in ir.parameters},
        **{i.id: f"{i.shape.value} {i.kind.value}" for i in ir.inputs},
        **{lk.id: "lookup" for lk in ir.lookups},
        **{s.id: s.kind for s in ir.steps},
    }
    views: dict[str, NodeView] = {}
    for node in ir.nodes():
        views[node.id] = {
            "id": node.id,
            "label": node.label,
            "kind": kinds[node.id],
            "origin": ", ".join(node.origin),
            "description": node.description,
            "formula": getattr(node, "formula", ""),
            "fingerprint": getattr(node, "fingerprint", ""),
            "expr": "",
            "precedents": "",
        }
    reads = precedent_map(ir)
    for step in ir.steps:
        views[step.id]["expr"] = "; ".join(expr_text(e) for e in step.exprs())
        views[step.id]["precedents"] = ", ".join(reads[step.id])
    return views


def workbook_slug(ir: WorkbookIR) -> str:
    """The workbook's file stem as a path segment, for ``docs/<workbook>.md``."""
    stem = PurePosixPath(ir.source.file.replace("\\", "/")).stem.lower()
    return re.sub(r"[^a-z0-9]+", "_", stem).strip("_") or "workbook"


def project(files: Mapping[str, str]) -> GeneratedProject:
    return GeneratedProject(files=tuple(GeneratedFile.of(p, files[p]) for p in sorted(files)))


def dbt_text(text: str) -> str:
    """Text that dbt renders as Jinja (descriptions, docs blocks) shows braces literally."""
    return "".join("{{ '" + ch + "' }}" if ch in "{}" else ch for ch in text)


def template_env(package: str) -> jinja2.Environment:
    """Templates of ``package`` plus the shared partials in ``bob_killer.generate``.

    The delimiters are ``[[ ]]`` and ``[% %]``, so dbt's own ``{{ }}`` passes through unchanged.
    """
    env = jinja2.Environment(
        loader=jinja2.ChoiceLoader(
            [
                jinja2.PackageLoader(package, "templates"),
                jinja2.PackageLoader("bob_killer.generate", "templates"),
            ]
        ),
        undefined=jinja2.StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
        block_start_string="[%",
        block_end_string="%]",
        variable_start_string="[[",
        variable_end_string="]]",
        comment_start_string="[#",
        comment_end_string="#]",
    )
    env.filters["dbt_text"] = dbt_text
    return env
