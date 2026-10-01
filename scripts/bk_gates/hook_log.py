"""Append-only hook log: each line carries the sha256 of the previous line (C4).

The chain catches edits to any line but the last; the ``Hooks-Log-Head`` commit
trailer and the committed-prefix check catch the rest, including a full recompute.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from bk_gates.core import GateContext, Violation, gate
from bk_gates.git_history import commits_in_range, file_at

LOG = ".context/hooks.log"
ANCHOR_TRAILER = "Hooks-Log-Head"
GENESIS = "0" * 64


def line_hash(line: str) -> str:
    return hashlib.sha256(line.encode()).hexdigest()


def chain_head(text: str) -> str:
    lines = text.splitlines()
    return line_hash(lines[-1]) if lines else GENESIS


def verify_chain(text: str) -> int | None:
    """Index of the first line whose ``prev`` does not match, or None when intact."""
    prev = GENESIS
    for i, line in enumerate(text.splitlines()):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            return i
        if not isinstance(entry, dict) or entry.get("prev") != prev:
            return i
        prev = line_hash(line)
    return None


def append_event(path: Path, event: dict[str, object]) -> str:
    """Append one event and return the new chain head."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    line = json.dumps({**event, "prev": chain_head(text)}, sort_keys=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return line_hash(line)


def _history(ctx: GateContext) -> list[Violation]:
    assert ctx.base is not None
    out: list[Violation] = []
    for commit in commits_in_range(ctx.repo_root, ctx.base, ctx.head):
        change = next((ch for ch in commit.changes if ch.path == LOG), None)
        if change is None:
            continue
        short = commit.sha[:8]
        old = file_at(ctx.repo_root, f"{commit.sha}^", LOG) or b""
        new = file_at(ctx.repo_root, commit.sha, LOG)
        if change.status == "D" or new is None or not new.startswith(old):
            out.append(Violation("append_only_log/rewritten", f"{short} rewrites or deletes {LOG}"))
            if new is None:
                continue
        text = new.decode()
        if (broken := verify_chain(text)) is not None:
            out.append(Violation("append_only_log/broken-chain", f"{short} line {broken + 1}"))
        anchor = commit.trailers.get(ANCHOR_TRAILER)
        if anchor is None:
            out.append(
                Violation("append_only_log/missing-anchor", f"{short} has no {ANCHOR_TRAILER}")
            )
        elif anchor != chain_head(text):
            out.append(Violation("append_only_log/anchor-mismatch", f"{short} anchor != log head"))
    return out


def is_ignored(repo: Path) -> bool:
    proc = subprocess.run(["git", "check-ignore", "-q", LOG], cwd=repo, check=False)
    return proc.returncode == 0


@gate("append_only_log")
def check(ctx: GateContext) -> list[Violation]:
    out = _history(ctx) if ctx.base is not None else []
    if is_ignored(ctx.repo_root):
        out.append(
            Violation("append_only_log/ignored", f"git ignores {LOG}; it can never be audited")
        )
    path = ctx.repo_root / LOG
    current = path.read_bytes() if path.is_file() else None
    committed = file_at(ctx.repo_root, ctx.head, LOG)
    if committed and (current is None or not current.startswith(committed)):
        out.append(Violation("append_only_log/rewritten", f"working tree rewrites committed {LOG}"))
    if current is not None and (broken := verify_chain(current.decode())) is not None:
        out.append(Violation("append_only_log/broken-chain", f"working tree line {broken + 1}"))
    return out
