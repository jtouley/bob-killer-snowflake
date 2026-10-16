"""Golden workbook -> Extract -> Graph -> Lift -> Workbook IR -> dbt project (written to build/dbt_<id>/)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from bob_killer.contracts.graph import FormulaCell, GraphInput
from bob_killer.contracts.ir import CellRef, CellValue, ExcelError, TargetConfig, cell_range
from bob_killer.contracts.raw import CachedType
from bob_killer.extract.reader import extract_workbook
from bob_killer.generate.dbt.generator import DbtGenerator
from bob_killer.graph.dag import build_graph
from bob_killer.ir import dump_ir
from bob_killer.lift import lift


def col_number(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


def value(c: object) -> CellValue:
    t, v = c.cached_type, c.cached_value  # type: ignore[attr-defined]
    if t == CachedType.NUMBER:
        return CellValue.number(float(v))
    if t == CachedType.STRING:
        return CellValue.text(v)
    if t == CachedType.BOOL:
        return CellValue.boolean(v.lower() in ("true", "1"))
    if t == CachedType.ERROR:
        return CellValue.error(next(e for e in ExcelError if e.value == v))
    return CellValue.blank()


def main(golden_id: str, schema: str) -> None:
    lock = json.loads(Path("golden.lock").read_text())
    entry = next(w for w in lock["workbooks"] if w["id"] == golden_id)
    data = (Path("golden") / entry["filename"]).read_bytes()
    raw = extract_workbook(data)
    graph = build_graph(GraphInput(cells=tuple(
        FormulaCell(sheet=c.sheet, address=c.address, formula=c.formula) for c in raw.cells if c.formula)))
    ir = lift(raw, graph, file=entry["filename"])
    by_cell = {}
    for c in raw.cells:
        m = re.fullmatch(r"([A-Z]+)(\d+)", c.address)
        if m:
            by_cell[(c.sheet, int(m.group(2)), col_number(m.group(1)))] = c
    cells: dict[CellRef, CellValue] = {}
    for group in (ir.inputs, ir.lookups, ir.steps):
        for node in group:
            for o in node.origin:
                for ref in cell_range(o).cells():
                    rc = by_cell.get((ref.sheet, ref.row, ref.col))
                    cells[ref] = value(rc) if rc is not None else CellValue.blank()
    target = TargetConfig(run_id="0" * 31 + "1", database="BOB_KILLER", deploy_schema=schema,
                          role="BOB_KILLER_OWNER", warehouse="BOB_KILLER_WH", dbt_version="1.12.3")
    project = DbtGenerator().generate(ir, target, cells)
    out = Path(f"build/dbt_{golden_id}")
    for f in project.files:
        p = out / f.path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f.content, encoding="utf-8")
    Path(f"build/ir_{golden_id}.yaml").write_text(dump_ir(ir), encoding="utf-8")
    print(f"{golden_id}: inputs={len(ir.inputs)} lookups={len(ir.lookups)} params={len(ir.parameters)} "
          f"steps={len(ir.steps)} outputs={len(ir.outputs)} unsupported={len(ir.unsupported)} "
          f"files={len(project.files)} -> {out}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "TEST_DBTDEMO")
