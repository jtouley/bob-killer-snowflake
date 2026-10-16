"""Stage ``extract``: a run's workbook into the Raw layer of its workbook.db.

A stage receives only the run id (``registry.Stage``). The host binds where the run's workbook
bytes and its workbook.db live with ``bind_inputs`` for the duration of a call. Registration is
explicit through ``register_stages()``; importing this module registers nothing.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from bob_killer import registry
from bob_killer.extract.raw_db import write_raw
from bob_killer.extract.reader import extract_workbook

STAGE = "extract"

ReadWorkbook = Callable[[str], bytes]
RawDbPath = Callable[[str], Path]

_inputs: ContextVar[tuple[ReadWorkbook, RawDbPath]] = ContextVar("extract_inputs")


@contextmanager
def bind_inputs(*, read_workbook: ReadWorkbook, raw_db: RawDbPath) -> Iterator[None]:
    token = _inputs.set((read_workbook, raw_db))
    try:
        yield
    finally:
        _inputs.reset(token)


def extract_stage(run_id: str) -> None:
    try:
        read_workbook, raw_db = _inputs.get()
    except LookupError:
        raise RuntimeError(
            f"stage {STAGE!r} has no inputs: run it inside {bind_inputs.__name__}(...)"
        ) from None
    write_raw(raw_db(run_id), extract_workbook(read_workbook(run_id)))


def register_stages() -> None:
    """Idempotent: registers the extract stage once."""
    if STAGE not in registry.stages:
        registry.stages.add(STAGE, extract_stage)
