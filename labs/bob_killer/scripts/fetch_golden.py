"""Download golden workbooks pinned in golden.lock into golden/ (gitignored).

    uv run python scripts/fetch_golden.py                 # fetch every resolved entry
    uv run python scripts/fetch_golden.py --accept sgec_v5_1   # pin a new or changed hash
    uv run python scripts/fetch_golden.py --verify-lock   # CI: validate the lock, no network

A hash change fails until someone reviews it and passes --accept.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import IO

from bk_gates.tdd_common import PROJECT_ROOT
from bob_killer.contracts.golden import GoldenEntry, GoldenLock, GoldenStatus

LOCK_PATH = PROJECT_ROOT / "golden.lock"
DEST = PROJECT_ROOT / "golden"
EXIT_OK = 0
EXIT_FAILED = 1
SHA256 = re.compile(r"[0-9a-f]{64}")
EXCEL_SUFFIXES = (".xlsx", ".xlsm", ".xls")

Opener = Callable[[str], IO[bytes]]


class HashMismatch(Exception):
    pass


class UnpinnedHash(Exception):
    pass


def load_lock(path: Path) -> GoldenLock:
    return GoldenLock.model_validate_json(path.read_text(encoding="utf-8"))


def _entry_problems(e: GoldenEntry) -> list[str]:
    out = []
    if e.filename is not None and (
        PurePosixPath(e.filename).name != e.filename or not e.filename.endswith(EXCEL_SUFFIXES)
    ):
        out.append(f"{e.id}: filename must be a bare Excel file name")
    if e.status is GoldenStatus.UNRESOLVED:
        if e.url is not None or e.sha256 is not None:
            out.append(f"{e.id}: unresolved entries carry no url or hash")
    elif e.url is None or e.filename is None:
        out.append(f"{e.id}: {e.status} needs url and filename")
    if e.status is GoldenStatus.RESOLVED and not SHA256.fullmatch(e.sha256 or ""):
        out.append(f"{e.id}: resolved entries need a 64-hex sha256")
    if e.status is GoldenStatus.PENDING_HASH and e.sha256 is not None:
        out.append(f"{e.id}: pending-hash entries have no sha256 yet")
    return out


def lock_problems(lock: GoldenLock) -> list[str]:
    ids = [e.id for e in lock.workbooks]
    out = [f"duplicate id {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    for entry in lock.workbooks:
        out.extend(_entry_problems(entry))
    return out


def _default_opener(url: str) -> IO[bytes]:
    return urllib.request.urlopen(url, timeout=120)  # type: ignore[no-any-return]


def fetch_entry(
    entry: GoldenEntry, dest: Path, *, accept: bool, opener: Opener = _default_opener
) -> GoldenEntry:
    """Download, verify against the pinned hash, and return the (possibly re-pinned) entry."""
    assert entry.url is not None and entry.filename is not None
    dest.mkdir(parents=True, exist_ok=True)
    partial = dest / f"{entry.filename}.partial"
    digest = hashlib.sha256()
    with opener(entry.url) as resp, partial.open("wb") as fh:
        while chunk := resp.read(1 << 20):
            digest.update(chunk)
            fh.write(chunk)
    actual = digest.hexdigest()
    if not accept and entry.sha256 is None:
        partial.unlink()
        raise UnpinnedHash(f"{entry.id}: sha256 {actual} not pinned; review, then --accept")
    if not accept and actual != entry.sha256:
        partial.unlink()
        raise HashMismatch(f"{entry.id}: expected {entry.sha256}, got {actual}")
    partial.replace(dest / entry.filename)
    return entry.model_copy(update={"sha256": actual, "status": GoldenStatus.RESOLVED})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=LOCK_PATH)
    parser.add_argument("--dest", type=Path, default=DEST)
    parser.add_argument("--verify-lock", action="store_true")
    parser.add_argument("--accept", action="append", default=[], metavar="ID")
    args = parser.parse_args(argv)

    lock = load_lock(args.lock)
    problems = lock_problems(lock)
    for p in problems:
        print(f"lock: {p}", file=sys.stderr)
    if problems or args.verify_lock:
        return EXIT_FAILED if problems else EXIT_OK

    failed = False
    updated: list[GoldenEntry] = []
    for entry in lock.workbooks:
        if entry.status is GoldenStatus.UNRESOLVED:
            print(f"skip  {entry.id}: unresolved ({entry.note})")
            updated.append(entry)
            continue
        try:
            new = fetch_entry(entry, args.dest, accept=entry.id in args.accept)
            print(f"ok    {entry.id}: {args.dest / (new.filename or '')} sha256={new.sha256}")
            updated.append(new)
        except (HashMismatch, UnpinnedHash, OSError) as exc:
            print(f"FAIL  {entry.id}: {exc}", file=sys.stderr)
            failed = True
            updated.append(entry)
    new_lock = lock.model_copy(update={"workbooks": tuple(updated)})
    if new_lock != lock:
        args.lock.write_text(new_lock.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return EXIT_FAILED if failed else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
