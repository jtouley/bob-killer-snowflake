"""Contracts: the only type definitions. ``TABLES`` drives the generated SQLite DDL."""

from bob_killer.contracts.base import SCHEMA_VERSION, StrictModel
from bob_killer.contracts.runs import Run, StageStatus

TABLES: tuple[type[StrictModel], ...] = (Run, StageStatus)

__all__ = ["SCHEMA_VERSION", "TABLES", "StrictModel"]
