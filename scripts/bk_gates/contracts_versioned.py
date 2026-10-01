"""Contract snapshots: DDL, JSON Schemas and OpenAPI generated from contracts/ (decision 8, D6).

Snapshots live in ``src/bob_killer/contracts/snapshots/v{SCHEMA_VERSION}/``. ``export`` refuses
an existing version directory, so changing a contract means bumping ``SCHEMA_VERSION``.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from bk_gates.core import GateContext, Violation, gate

SNAPSHOTS = Path("src/bob_killer/contracts/snapshots")


def default_models() -> list[type]:
    """Every shipped StrictModel subclass (test-defined models are excluded), sorted by name."""
    import bob_killer.contracts.golden  # noqa: F401  (register subclasses)
    import bob_killer.contracts.runs  # noqa: F401
    from bob_killer.contracts.base import StrictModel

    found: list[type] = []
    stack: list[type] = [StrictModel]
    while stack:
        for sub in stack.pop().__subclasses__():
            stack.append(sub)
            if sub.__module__.startswith("bob_killer.contracts"):
                found.append(sub)
    return sorted(found, key=lambda m: f"{m.__module__}.{m.__qualname__}")


def generate(models: Sequence[type] | None = None) -> dict[str, str]:
    from bob_killer.api.main import app
    from bob_killer.contracts import TABLES
    from bob_killer.contracts.ddl import schema_ddl

    schemas = {
        f"{m.__module__}.{m.__qualname__}": m.model_json_schema()  # type: ignore[attr-defined]
        for m in (default_models() if models is None else models)
    }
    return {
        "ddl.sql": schema_ddl(TABLES),
        "schemas.json": json.dumps(schemas, indent=2, sort_keys=True) + "\n",
        "openapi.json": json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n",
    }


def snapshot_dir(project_root: Path, version: int) -> Path:
    return project_root / SNAPSHOTS / f"v{version}"


def export(generated: dict[str, str], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=False)
    for name, text in generated.items():
        (directory / name).write_text(text, encoding="utf-8")


def check_snapshots(generated: dict[str, str], directory: Path) -> list[Violation]:
    if not directory.is_dir():
        return [
            Violation(
                "contracts_versioned/missing-snapshot",
                f"{directory} missing; bump SCHEMA_VERSION, then run scripts/export_contracts.py",
            )
        ]
    out = []
    for name, text in generated.items():
        path = directory / name
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            out.append(
                Violation(
                    "contracts_versioned/drift",
                    f"{name} differs from {directory.name}: bump SCHEMA_VERSION and export a new "
                    "snapshot (or a pinned dependency such as fastapi/pydantic drifted)",
                )
            )
    return out


@gate("contracts_versioned")
def check(ctx: GateContext) -> list[Violation]:
    from bob_killer.contracts import SCHEMA_VERSION

    return check_snapshots(generate(), snapshot_dir(ctx.project_root, SCHEMA_VERSION))
