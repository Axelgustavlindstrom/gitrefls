from __future__ import annotations

import collections
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


REFLIST_DATE_FORMATS = (
    "%a %b %d %H:%M:%S %Y %z",
    "%a %b %d %H:%M:%S %Y",
    "%Y-%m-%d %H:%M:%S %z",
    "%Y-%m-%d %H:%M:%S",
)


class RefParseError(Exception):
    pass


def _run_git(args: List[str], cwd: Optional[Path] = None) -> str:
    cmd = ["git"] + args
    try:
        data = subprocess.run(cmd, cwd=cwd, check=True, text=True, capture_output=True)
    except FileNotFoundError as exc:
        raise RuntimeError("git executable not found.") from exc
    except subprocess.CalledProcessError as exc:
        msg = exc.stderr.strip() or str(exc)
        raise RuntimeError(f"git command failed: {' '.join(cmd)}\n{msg}") from exc
    return data.stdout


def discover_repo_root(start: Optional[Path] = None) -> Path:
    cwd = start or Path.cwd()
    path = cwd.resolve()
    checked: List[Path] = []
    while True:
        checked.append(path)
        if (path / ".git").exists():
            return path
        parent = path.parent
        if parent == path:
            break
        path = parent
    parents = "\n".join(str(p) for p in checked)
    raise RefParseError(f"no git repository found from:\n{parents}")


def read_ref(
    ref: str,
    repo: Optional[Path] = None,
) -> Optional[str]:
    repo_root = discover_repo_root(repo)
    try:
        return _run_git(["rev-parse", ref], cwd=repo_root).strip()
    except RuntimeError:
        return None


def read_reflog(
    ref: Optional[str] = None,
    repo: Optional[Path] = None,
) -> List["ReflogEntry"]:
    repo_root = discover_repo_root(repo)
    args = ["reflog", "show", "--date=iso", "--format=%H%x00%gd%x00%gs%x00%ci"]
    if ref:
        args.append(ref)
    out = _run_git(args, cwd=repo_root)
    entries: List[ReflogEntry] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        try:
            entries.append(ReflogEntry.parse(line))
        except RefParseError:
            continue
    return entries


def refs_current_at(
    commits: Dict[str, Optional[str]],
    repo: Optional[Path] = None,
):
    repo_root = discover_repo_root(repo)
    current: Dict[str, Optional[str]] = {}
    for ref in commits:
        current[ref] = read_ref(ref, repo=repo_root)
    return current


def refinfo(
    refs: Sequence[str],
    repo: Optional[Path] = None,
) -> "RefInfo":
    repo_root = discover_repo_root(repo)
    known: Dict[str, Optional[str]] = {}
    ref_entries: Dict[str, List[ReflogEntry]] = {}
    for ref in refs:
        known[ref] = read_ref(ref, repo=repo_root)
        if known[ref]:
            ref_entries[ref] = read_reflog(ref, repo=repo_root)[:5]
    summary = {ref: len(entries) for ref, entries in ref_entries.items()}
    return RefInfo(
        repo_root=repo_root,
        refs=known,
        summary=summary,
        recent=ref_entries,
    )


def read_entry_at(
    sha: str,
    ref: Optional[str] = None,
    repo: Optional[Path] = None,
) -> Optional["ReflogEntry"]:
    entries = read_reflog(ref, repo=repo)
    for entry in entries:
        if entry.sha == sha:
            return entry
    return None


def diff_between(
    from_: str,
    to: str,
    repo: Optional[Path] = None,
) -> "RefDiff":
    repo_root = discover_repo_root(repo)
    try:
        text = _run_git(["diff", from_, to], cwd=repo_root)
    except RuntimeError as exc:
        raise RefParseError(str(exc)) from exc
    return RefDiff(from_=from_, to=to, diff_summary=text)


def summary(repo: Optional[Path] = None) -> str:
    repo_root = discover_repo_root(repo)
    args = [
        "for-each-ref",
        "--format=%(refname:short) | %(objecttype) | %(objectname) | %(refname)",
        "refs/heads/",
        "refs/tags/",
        "refs/remotes/",
    ]
    out = _run_git(args, cwd=repo_root).strip()
    branches = []
    tags = []
    remotes = []
    for line in out.splitlines() if out else []:
        refname = line.split(" | ", 3)[-1]
        if refname.startswith("refs/remotes/"):
            remotes.append(refname)
        elif refname.startswith("refs/tags/"):
            tags.append(refname)
        else:
            branches.append(refname)
    return f"branches={len(branches)} tags={len(tags)} remotes={len(remotes)}"


@dataclass(frozen=True)
class ReflogEntry:
    sha: str
    ref: str
    message: str
    timestamp: datetime
    raw_line: str = field(repr=False)

    @classmethod
    def parse(cls, raw_line: str) -> "ReflogEntry":
        parts = raw_line.split("\x00", 3)
        if len(parts) != 4:
            raise RefParseError(f"unexpected reflog line: {raw_line!r}")
        sha, ref, message, date_text = parts
        timestamp, _ = _parse_date(date_text)
        if timestamp:
            timestamp = timestamp.astimezone(timezone.utc)
        else:
            timestamp = datetime(1970, 1, 1, tzinfo=timezone.utc)
        return cls(sha=sha, ref=ref, message=message, timestamp=timestamp, raw_line=raw_line)


@dataclass(frozen=True)
class RefInfo:
    repo_root: Path
    refs: Dict[str, Optional[str]]
    summary: Dict[str, int]
    recent: Dict[str, List[ReflogEntry]]


@dataclass(frozen=True)
class RefDiff:
    from_: str
    to: str
    diff_summary: str


def _parse_date(text: str) -> Tuple[Optional[datetime], Optional[str]]:
    text = text.strip()
    for pattern in REFLIST_DATE_FORMATS:
        try:
            dt = datetime.strptime(text, pattern)
            return dt, pattern
        except ValueError:
            continue
    return None, None
