"""The shared RunRepository contract suite, run live on SnowflakeRunStore (host Phase 4 exit).

The test functions are the ones in tests/unit/test_store.py; tests/live/conftest.py overrides their
``store`` fixture with a live store, so the same assertions run against real Snowflake tables.
"""

from __future__ import annotations

from tests.unit.test_store import (
    test_claim_is_won_once,
    test_run_round_trips,
    test_set_state_and_stages,
    test_stage_rows_keep_registry_order_after_execute,
    test_unknown_run_is_none_and_not_claimed,
    test_upsert_updates_the_row_in_place,
)

__all__ = [
    "test_claim_is_won_once",
    "test_run_round_trips",
    "test_set_state_and_stages",
    "test_stage_rows_keep_registry_order_after_execute",
    "test_unknown_run_is_none_and_not_claimed",
    "test_upsert_updates_the_row_in_place",
]
