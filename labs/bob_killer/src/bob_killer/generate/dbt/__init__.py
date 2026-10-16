"""The dbt target (§4): registers ``"dbt"`` in ``registry.generators``."""

from bob_killer import registry
from bob_killer.generate.dbt.generator import DbtGenerator

registry.generators.add("dbt", DbtGenerator())
