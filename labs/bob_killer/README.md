# Bob Killer

Excel workbook → Streamlit app + plain-English docs + equivalence tests, all compiled
from one Workbook IR. Design: [SPEC.md](SPEC.md). Working agreement: [CLAUDE.md](CLAUDE.md).

Hosted in Snowflake by this repository (see the root README and `hosts/snowflake/README.md`).
Licensed Apache-2.0 (this subtree only).

```bash
cd labs/bob_killer
uv sync
uv run pytest -q
uv run python scripts/gates.py        # every gate; must pass before stopping
uv run python scripts/fetch_golden.py # download golden workbooks pinned in golden.lock
```
