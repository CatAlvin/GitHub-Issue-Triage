"""Run the bundled issue snapshot through all implemented capabilities offline."""

import os
from datetime import datetime, timedelta

os.environ["APP_MODE"] = "offline"

import assistant
from risk_rules import evaluate, summary_by_rule


def main() -> None:
    issues = assistant.load_issues(assistant.SAMPLE_ISSUES_PATH)
    if not issues:
        raise RuntimeError("No issue snapshot found in data/")
    newest = max(datetime.fromisoformat(i["timestamp"].replace("Z", "+00:00"))
                 for i in issues)
    reference_time = newest + timedelta(days=1)

    print(f"Loaded {len(issues)} issues; reference time: {reference_time.isoformat()}")
    print("\n== Summary ==")
    print(assistant.weekly_summary(issues, days=7, mock=True, now=reference_time))
    print("\n== Risk rules ==")
    hits = evaluate(issues, now=reference_time)
    print(summary_by_rule(hits))
    print("\n== Knowledge-base answer ==")
    index = assistant.build_kb_index()
    print(assistant.answer_question("How do I report a bug?", index, mock=True))
    print("\n== Refusal ==")
    print(assistant.answer_question("Best pizza topping in Naples?", index, mock=True))


if __name__ == "__main__":
    main()
