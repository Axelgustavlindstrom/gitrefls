from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent

THIS_REPO = Path(__file__).resolve().parents[3]


def _run_git(cmd: list[str], cwd: Path) -> None:
    subprocess.run(["git", "-C", str(cwd)] + cmd, check=True, text=True, capture_output=True)


def _init_repo(tmp_path: Path, branch: str = "master") -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(["init"], cwd=repo)
    _run_git(["config", "user.email", "agent@example.com"], cwd=repo)
    _run_git(["config", "user.name", "Agent"], cwd=repo)
    (repo / "README.md").write_text("hello\n")
    _run_git(["add", "README.md"], cwd=repo)
    _run_git(["commit", "-m", "init"], cwd=repo)
    if branch != "master":
        _run_git(["checkout", "-b", branch], cwd=repo)
    return repo


def _current_branch(repo: Path) -> str:
    out = subprocess.run(["git", "-C", str(repo), "branch", "--show-current"], text=True, capture_output=True)
    return out.stdout.strip() or "HEAD"


from gitrefls import (
    RefParseError,
    discover_repo_root,
    read_reflog,
    refinfo,
    summary,
)


def test_refinfo_reports_current_ref(tmp_path: Path):
    repo = _init_repo(tmp_path)
    branch = _current_branch(repo)
    info = refinfo([branch], repo=repo)
    assert info.refs[branch] is not None
    # newly initialized branch has at least one checkout/commit reflog event
    assert info.summary[branch] >= 1


def test_missing_ref_returns_none(tmp_path: Path):
    repo = _init_repo(tmp_path)
    info = refinfo(["refs/heads/does-not-exist"], repo=repo)
    assert info.refs["refs/heads/does-not-exist"] is None


def test_reflog_records_extracted(tmp_path: Path):
    repo = _init_repo(tmp_path)
    branch = _current_branch(repo)
    (repo / "file.txt").write_text("line1\n")
    _run_git(["add", "file.txt"], cwd=repo)
    _run_git(["commit", "-m", "add file"], cwd=repo)

    entries = read_reflog(branch, repo=repo)
    refs = {entry.ref for entry in entries}
    assert any(r == branch or r.startswith(branch + "@{") for r in refs)
    for entry in entries:
        assert entry.timestamp.tzinfo is not None


def test_discover_repo_root_errors_outside(tmp_path: Path):
    outside = tmp_path / "not-a-repo"
    outside.mkdir()
    try:
        discover_repo_root(start=outside)
    except RefParseError as exc:
        assert "no git repository found" in str(exc)
    else:
        raise AssertionError("expected RefParseError outside a git repo")


def test_summary_counts_branches(tmp_path: Path):
    repo = _init_repo(tmp_path, branch="main")
    _run_git(["checkout", "-b", "feature"], cwd=repo)

    line = summary(repo)
    assert "branches=" in line
    assert line.split("branches=")[1].split(" ")[0] >= "2"
