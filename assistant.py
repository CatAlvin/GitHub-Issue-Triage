"""Issue summaries, evidence-based risk reports and cited knowledge answers."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
from common import llm  # noqa: E402
from common.retriever import TfidfIndex, paragraph_chunks, tokenize  # noqa: E402
from common.summarization import summarize  # noqa: E402

from risk_rules import evaluate as evaluate_risk, summary_by_rule  # noqa: E402
from schema import to_message  # noqa: E402

DATA_DIR = ROOT / "data"
KB_DIR = ROOT / "kb"
ISSUES_CLEAN_PATH = DATA_DIR / "issues_clean.jsonl"
SAMPLE_ISSUES_PATH = DATA_DIR / "sample_issues.jsonl"
RAG_MIN_SCORE = 0.05  # below this, treat retrieval as "nothing relevant" and refuse

# common/retriever.py's TF-IDF doesn't filter stopwords (kept minimal on purpose),
# which lets a question like "what is the capital of France?" score deceptively
# well against any English doc just on shared "what/is/the/of". A score alone
# isn't a safe refuse-gate on a KB this small; also require the question to
# share a real content word with the best-matching chunk.
_STOPWORDS = {"a", "an", "the", "is", "are", "was", "were", "what", "how", "do",
             "does", "did", "i", "of", "to", "in", "on", "for", "and", "or",
             "it", "this", "that", "can", "you", "me", "my", "please"}


def _content_tokens(text: str) -> set:
    return {t for t in tokenize(text) if t not in _STOPWORDS and len(t) > 2}


def load_issues(path: Path | None = None) -> list[dict]:
    """Prefer a real ingest.py pull; fall back to the bundled real-data sample
    containing 25 public microsoft/vscode issues."""
    chosen = path or (ISSUES_CLEAN_PATH if ISSUES_CLEAN_PATH.exists() else SAMPLE_ISSUES_PATH)
    if not chosen.exists():
        return []
    with chosen.open(encoding="utf-8") as fh:
        from schema import validate
        records = []
        for lineno, line in enumerate(fh, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            errors = validate(record)
            if errors:
                raise ValueError(f"Invalid issue at line {lineno}: {errors}")
            records.append(record)
        return records


def recent_issues(issues: list[dict], days: int, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    if not 1 <= days <= 90:
        raise ValueError("days must be between 1 and 90")
    window = [i for i in issues
              if cutoff <= datetime.fromisoformat(i["timestamp"].replace("Z", "+00:00")) <= now]
    return sorted(window, key=lambda i: i["timestamp"], reverse=True)


def _label_breakdown(issues: list[dict]) -> str:
    counts = {}
    for issue in issues:
        for label in issue.get("labels") or ["(unlabeled)"]:
            counts[label] = counts.get(label, 0) + 1
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:6]
    return ", ".join(f"{name}={n}" for name, n in top) or "(no labels)"


MAX_SUMMARY_ISSUES = 40  # bounds a single Slack reply's LLM cost/latency, not a data limit


def weekly_summary(issues: list[dict], days: int = 7, mock: bool | None = None,
                   now: datetime | None = None) -> str:
    # `now` pins the window for reproducible benchmarks; default is the real clock.
    window = recent_issues(issues, days, now)
    if not window:
        return f"Last {days}d: 0 new issues in the loaded dataset."
    truncated = len(window) > MAX_SUMMARY_ISSUES
    messages = [to_message(i) for i in window[:MAX_SUMMARY_ISSUES]]
    use_mock = mock if mock is not None else not llm.llm_available()
    strategy = "map-reduce" if len(messages) > 8 else "single"
    # Reserve enough context for verbose issue bodies and partial summaries.
    result = summarize(messages, audience="engineer", strategy=strategy, mock=use_mock,
                       context_budget=120_000)
    header = (f"Last {days}d: {len(window)} issues ({_label_breakdown(window)}) "
              f"{'[showing most recent ' + str(MAX_SUMMARY_ISSUES) + '] ' if truncated else ''}"
              f"[{result['mode']}]")
    return header + "\n" + result["text"]


def build_kb_index(kb_dir: Path = KB_DIR) -> TfidfIndex:
    index = TfidfIndex()
    for doc_path in sorted(kb_dir.glob("*.md")):
        for chunk in paragraph_chunks(doc_path.read_text(encoding="utf-8")):
            index.add(chunk, source=doc_path.name)
    index.build()
    return index


def answer_question(question: str, index: TfidfIndex, mock: bool | None = None) -> str:
    """RAG with citation; refuses rather than answering off the retrieved text."""
    hits = index.search(question, k=3)
    overlap = _content_tokens(question) & _content_tokens(hits[0]["text"]) if hits else set()
    if not hits or hits[0]["score"] < RAG_MIN_SCORE or not overlap:
        return ("I couldn't find anything in the indexed docs (CONTRIBUTING.md) "
                "that answers that — not going to guess.")
    context = "\n\n".join(f"[{h['meta']['source']}] {h['text']}" for h in hits)
    use_mock = mock if mock is not None else not llm.llm_available()

    def mock_answer(system, user):
        top = hits[0]
        return (f"Per [{top['meta']['source']}] (best match, score={top['score']}):\n"
                f"{top['text'][:400]}")

    if use_mock:
        return mock_answer(None, None)
    return llm.call_llm(
        system=("Answer using ONLY the provided excerpts. Cite the source file for every "
                "claim in [brackets]. If the excerpts don't answer the question, say so "
                "plainly instead of guessing."),
        user=f"Question: {question}\n\nExcerpts:\n{context}",
        mock=mock_answer, max_output_tokens=400)


def risk_report(issues: list[dict], max_items: int = 10) -> str:
    hits = evaluate_risk(issues)
    if not hits:
        return f"No risk-rule hits across {len(issues)} loaded issues."
    counts = summary_by_rule(hits)
    lines = [f"{len(hits)} risk hits across {len(issues)} issues — {counts}"]
    for hit in hits[:max_items]:
        lines.append(f"  #{hit['thread_id']} [{hit['rule']}] {hit['evidence']} {hit['url']}")
    if len(hits) > max_items:
        lines.append(f"  ... and {len(hits) - max_items} more")
    return "\n".join(lines)


HELP_TEXT = (
    "Commands (mention me, e.g. `@bot summary`):\n"
    "  `summary [days]`  — weekly-style issue summary (default 7 days)\n"
    "  `risk`            — current risk-rule hits (3 rules)\n"
    "  `ask <question>`  — RAG Q&A over CONTRIBUTING.md, cites or refuses\n"
    "  `help`            — this message"
)


def self_test():
    issues = load_issues()
    assert issues, "bundled sample_issues.jsonl should not be empty"
    print(f"[test] loaded {len(issues)} issues (source: "
          f"{'issues_clean.jsonl' if ISSUES_CLEAN_PATH.exists() else 'sample_issues.jsonl'})")

    # Pin the demo clock to the bundled snapshot so this check stays valid later.
    newest = max(datetime.fromisoformat(i["timestamp"].replace("Z", "+00:00"))
                 for i in issues)
    summary = weekly_summary(issues, days=7, mock=True, now=newest + timedelta(days=1))
    assert summary and "[mock]" in summary
    print("[test] weekly_summary:\n" + summary[:300])

    index = build_kb_index()
    answer = answer_question("How do I report a bug?", index, mock=True)
    assert "CONTRIBUTING.md" in answer
    print("\n[test] answer_question:\n" + answer)

    refusal = answer_question("What's the best pizza topping in Naples?", index, mock=True)
    assert "couldn't find" in refusal
    print("\n[test] refusal path:\n" + refusal)

    report = risk_report(issues)
    print("\n[test] risk_report:\n" + report)
    print("\n[test] assistant self-test passed (mock mode, no network calls)")


if __name__ == "__main__":
    self_test()
