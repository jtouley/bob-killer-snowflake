"""Collection-order regression (G1): a stage added at import time never reaches a test.

pytest imports every test module at collection, before any fixture runs. The autouse
fixture in tests/conftest.py must still give each test the empty core stage baseline.
"""

from __future__ import annotations

from bob_killer import registry


def _import_probe(run_id: str) -> None:
    return None


registry.stages.add(_import_probe.__name__, _import_probe)


def test_stage_added_at_import_is_not_visible() -> None:
    assert _import_probe.__name__ not in registry.stages
    assert not registry.stages
