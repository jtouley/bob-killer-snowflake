"""Excel functions, one module per family. Importing this package registers each one in
``registry.functions`` under its Excel name."""

from bob_killer.runtime.functions import aggregate, logical, round_digits

__all__ = ["aggregate", "logical", "round_digits"]
