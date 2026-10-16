"""contracts/: strict, closed, frozen models and the DDL generated from them."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from bob_killer.contracts import TABLES
from bob_killer.contracts.base import StrictModel
from bob_killer.contracts.bronze import BronzePayload, BronzeRow, LandedFile
from bob_killer.contracts.ddl import ddl_dialects, schema_ddl, table_ddl
from bob_killer.contracts.runs import Run, RunRejected, StageStatus
from tests.conftest import sample_run


def _all_models(cls: type[StrictModel]) -> list[type[StrictModel]]:
    subs = cls.__subclasses__()
    return subs + [m for s in subs for m in _all_models(s)]


def test_every_model_inherits_the_strict_config() -> None:
    import bob_killer.contracts.runs  # noqa: F401  (registers subclasses)

    models = _all_models(StrictModel)
    assert models
    for model in models:
        assert model.model_config == StrictModel.model_config, model.__name__


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        Run.model_validate({**sample_run().model_dump(), "surprise": "x"})


def test_strict_types_reject_coercion() -> None:
    with pytest.raises(ValidationError):
        Run.model_validate({**sample_run().model_dump(), "schema_version": "1"})


def test_models_are_frozen() -> None:
    run = sample_run()
    with pytest.raises(ValidationError):
        run.run_id = "other"  # type: ignore[misc]


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(schema_ddl(TABLES))
    return conn


def test_ddl_columns_match_model_fields() -> None:
    conn = _db()
    for model in TABLES:
        cols = [row[1] for row in conn.execute(f"PRAGMA table_info({model.table_name})")]
        assert cols == list(model.model_fields)


def test_ddl_enum_check_rejects_unknown_state() -> None:
    conn = _db()
    row = sample_run().model_dump(mode="json")
    row["state"] = "exploded"
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            f"INSERT INTO {Run.table_name} VALUES ({','.join('?' * len(row))})", list(row.values())
        )


def test_ddl_is_strict_about_types() -> None:
    conn = _db()
    row = sample_run().model_dump(mode="json")
    row["schema_version"] = "one"
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            f"INSERT INTO {Run.table_name} VALUES ({','.join('?' * len(row))})", list(row.values())
        )


def test_ddl_rejects_unmapped_types() -> None:
    class Unmapped(StrictModel):
        table_name = "unmapped"
        primary_key = ("items",)
        items: list[str]

    with pytest.raises(TypeError):
        table_ddl(Unmapped)


def test_primary_keys_are_model_fields() -> None:
    for model in TABLES:
        assert model.primary_key
        assert set(model.primary_key) <= set(model.model_fields)
    assert StageStatus in TABLES


SNAPSHOTS = Path(__file__).resolve().parents[2] / "src/bob_killer/contracts/snapshots"


def test_sqlite_dialect_output_equals_the_v1_snapshot() -> None:
    expected = (SNAPSHOTS / "v1" / "ddl.sql").read_text(encoding="utf-8")
    assert ddl_dialects["sqlite"](TABLES) == expected


def _payload() -> dict[str, Any]:
    return {
        "column_names": ("a", "b"),
        "dtypes": {"a": "n", "b": "s"},
        "data": {"a": 1.5, "b": None},
    }


def _landed() -> dict[str, Any]:
    sha = "ab" * 32
    return {
        "file_sha256": sha,
        "filename": "book.xlsx",
        "stage_file": f"{sha}.xlsx",
        "size_bytes": 10,
        "first_run_id": "r1",
    }


def _bronze_row() -> dict[str, Any]:
    return {
        "file_sha256": "ab" * 32,
        "sheet": "Sheet1",
        "row_number": 2,
        "run_id": "r1",
        "payload": BronzePayload.model_validate(_payload()),
    }


def _rejected() -> dict[str, Any]:
    return {"status": 413, "detail": "too large"}


# (model, valid fields, field to break, wrong-type value)
NEW_MODELS = [
    (BronzePayload, _payload, "column_names", "a"),
    (BronzePayload, _payload, "data", {"a": [1]}),
    (LandedFile, _landed, "size_bytes", "10"),
    (BronzeRow, _bronze_row, "row_number", "2"),
    (BronzeRow, _bronze_row, "payload", {"column_names": ()}),
    (RunRejected, _rejected, "status", "413"),
    (RunRejected, _rejected, "status", 418),
    (RunRejected, _rejected, "detail", 1),
]


@pytest.mark.parametrize(("model", "valid", "field", "bad"), NEW_MODELS)
def test_new_models_reject_wrong_types(
    model: type[StrictModel], valid: Any, field: str, bad: object
) -> None:
    model.model_validate(valid())
    with pytest.raises(ValidationError):
        model.model_validate({**valid(), field: bad})


@pytest.mark.parametrize(("model", "valid"), sorted({(m, v) for m, v, _, _ in NEW_MODELS}, key=str))
def test_new_models_reject_extra_keys(model: type[StrictModel], valid: Any) -> None:
    with pytest.raises(ValidationError):
        model.model_validate({**valid(), "surprise": "x"})


@pytest.mark.parametrize("status", [400, 413, 415])  # docs/SPEC.md §5.2 step 2
def test_run_rejected_accepts_each_allowed_status(status: int) -> None:
    assert RunRejected(status=status, detail="d").status == status
