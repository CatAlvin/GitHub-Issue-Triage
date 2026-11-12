import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

os.environ["APP_MODE"] = "offline"
import assistant
import risk_rules
import schema
from common import llm
from common.retriever import TfidfIndex

NOW = datetime(2026, 9, 23, tzinfo=timezone.utc)

def issue(**changes):
    record = {"sender": "dev", "timestamp": "2026-09-22T00:00:00Z",
              "text": "editor crash", "channel": "microsoft/vscode", "thread_id": 1,
              "labels": ["regression"], "state": "open", "comments_count": 5}
    return dict(record, **changes)

class BusinessTests(unittest.TestCase):
    def test_bundled_schema(self):
        records = assistant.load_issues(assistant.SAMPLE_ISSUES_PATH)
        self.assertEqual(len(records), 25)
        self.assertTrue(all(not schema.validate(record) for record in records))

    def test_invalid_types_and_dates(self):
        for changes in ({"timestamp": 1}, {"timestamp": "2026-02-30T00:00:00Z"},
                        {"thread_id": True}, {"thread_id": 0}, {"labels": [4]},
                        {"comments_count": -1}, {"comments_count": True}, {"channel": ""}):
            with self.subTest(changes=changes):
                self.assertTrue(schema.validate(issue(**changes)))
        self.assertTrue(schema.validate([]))

    def test_loading_invalid_record_reports_line(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "issues.jsonl"
            path.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "line 1"):
                assistant.load_issues(path)

    def test_window_order_boundaries_and_future(self):
        records = [issue(thread_id=1, timestamp="2026-09-16T00:00:00Z"),
                   issue(thread_id=2, timestamp="2026-09-23T00:00:00Z"),
                   issue(thread_id=3, timestamp="2026-09-24T00:00:00Z"),
                   issue(thread_id=4, timestamp="2026-09-15T23:59:59Z")]
        self.assertEqual([r["thread_id"] for r in assistant.recent_issues(records, 7, NOW)], [2, 1])
        for days in (0, 91):
            with self.assertRaises(ValueError):
                assistant.recent_issues(records, days, NOW)

    def test_summary_cap_selects_latest(self):
        records = [issue(thread_id=n, timestamp=(NOW-timedelta(hours=50-n)).strftime("%Y-%m-%dT%H:%M:%SZ"))
                   for n in range(50)]
        with patch.object(assistant, "summarize", return_value={"mode": "mock", "text": "ok"}) as call:
            result = assistant.weekly_summary(records, mock=True, now=NOW)
        self.assertIn("50 issues", result)
        self.assertIn("most recent 40", result)
        self.assertEqual([r["thread_id"] for r in call.call_args.args[0]], list(range(49, 9, -1)))

    def test_summary_real_offline_path(self):
        records = assistant.load_issues(assistant.SAMPLE_ISSUES_PATH)
        now = max(datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00")) for r in records)
        self.assertIn("[mock]", assistant.weekly_summary(records, mock=True, now=now))
        self.assertIn("0 new issues", assistant.weekly_summary([], now=NOW))

    def test_risk_time_boundaries(self):
        security = issue(labels=["security"], comments_count=0, timestamp="2026-09-09T00:00:00Z")
        self.assertIsNone(risk_rules.rule_unaddressed_security(security, NOW))
        self.assertIsNotNone(risk_rules.rule_unaddressed_security(security, NOW+timedelta(seconds=1)))
        self.assertIsNone(risk_rules.rule_unaddressed_security(dict(security, state="closed"), NOW+timedelta(days=1)))
        escalation = issue(timestamp="2026-09-20T00:00:00Z")
        self.assertIsNotNone(risk_rules.rule_fast_escalating_regression(escalation, NOW))
        self.assertIsNone(risk_rules.rule_fast_escalating_regression(escalation, NOW+timedelta(seconds=1)))
        self.assertIsNone(risk_rules.rule_fast_escalating_regression(issue(timestamp="2026-09-24T00:00:00Z"), NOW))
        self.assertIsNone(risk_rules.rule_fast_escalating_regression(issue(comments_count=4), NOW))

    def test_risk_requires_independent_signals(self):
        self.assertIsNotNone(risk_rules.rule_severity_keyword_match(issue(), NOW))
        self.assertIsNone(risk_rules.rule_severity_keyword_match(issue(labels=["bug"]), NOW))
        self.assertIsNone(risk_rules.rule_severity_keyword_match(issue(text="small typo"), NOW))

    def test_citation_and_refusal(self):
        index = assistant.build_kb_index()
        self.assertIn("[CONTRIBUTING.md]", assistant.answer_question("How do I report a bug?", index, mock=True))
        for question in ("What is the capital of France?", "Best pizza topping in Naples?"):
            self.assertIn("couldn't find", assistant.answer_question(question, index, mock=True))
        self.assertIn("couldn't find", assistant.answer_question("How to report bugs?", TfidfIndex(), mock=True))

    def test_offline_ignores_ambient_key_and_live_requires_key(self):
        with patch.dict(os.environ, {"APP_MODE": "offline", "OPENAI_API_KEY": "unused"}):
            self.assertEqual(llm.call_llm("system", "user", mock="offline"), "offline")
        with patch.dict(os.environ, {"APP_MODE": "live"}, clear=True):
            with self.assertRaises(llm.ConfigurationError):
                llm.llm_provider()

if __name__ == "__main__":
    unittest.main()
