"""A run's files on local disk: workbook.db (Raw layer), the cell graph and the IR YAML.

One directory per run under ``root``. ``Workspace`` is the ``GraphIO`` and ``LiftIO`` of the
graph and lift stages, and gives the extract stage its ``raw_db`` path (D17, MVP: the stages run
against a SQLite workbook.db in the host's temp dir; docs/review/REVIEW_2026-10-26.md §3.2 item 6).
"""

from __future__ import annotations

from pathlib import Path

from bob_killer.contracts.graph import CellGraph, DefinedName, FormulaCell, GraphInput
from bob_killer.contracts.ir import WorkbookIR
from bob_killer.contracts.raw import RawWorkbook
from bob_killer.extract.raw_db import read_raw
from bob_killer.ir import dump_ir

WORKBOOK_DB = "workbook.db"
CELL_GRAPH = "cell_graph.json"
IR_YAML = "ir.yaml"


def graph_input(raw: RawWorkbook) -> GraphInput:
    """Every formula cell and every defined name of the Raw layer."""
    return GraphInput(
        cells=tuple(
            FormulaCell(sheet=c.sheet, address=c.address, formula=c.formula)
            for c in raw.cells
            if c.formula
        ),
        names=tuple(
            DefinedName(name=n.name, scope=n.scope or None, refers_to=n.refers_to)
            for n in raw.defined_names
        ),
    )


class Workspace:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, run_id: str, name: str) -> Path:
        return self.root / run_id / name

    def raw_db(self, run_id: str) -> Path:
        return self.path(run_id, WORKBOOK_DB)

    def load_graph_input(self, run_id: str) -> GraphInput:
        return graph_input(read_raw(self.raw_db(run_id)))

    def save_cell_graph(self, run_id: str, graph: CellGraph) -> None:
        self.path(run_id, CELL_GRAPH).write_text(graph.model_dump_json(), encoding="utf-8")

    def load_lift_input(self, run_id: str) -> tuple[RawWorkbook, CellGraph]:
        graph = CellGraph.model_validate_json(self.path(run_id, CELL_GRAPH).read_text("utf-8"))
        return read_raw(self.raw_db(run_id)), graph

    def save_ir(self, run_id: str, ir: WorkbookIR) -> None:
        self.path(run_id, IR_YAML).write_text(dump_ir(ir), encoding="utf-8")
