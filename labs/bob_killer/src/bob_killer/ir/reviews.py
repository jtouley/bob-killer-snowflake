"""Name reviews (core decision 3, D25): decisions on output-facing names, applied to an IR.

A review applies to the step or output with its id, origin and fingerprint; the node becomes
``accepted`` under ``NameRule.REVIEWED`` with the review's label. ``top_choice_reviews`` records
the deterministic naming rule's own choice for every output-facing node that needs review (the
MVP pre-approval); the queue it answers is ``needs_review``.
"""

from __future__ import annotations

from bob_killer.contracts.ir import NameRule, NameStatus, Node, WorkbookIR
from bob_killer.contracts.workbook import NameReview, ReviewFile


def _fingerprint(node: Node) -> str:
    return getattr(node, "fingerprint", "")


def needs_review(ir: WorkbookIR) -> tuple[Node, ...]:
    """Output-facing nodes awaiting review: each output and its step, in IR order."""
    steps = {s.id: s for s in ir.steps}
    out: dict[str, Node] = {}
    for o in ir.outputs:
        for node in (steps[o.step], o):
            if node.name_status is NameStatus.NEEDS_REVIEW:
                out.setdefault(node.id, node)
    return tuple(out.values())


def top_choice_reviews(ir: WorkbookIR, *, reviewer: str, reason: str) -> ReviewFile:
    return ReviewFile(
        workbook_sha256=ir.source.sha256,
        reviews=tuple(
            NameReview(
                node_id=n.id,
                origin=n.origin[0],
                fingerprint=_fingerprint(n),
                label=n.label,
                reviewer=reviewer,
                reason=reason,
            )
            for n in needs_review(ir)
        ),
    )


def apply_reviews(ir: WorkbookIR, reviews: tuple[NameReview, ...]) -> WorkbookIR:
    """The IR with each matching node accepted; a review that matches no node is ignored."""
    by_key = {(r.node_id, r.origin, r.fingerprint): r for r in reviews}

    def reviewed[N: Node](node: N) -> N:
        review = by_key.get((node.id, node.origin[0], _fingerprint(node)))
        if review is None:
            return node
        return node.model_copy(
            update={
                "label": review.label,
                "name_rule": NameRule.REVIEWED,
                "name_status": NameStatus.ACCEPTED,
            }
        )

    return ir.model_copy(
        update={
            "steps": tuple(reviewed(s) for s in ir.steps),
            "outputs": tuple(reviewed(o) for o in ir.outputs),
        }
    )


__all__ = ["apply_reviews", "needs_review", "top_choice_reviews"]
