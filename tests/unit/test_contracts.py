"""contracts/: strict, closed, frozen models and the DDL generated from them."""

from __future__ import annotations

import sqlite3

import pytest
from pydantic import ValidationError

from bob_killer.contracts import TABLES
from bob_killer.contracts.base import StrictModel
from bob_killer.contracts.ddl import schema_ddl, table_ddl
from bob_killer.contracts.runs import Run, StageStatus
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
