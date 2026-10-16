import json
from pathlib import Path

from bk_gates.tdd_common import digest_tests_tree, parse_junit, read_worktree_tests
from record_run import record

FAILING_TEST = b"def test_fails():\n    assert 1 == 2\n"


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "proj"
    (project / "tests").mkdir(parents=True)
    (project / "tests" / "test_demo.py").write_bytes(FAILING_TEST)
    return project


def test_digest_ignores_pycache_and_order() -> None:
    a = {"x.py": b"1", "y.py": b"2"}
    b = {"y.py": b"2", "x.py": b"1", "__pycache__/x.pyc": b"junk"}
    assert digest_tests_tree(a) == digest_tests_tree(b)


def test_digest_changes_with_content() -> None:
    assert digest_tests_tree({"x.py": b"1"}) != digest_tests_tree({"x.py": b"2"})


def test_parse_junit_outcomes() -> None:
    xml = (
        b'<testsuites><testsuite><testcase classname="t" name="ok"/>'
        b'<testcase classname="t" name="bad"><failure/></testcase>'
        b'<testcase classname="t" name="err"><error/></testcase>'
        b'<testcase classname="t" name="skip"><skipped/></testcase>'
        b"</testsuite></testsuites>"
    )
    outcomes = parse_junit(xml)
    expected = {"t::ok": "passed", "t::bad": "failed", "t::err": "error", "t::skip": "skipped"}
    assert outcomes == expected


def test_record_writes_failed_run(tmp_path: Path) -> None:
    project = _project(tmp_path)
    out = record(project, tmp_path / ".context", "red", ["tests/test_demo.py"])
    data = json.loads(out.read_text())
    assert data["tdd_phase"] == "red"
    assert set(data["nodes"].values()) == {"failed"}
    assert data["tests_tree_sha256"] == digest_tests_tree(read_worktree_tests(project))
    assert (out.parent / "junit.xml").is_file()
