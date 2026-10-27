"""Builders for the Streamlit app tests: rows shaped like Snowflake returns them."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from bob_killer.contracts.runs import RunState, StageState, StageStatus
from tests.conftest import sample_run
from tests.fakes.snowpark import FakeSession

APP = Path(__file__).resolve().parents[3] / "src/bob_killer_sis/streamlit_app.py"


def upper(row: dict[str, Any]) -> dict[str, Any]:
    """Snowflake returns unquoted column names in upper case."""
    return {k.upper(): v for k, v in row.items()}


def run_row(state: str = RunState.RUNNING.value, run_id: str = "r1") -> dict[str, Any]:
    """A RUNS row; created_at stays a datetime, as Snowpark returns TIMESTAMP_TZ."""
    return upper({**sample_run(run_id).model_dump(), "state": state})


def stage_row(run_id: str = "r1") -> dict[str, Any]:
    status = StageStatus(run_id=run_id, stage="land_bronze", state=StageState.RUNNING, detail="")
    return upper(status.model_dump(mode="json"))


@pytest.fixture
def fake() -> FakeSession:
    return FakeSession()


@pytest.fixture
def app(fake: FakeSession) -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=30)
    at.session_state["snowpark_session"] = fake
    return at
