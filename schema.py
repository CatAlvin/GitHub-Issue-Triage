"""Issue normalization and field validation shared by all entry points."""
import re
from datetime import datetime

REQUIRED_FIELDS = ("sender", "timestamp", "text", "channel", "thread_id",
                   "labels", "state", "comments_count")

_TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")

# Some issue bodies are multi-thousand-line log/stack-trace dumps that add no
# summarization signal but blow the LLM context budget. Cap it; RAG chunking
# elsewhere has the same kind of size limit for the same reason.
MAX_BODY_CHARS = 2000


def from_github_issue(issue: dict, repo: str) -> dict:
    """Raw GitHub REST issue object -> the unified schema in specs/data-models.md."""
    body = issue.get("body") or ""
    if len(body) > MAX_BODY_CHARS:
        body = body[:MAX_BODY_CHARS] + "\n[truncated]"
    return {
        "sender": issue["user"]["login"],
        "timestamp": issue["created_at"],
        "text": (issue["title"] + "\n\n" + body).strip(),
        "channel": repo,
        "thread_id": issue["number"],
        "labels": [label["name"] for label in issue.get("labels", [])],
        "state": issue["state"],
        "comments_count": issue.get("comments", 0),
        "url": issue.get("html_url", ""),
    }


def validate(record: dict) -> list[str]:
    """Returns a list of problems; empty list means the record is well-formed.

    Mirrors common/task_contracts.py's style: check shape, not semantic truth.
    """
    errors = []
    if not isinstance(record, dict):
        return ["record must be an object"]
    for field in REQUIRED_FIELDS:
        if field not in record:
            errors.append(f"'{field}' missing")
    if "sender" in record and (not isinstance(record["sender"], str) or not record["sender"]):
        errors.append("'sender' must be a non-empty string")
    if "timestamp" in record:
        stamp = record["timestamp"]
        try:
            if not isinstance(stamp, str) or not _TIMESTAMP_RE.fullmatch(stamp):
                raise ValueError("bad timestamp")
            datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            errors.append("'timestamp' must be a valid ISO8601 UTC date-time")
    if "text" in record and not isinstance(record["text"], str):
        errors.append("'text' must be a string")
    if "channel" in record and (not isinstance(record["channel"], str) or not record["channel"].strip()):
        errors.append("'channel' must be a non-empty string")
    if "thread_id" in record and (type(record["thread_id"]) is not int or record["thread_id"] < 1):
        errors.append("'thread_id' must be a positive integer")
    if "labels" in record and (not isinstance(record["labels"], list) or
                               not all(isinstance(label, str) for label in record["labels"])):
        errors.append("'labels' must be a list of strings")
    if "state" in record and record.get("state") not in ("open", "closed"):
        errors.append("'state' must be 'open' or 'closed'")
    if "comments_count" in record and (type(record["comments_count"]) is not int or record["comments_count"] < 0):
        errors.append("'comments_count' must be a nonnegative integer")
    if "url" in record and not isinstance(record["url"], str):
        errors.append("'url' must be a string")
    return errors


def to_message(record: dict) -> dict:
    """Adapt a clean issue record to the shape common/summarization.py expects.

    summarize() reads 'text' plus optional 'ts' / 'author' / 'team_id' /
    'channel' for source attribution — it doesn't need a new schema, just
    these aliases alongside the fields already in `record`.
    """
    return {**record, "ts": record["timestamp"], "author": record["sender"],
            "team_id": "github"}
