"""Name review files for a workbook: ``python -m bob_killer.hosts.snowflake.reviews``.

    uv run python -m bob_killer.hosts.snowflake.reviews golden/<file> --name <id> \\
        --reviewer <who> --reason "<why>"

lifts the workbook exactly as the pipeline does (every formula and defined name), records the
deterministic naming rule's own choice for every output-facing node that needs review
(``ir.reviews.top_choice_reviews``) in ``hosts/snowflake/reviews/<id>.yaml``, and writes the
whole queue to ``.context/evidence/review_queue_<id>.md`` for a later human pass. The deploy puts
the YAML files on ``@DBT_SRC/_reviews/``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from bob_killer.contracts.ir import WorkbookIR
from bob_killer.contracts.workbook import ReviewFile
from bob_killer.extract import extract_workbook
from bob_killer.graph.dag import build_graph
from bob_killer.ir.reviews import needs_review, top_choice_reviews
from bob_killer.lift import lift
from bob_killer.service.workspace import graph_input

PROJECT = Path(__file__).resolve().parents[4]
REVIEWS_DIR = PROJECT / "hosts" / "snowflake" / "reviews"
EVIDENCE_DIR = PROJECT.parents[1] / ".context" / "evidence"


def lifted(data: bytes) -> WorkbookIR:
    raw = extract_workbook(data)
    return lift(raw, build_graph(graph_input(raw)))


def review_yaml(review: ReviewFile) -> str:
    return yaml.safe_dump(review.model_dump(mode="json"), sort_keys=False, width=100)


def queue_markdown(name: str, ir: WorkbookIR, review: ReviewFile) -> str:
    lines = [
        f"# Name review queue: {name}",
        "",
        f"Workbook sha256 `{ir.source.sha256}`. {len(review.reviews)} output-facing nodes need",
        "review; each was pre-approved with the naming rule's own choice (reviews/"
        f"{name}.yaml). Revisit any row below with a better name.",
        "",
        "| node | origin | rule | label | formula |",
        "| --- | --- | --- | --- | --- |",
    ]
    for n in needs_review(ir):
        formula = getattr(n, "formula", "").replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| `{n.id}` | {n.origin[0]} | {n.name_rule.value} | {n.label} | `{formula}` |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bob_killer.hosts.snowflake.reviews")
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--name", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args(argv)
    ir = lifted(args.workbook.read_bytes())
    review = top_choice_reviews(ir, reviewer=args.reviewer, reason=args.reason)
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    (REVIEWS_DIR / f"{args.name}.yaml").write_text(review_yaml(review), encoding="utf-8")
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    queue = EVIDENCE_DIR / f"review_queue_{args.name}.md"
    queue.write_text(queue_markdown(args.name, ir, review), encoding="utf-8")
    print(f"{len(review.reviews)} reviews -> {REVIEWS_DIR / args.name}.yaml, {queue}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
