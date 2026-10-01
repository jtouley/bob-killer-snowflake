"""Write contract snapshots for the current SCHEMA_VERSION. Refuses to overwrite a version.

    uv run python scripts/export_contracts.py
"""

from __future__ import annotations

import sys

from bk_gates.contracts_versioned import export, generate, snapshot_dir
from bk_gates.tdd_common import PROJECT_ROOT
from bob_killer.contracts import SCHEMA_VERSION


def main() -> int:
    target = snapshot_dir(PROJECT_ROOT, SCHEMA_VERSION)
    try:
        export(generate(), target)
    except FileExistsError:
        print(f"{target} exists: bump SCHEMA_VERSION to change contracts", file=sys.stderr)
        return 1
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
