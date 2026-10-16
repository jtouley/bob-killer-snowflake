"""``bob-killer all|<stage> WORKBOOK``: a thin client over the service layer."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bob_killer import registry
from bob_killer.contracts.runs import RunState, UploadLimits
from bob_killer.service.runs import create_run, execute_run
from bob_killer.service.uploads import UploadRejected
from bob_killer.store.db import RunStore

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_REJECTED = 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bob-killer")
    parser.add_argument("command", choices=("all", *registry.stages.names()))
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--db", type=Path, default=Path("build/bob_killer.db"))
    args = parser.parse_args(argv)

    store = RunStore(args.db)
    try:
        run = create_run(store, args.workbook.name, args.workbook.read_bytes(), UploadLimits())
    except UploadRejected as exc:
        print(f"rejected: {exc.detail}", file=sys.stderr)
        return EXIT_REJECTED
    state = execute_run(store, run.run_id)
    print(f"{run.run_id} {state}")
    return EXIT_OK if state == RunState.SUCCEEDED else EXIT_FAILED
