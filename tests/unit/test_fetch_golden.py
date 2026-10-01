"""fetch_golden.py: hashes pinned in golden.lock; a change fails until explicitly accepted."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fetch_golden import (
    EXIT_OK,
    LOCK_PATH,
    HashMismatch,
    UnpinnedHash,
    fetch_entry,
    load_lock,
    lock_problems,
    main,
)

from bob_killer.contracts.golden import GoldenEntry, GoldenLock, GoldenStatus

PAYLOAD = b"PK\x03\x04 pretend workbook"


def _entry(source: Path, **over: object) -> GoldenEntry:
    fields: dict[str, object] = {
        "id": "demo",
        "complexity": "low",
        "title": "Demo",
        "source_page": "https://example.org/demo",
        "url": source.as_uri(),
        "filename": "demo.xlsx",
        "sha256": None,
        "status": GoldenStatus.PENDING_HASH,
        "note": "",
    }
    fields.update(over)
    return GoldenEntry.model_validate(fields)


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "src.xlsx"
    path.write_bytes(PAYLOAD)
    return path


def test_repo_lock_is_valid() -> None:
    assert lock_problems(load_lock(LOCK_PATH)) == []


@pytest.mark.parametrize(
    "over",
    [
        {"status": GoldenStatus.RESOLVED},
        {"status": GoldenStatus.UNRESOLVED},
        {"filename": "../escape.xlsx"},
        {"filename": "notes.txt"},
        {"sha256": "abc", "status": GoldenStatus.RESOLVED},
    ],
    ids=["resolved-without-hash", "unresolved-with-url", "path-escape", "not-excel", "short-hash"],
)
def test_invalid_entries_reported(source: Path, over: dict[str, object]) -> None:
    lock = GoldenLock(lock_version=1, workbooks=(_entry(source, **over),))
    assert lock_problems(lock)


def test_duplicate_ids_reported(source: Path) -> None:
    lock = GoldenLock(lock_version=1, workbooks=(_entry(source), _entry(source)))
    assert lock_problems(lock)


def test_unpinned_download_needs_accept(source: Path, tmp_path: Path) -> None:
    dest = tmp_path / "golden"
    with pytest.raises(UnpinnedHash):
        fetch_entry(_entry(source), dest, accept=False)
    assert not any(dest.iterdir())


def test_accept_pins_hash(source: Path, tmp_path: Path) -> None:
    updated = fetch_entry(_entry(source), tmp_path / "golden", accept=True)
    assert updated.sha256 == hashlib.sha256(PAYLOAD).hexdigest()
    assert updated.status == GoldenStatus.RESOLVED
    assert (tmp_path / "golden" / "demo.xlsx").read_bytes() == source.read_bytes()


def test_pinned_hash_matches(source: Path, tmp_path: Path) -> None:
    pinned = _entry(
        source, sha256=hashlib.sha256(PAYLOAD).hexdigest(), status=GoldenStatus.RESOLVED
    )
    assert fetch_entry(pinned, tmp_path / "golden", accept=False) == pinned


def test_hash_change_fails_and_saves_nothing(source: Path, tmp_path: Path) -> None:
    pinned = _entry(source, sha256=hashlib.sha256(b"old").hexdigest(), status=GoldenStatus.RESOLVED)
    dest = tmp_path / "golden"
    with pytest.raises(HashMismatch):
        fetch_entry(pinned, dest, accept=False)
    assert not any(dest.iterdir())


def test_main_accept_rewrites_lock(source: Path, tmp_path: Path) -> None:
    lock_file = tmp_path / "golden.lock"
    lock_file.write_text(
        GoldenLock(lock_version=1, workbooks=(_entry(source),)).model_dump_json(indent=2)
    )
    argv = ["--lock", str(lock_file), "--dest", str(tmp_path / "g"), "--accept", "demo"]
    assert main(argv) == EXIT_OK
    entry = load_lock(lock_file).workbooks[0]
    assert entry.status == GoldenStatus.RESOLVED
    assert entry.sha256 == hashlib.sha256(PAYLOAD).hexdigest()


def test_verify_lock_needs_no_network(source: Path, tmp_path: Path) -> None:
    lock_file = tmp_path / "golden.lock"
    lock_file.write_text(
        GoldenLock(lock_version=1, workbooks=(_entry(source),)).model_dump_json(indent=2)
    )
    source.unlink()
    assert main(["--lock", str(lock_file), "--verify-lock"]) == EXIT_OK
