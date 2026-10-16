"""Read-only git queries shared by history gates."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Change:
    status: str
    path: str
    old_path: str | None = None

    @property
    def source(self) -> str:
        """Path before the change (differs from ``path`` only for renames)."""
        return self.old_path or self.path


@dataclass(frozen=True)
class Commit:
    sha: str
    trailers: dict[str, str]
    changes: tuple[Change, ...]


def git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return out.stdout


def file_at(repo: Path, rev: str, path: str) -> bytes | None:
    out = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=repo, capture_output=True)
    return out.stdout if out.returncode == 0 else None


def files_under(repo: Path, rev: str, prefix: str) -> dict[str, bytes]:
    """Committed files under ``prefix`` at ``rev``, keyed by path relative to the prefix."""
    names = git(repo, "ls-tree", "-r", "--name-only", rev, "--", prefix).splitlines()
    result: dict[str, bytes] = {}
    for name in names:
        content = file_at(repo, rev, name)
        if content is not None:
            result[name[len(prefix) :]] = content
    return result


def _trailers(repo: Path, sha: str) -> dict[str, str]:
    raw = git(repo, "log", "-1", "--format=%(trailers:only,unfold)", sha)
    trailers: dict[str, str] = {}
    for line in raw.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            trailers[key.strip()] = value.strip()
    return trailers


def _changes(repo: Path, sha: str) -> tuple[Change, ...]:
    raw = git(repo, "diff-tree", "--root", "--no-commit-id", "-r", "-M", "--name-status", sha)
    changes = []
    for line in raw.splitlines():
        parts = line.split("\t")
        if parts[0].startswith(("R", "C")):
            changes.append(Change(parts[0][0], parts[2], parts[1]))
        else:
            changes.append(Change(parts[0][0], parts[1]))
    return tuple(changes)


def commits_in_range(repo: Path, base: str, head: str) -> list[Commit]:
    """First-parent, non-merge commits in base..head, oldest first."""
    shas = git(
        repo, "rev-list", "--reverse", "--first-parent", "--no-merges", f"{base}..{head}"
    ).split()
    return [Commit(sha, _trailers(repo, sha), _changes(repo, sha)) for sha in shas]


def changed_paths(repo: Path, base: str, head: str) -> list[str]:
    return git(repo, "diff", "--name-only", base, head).splitlines()


def rev_exists(repo: Path, rev: str) -> bool:
    out = subprocess.run(
        ["git", "cat-file", "-e", f"{rev}^{{commit}}"], cwd=repo, capture_output=True
    )
    return out.returncode == 0


def is_ancestor(repo: Path, ancestor: str, rev: str) -> bool:
    out = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, rev], cwd=repo, capture_output=True
    )
    return out.returncode == 0


def tree_of(repo: Path, rev: str) -> str:
    return git(repo, "rev-parse", f"{rev}^{{tree}}").strip()
