"""INSERT rows for WB_INPUT_CELLS: the golden's input cells with Excel's cached values (wire JSON)."""
import json, re, sys
from pathlib import Path
sys.path.insert(0, "build")
from gen_dbt import col_number, value  # noqa: E402
from bob_killer.contracts.graph import FormulaCell, GraphInput
from bob_killer.contracts.ir import cell_range
from bob_killer.extract.reader import extract_workbook
from bob_killer.graph.dag import build_graph
from bob_killer.lift import lift

gid, run_id = sys.argv[1], "0" * 31 + "1"
w = next(x for x in json.loads(Path("golden.lock").read_text())["workbooks"] if x["id"] == gid)
raw = extract_workbook((Path("golden") / w["filename"]).read_bytes())
g = build_graph(GraphInput(cells=tuple(FormulaCell(sheet=c.sheet, address=c.address, formula=c.formula) for c in raw.cells if c.formula)))
ir = lift(raw, g, file=w["filename"])
by = {}
for c in raw.cells:
    m = re.fullmatch(r"([A-Z]+)(\d+)", c.address)
    if m:
        by[(c.sheet, int(m.group(2)), col_number(m.group(1)))] = c
rows = []
for node in ir.inputs:
    for o in node.origin:
        for r in cell_range(o).cells():
            c = by.get((r.sheet, r.row, r.col))
            wire = value(c).wire() if c is not None else '{"k":"z"}'
            rows.append(f"('{run_id}', '{r.sheet.replace(chr(39), chr(39)*2)}', {r.row}, {r.col}, '{node.id}', PARSE_JSON('{wire}'))")
sql = ['INSERT INTO WB_INPUT_CELLS ("run_id","sheet","row","col","node_id","value") SELECT column1, column2, column3, column4, column5, column6 FROM VALUES ' + ",\n".join(r.replace("PARSE_JSON(", "(") for r in rows) + ";"]
Path(f"build/inputs_{gid}.sql").write_text("\n".join(sql) + "\n")
print(len(rows), "input cells")
