"""IR YAML export and import: a deterministic text form of ``contracts.ir.WorkbookIR``."""

from __future__ import annotations

import json

import yaml

from bob_killer.contracts.ir import WorkbookIR


def dump_ir(ir: WorkbookIR) -> str:
    return yaml.safe_dump(
        ir.model_dump(mode="json"), sort_keys=False, allow_unicode=True, width=100
    )


def load_ir(text: str) -> WorkbookIR:
    """Validate through the strict JSON mode, so YAML lists and enum text load as the contract."""
    return WorkbookIR.model_validate_json(json.dumps(yaml.safe_load(text)))
