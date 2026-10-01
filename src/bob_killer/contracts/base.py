"""The one place a type is defined: strict, closed, frozen Pydantic models (SPEC decision 8)."""

from __future__ import annotations

from typing import ClassVar, Final

from pydantic import BaseModel, ConfigDict

SCHEMA_VERSION: Final = 1


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    table_name: ClassVar[str] = ""
    primary_key: ClassVar[tuple[str, ...]] = ()
