"""hosts/snowflake/batch.py: batched contract-row inserts with bound values only."""

from __future__ import annotations

import json

from hypothesis import given
from hypothesis import strategies as st

from bob_killer.contracts.ir import CellValue
from bob_killer.contracts.workbook import WbInputCell
from bob_killer.hosts.snowflake.batch import insert_rows
from tests.fakes.snowpark import FakeSession
from tests.unit.test_verify_config import wire_values

rows = st.lists(
    st.builds(
        WbInputCell,
        run_id=st.just("cd" * 16),
        sheet=st.text(),
        cell_row=st.integers(min_value=1, max_value=99),
        cell_col=st.integers(min_value=1, max_value=99),
        node_id=st.just("s_a1"),
        value=wire_values,
    ),
    max_size=7,
)


@given(rows, st.integers(min_value=1, max_value=3))
def test_rows_go_in_batches_of_bound_values(batch: list[WbInputCell], size: int) -> None:
    session = FakeSession()
    insert_rows(session, WbInputCell, batch, batch_size=size)
    assert len(session.statements) == -(-len(batch) // size)
    names = list(WbInputCell.model_fields)
    binds = [p for _, params in session.statements for p in params]
    assert len(binds) == len(batch) * len(names)
    for i, row in enumerate(batch):
        bound = dict(zip(names, binds[i * len(names) : (i + 1) * len(names)], strict=True))
        assert CellValue.model_validate_json(bound.pop("value")) == row.value
        others = {k: v for k, v in row.model_dump(mode="json").items() if k in bound}
        assert bound == others
    for sql, _ in session.statements:
        assert sql.count("?") == sql.count("(?") * len(names)
        assert all(json.dumps(r.sheet) not in sql for r in batch if r.sheet)
