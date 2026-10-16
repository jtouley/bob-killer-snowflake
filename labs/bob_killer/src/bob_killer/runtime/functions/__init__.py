"""Excel functions, one module per family. Importing this package registers each one in
``registry.functions`` under its Excel name, and the Excel operators as ``OP_<name>``
(runtime/operators.py)."""

from bob_killer.runtime import operators
from bob_killer.runtime.functions import aggregate, information, logical, lookup, round_digits

__all__ = ["aggregate", "information", "logical", "lookup", "operators", "round_digits"]
