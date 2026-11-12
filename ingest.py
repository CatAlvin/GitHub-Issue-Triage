#!/usr/bin/env python3
"""Fetch public GitHub issues and validate the local JSONL snapshot."""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

from schema import from_github_issue, validate

load_dotenv(Path(__file__).resolve().parent / ".env")

REPO = "microsoft/vscode"
DATA_DIR = Path(__file__).resolve().parent / "data"
RAW_PATH = DATA_DIR / "issues_raw.jsonl"
CLEAN_PATH = DATA_DIR / "issues_clean.jsonl"


def fetch_issues(repo: str = REPO, pages: int = 8, per_page: int = 100,
                  token: str | None = None, sleep_sec: float = 0.5) -> list[dict]:
    """Pull `state=all` issues, oldest API convention first. Skips PRs."""
    token = token if token is not None else os.environ.get("GITHUB_TOKEN")
    headers = {"Authorization": f"token {token}"} if token else {}
    issues = []
    for page in range(1, pages + 1):
        resp = requests.get(
            f"https://api.github.com/repos/{repo}/issues",
            params={"state": "all", "per_page": per_page, "page": page},
            headers=headers, timeout=20)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        issues.extend(item for item in batch if "pull_request" not in item)
        time.sleep(sleep_sec)
    return issues


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def run(pages: int, repo: str = REPO) -> tuple[int, int]:
    raw = fetch_issues(repo, pages=pages)
    clean = [from_github_issue(issue, repo) for issue in raw]
    bad = [(i, validate(rec)) for i, rec in enumerate(clean) if validate(rec)]
    if bad:
        raise ValueError(f"{len(bad)} records failed schema validation, e.g. {bad[0]}")
    write_jsonl(RAW_PATH, raw)
    write_jsonl(CLEAN_PATH, clean)
    return len(raw), len(clean)


def self_test():
    fake_issue = {
        "user": {"login": "octocat"}, "created_at": "2026-01-02T03:04:05Z",
        "title": "Editor freezes on large files", "body": "Repro: open a 50MB log.",
        "number": 42, "labels": [{"name": "bug"}, {"name": "freeze-slow-crash-leak"}],
        "state": "open", "comments": 3, "html_url": "https://github.com/x/y/issues/42",
    }
    record = from_github_issue(fake_issue, "microsoft/vscode")
    errors = validate(record)
    assert not errors, errors
    print(f"[test] schema OK: {record['sender']} / {record['labels']} / thread_id={record['thread_id']}")
    print("[test] ingest self-test passed (no network calls)")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pages", type=int, default=8, help="100 issues/page (default 8 ~= 800 issues)")
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--test", action="store_true")
    args = ap.parse_args()
    if args.test:
        return self_test()
    n_raw, n_clean = run(args.pages, args.repo)
    print(f"fetched {n_raw} issues, wrote {n_clean} clean records -> {CLEAN_PATH}")


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as exc:
        print(f"GitHub API error: {exc}. Check rate limit / GITHUB_TOKEN.", file=sys.stderr)
        raise SystemExit(1)
