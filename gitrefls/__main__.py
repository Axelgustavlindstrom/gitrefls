"""CLI interface for gitrefls."""

from __future__ import annotations

import argparse
import json
import collections
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from gitrefls.models import (
    RefDiff,
    RefInfo,
    ReflogEntry,
    RefParseError,
    discover_repo_root,
    read_reflog,
    refinfo,
    summary,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gitrefls",
        description="Inspect Git reflog activity and ref summaries.",
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Path to the target Git repository. Defaults to the current directory.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser("status", help="Show current ref targets and activity summaries.")
    status.add_argument("ref", nargs="*", default=[], help="Optional ref names to inspect.")
    status.add_argument("--json", action="store_true", help="Format status output as JSON.")
    status.add_argument("--recent-limit", type=int, default=3, help="Maximum recent reflog entries per ref.")

    show = subparsers.add_parser("show", help="Show reflog entries for one or more refs.")
    show.add_argument("ref", nargs="+", help="One or more ref names to inspect.")
    show.add_argument("--limit", type=int, default=10, help="Maximum entries per ref.")
    show.add_argument("--json", action="store_true", help="Format show output as JSON.")

    return parser


def _normalize_repo(repo: Path) -> Path:
    if not repo.exists():
        raise RefParseError(f"--repo path does not exist: {repo}")
    return repo.resolve()


def _first_local_branch(repo: Path) -> Optional[str]:
    try:
        out = discover_repo_root(start=repo)
    except RefParseError:
        return None
    try:
        data = _run_git(["branch", "--format=%(refname:short)"], cwd=out)
        for line in data.splitlines():
            name = line.strip()
            if name:
                return name
    except RuntimeError:
        return None
    return None


def _resolve_refs(cli_refs: Sequence[str], repo: Path) -> List[str]:
    if cli_refs:
        return list(cli_refs)
    first = _first_local_branch(repo)
    if first:
        return [first]
    return ["HEAD"]


def handle_status(args: argparse.Namespace) -> int:
    try:
        repo = _normalize_repo(Path(args.repo))
    except RefParseError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        discover_repo_root(start=repo)
    except RefParseError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    refs = _resolve_refs(args.ref, repo)
    info = refinfo(refs, repo=repo)
    if args.json:
        payload = _serialize_refinfo(info, recent_limit=args.recent_limit)
        print(json.dumps(payload, indent=2, default=_json_default))
        return 0
    print(f"summary: {summary(repo)}")
    for ref, sha in info.refs.items():
        current = sha or "MISSING"
        print(f"ref={ref} current={current} activity={info.summary.get(ref, 0)}")
        for entry in _sorted_recent(info.recent.get(ref, []), args.recent_limit):
            print(f"  date={entry.timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')} sha={entry.sha} message={entry.message}")
    return 0


def _sorted_recent(entries: List[ReflogEntry], limit: int) -> List[ReflogEntry]:
    by_key: dict = collections.defaultdict(list)
    for entry in entries:
        by_key[entry.sha].append(entry)
    deduped = [entries[0] for entries in by_key.values()]
    deduped.sort(key=_entry_sort_key, reverse=True)
    return deduped[:limit]


def _entry_sort_key(entry):
    return entry.timestamp, entry.sha


def _serialize_refinfo(info: RefInfo, recent_limit: int) -> dict:
    payload: dict = {"summary": info.summary, "refs": {}}
    for ref, sha in info.refs.items():
        payload["refs"][ref] = {
            "current": sha,
            "activity": info.summary.get(ref, 0),
            "recent": [
                {
                    "sha": entry.sha,
                    "ref": entry.ref,
                    "message": entry.message,
                    "timestamp": entry.timestamp.isoformat(),
                }
                for entry in _sorted_recent(info.recent.get(ref, []), recent_limit)
            ],
        }
    return payload


def _json_default(obj):
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def handle_show(args: argparse.Namespace) -> int:
    try:
        repo = _normalize_repo(Path(args.repo))
    except RefParseError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        discover_repo_root(start=repo)
    except RefParseError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        combined: List[dict] = []
        for ref in args.ref:
            combined.extend(
                {
                    "sha": entry.sha,
                    "ref": entry.ref,
                    "message": entry.message,
                    "timestamp": entry.timestamp.isoformat(),
                }
                for entry in _sorted_recent(read_reflog(ref, repo=repo), args.limit)
            )
        print(json.dumps(combined, indent=2, default=_json_default))
        return 0
    output = []
    for ref in args.ref:
        entries = _sorted_recent(read_reflog(ref, repo=repo), args.limit)
        output.append(f"{ref} ({len(entries)} entries)")
        for entry in entries:
            output.append(
                f"  {entry.timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')} {entry.sha} {entry.ref} {entry.message}"
            )
        output.append("")
    print("\n".join(output).strip())
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "status":
        return handle_status(args)
    return handle_show(args)


if __name__ == "__main__":
    raise SystemExit(main())
