#!/usr/bin/env python3
"""Read-only issue tools exposed through the official MCP SDK."""
import contextlib
import os
import sys
from collections import Counter
from functools import lru_cache

from anyio import to_thread
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

import assistant
from risk_rules import evaluate as evaluate_risk, summary_by_rule

READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
MAX_SEARCH_RESULTS = 50


@lru_cache(maxsize=1)
def _issues() -> tuple:
    # The snapshot is baked into the image / fixed for the process lifetime,
    # so load once. Restart (or redeploy) to pick up a fresh ingest.py pull.
    return tuple(assistant.load_issues())


@lru_cache(maxsize=1)
def _kb_index():
    return assistant.build_kb_index()


def _source_name() -> str:
    return (assistant.ISSUES_CLEAN_PATH if assistant.ISSUES_CLEAN_PATH.exists()
            else assistant.SAMPLE_ISSUES_PATH).name


async def _run(fn, *args):
    """Run blocking work off the event loop. common/summarization.py prints
    progress to stdout; on the stdio transport stdout belongs to the protocol,
    so route those prints to stderr (the SDK captured the real stdout at start)."""
    def call():
        with contextlib.redirect_stdout(sys.stderr):
            return fn(*args)
    return await to_thread.run_sync(call)


# --- tool bodies (sync, plain data in/out; testable without MCP) -------------

def dataset_info() -> dict:
    issues = _issues()
    stamps = sorted(i["timestamp"] for i in issues)
    return {
        "repo": "microsoft/vscode",
        "source_file": _source_name(),
        "issues": len(issues),
        "oldest": stamps[0] if stamps else None,
        "newest": stamps[-1] if stamps else None,
        "by_state": dict(Counter(i["state"] for i in issues)),
        "top_labels": dict(Counter(l for i in issues for l in i["labels"]).most_common(10)),
    }


def search_issues(query: str = "", label: str = "", state: str = "",
                  limit: int = 10) -> list[dict]:
    q, label, state = query.strip().lower(), label.strip(), state.strip().lower()
    if state and state not in ("open", "closed"):
        raise ValueError("state must be 'open', 'closed' or empty")
    limit = max(1, min(limit, MAX_SEARCH_RESULTS))
    out = []
    for issue in sorted(_issues(), key=lambda i: i["timestamp"], reverse=True):
        if q and q not in issue["text"].lower():
            continue
        if label and label not in issue["labels"]:
            continue
        if state and issue["state"] != state:
            continue
        out.append({"number": issue["thread_id"],
                    "title": issue["text"].split("\n", 1)[0],
                    "labels": issue["labels"], "state": issue["state"],
                    "comments": issue["comments_count"],
                    "created": issue["timestamp"], "url": issue.get("url", "")})
        if len(out) >= limit:
            break
    return out


def scan_risks() -> dict:
    issues = list(_issues())
    hits = evaluate_risk(issues)
    return {"issues_scanned": len(issues), "hits_by_rule": summary_by_rule(hits),
            "hits": hits}


def summarize_issues(days: int = 7) -> str:
    if not 1 <= days <= 90:
        raise ValueError("days must be between 1 and 90")
    return assistant.weekly_summary(list(_issues()), days=days)


def ask_contributing(question: str) -> str:
    if len(question.strip()) < 3:
        raise ValueError("question must be at least 3 characters")
    return assistant.answer_question(question, _kb_index())


# --- MCP wiring --------------------------------------------------------------

def create_mcp() -> FastMCP:
    hosts = ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*"]
    hosts.extend(h.strip() for h in os.getenv("MCP_ALLOWED_HOSTS", "").split(",") if h.strip())
    if render_host := os.getenv("RENDER_EXTERNAL_HOSTNAME"):
        hosts.append(render_host)
    origins = ["http://localhost:*", "http://127.0.0.1:*"]
    origins.extend(f"https://{h}" for h in hosts if ":" not in h)
    server = FastMCP(
        "vscode-triage",
        instructions=("Read-only triage over a snapshot of public microsoft/vscode "
                      "issues. Call dataset_info first to see how fresh the data is."),
        stateless_http=True, json_response=True,
        transport_security=TransportSecuritySettings(
            allowed_hosts=hosts, allowed_origins=origins),
    )

    @server.tool(name="dataset_info", annotations=READ_ONLY)
    async def _dataset_info() -> dict:
        """Size, date range, state split and top labels of the loaded issue snapshot."""
        return await _run(dataset_info)

    @server.tool(name="search_issues", annotations=READ_ONLY)
    async def _search_issues(query: str = "", label: str = "", state: str = "",
                             limit: int = 10) -> list[dict]:
        """Find issues by substring in title/body, exact label (e.g. 'bug',
        'freeze-slow-crash-leak') and/or state ('open'|'closed'). Newest first."""
        return await _run(search_issues, query, label, state, limit)

    @server.tool(name="scan_risks", annotations=READ_ONLY)
    async def _scan_risks() -> dict:
        """Run the three independent risk rules (unaddressed_security,
        severity_keyword_match, fast_escalating_regression); each hit has evidence."""
        return await _run(scan_risks)

    @server.tool(name="summarize_issues", annotations=READ_ONLY)
    async def _summarize_issues(days: int = 7) -> str:
        """Label breakdown + engineer-facing summary of issues opened in the last N days."""
        return await _run(summarize_issues, days)

    @server.tool(name="ask_contributing", annotations=READ_ONLY)
    async def _ask_contributing(question: str) -> str:
        """Answer from vscode's CONTRIBUTING.md with a [source] citation, or refuse."""
        return await _run(ask_contributing, question)

    return server


def self_test():
    info = dataset_info()
    assert info["issues"] > 0, info
    print(f"[test] dataset_info: {info['issues']} issues from {info['source_file']} "
          f"({info['oldest']} .. {info['newest']})")
    found = search_issues(state="open", limit=3)
    assert found and all(i["state"] == "open" for i in found)
    print(f"[test] search_issues: #{found[0]['number']} {found[0]['title'][:60]}")
    risks = scan_risks()
    print(f"[test] scan_risks: {risks['hits_by_rule']}")
    index = _kb_index()  # mock=True: the self-test must not spend LLM credits
    assert "CONTRIBUTING.md" in assistant.answer_question("How do I report a bug?", index, mock=True)
    assert "couldn't find" in assistant.answer_question("best pizza topping in Naples?", index, mock=True)
    print("[test] ask_contributing: cites and refuses as expected")
    tools = [t.name for t in create_mcp()._tool_manager.list_tools()]
    print(f"[test] tools: {tools}")
    print("[test] mcp_server self-test passed (no network calls)")


if __name__ == "__main__":
    if "--test" in sys.argv:
        self_test()
    else:
        create_mcp().run()  # stdio
