import os
import unittest
from unittest.mock import patch

os.environ["APP_MODE"] = "offline"
from fastapi.testclient import TestClient
from api import app
import mcp_server
import slack_bot

class ApiTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"APP_MODE": "offline", "SERVICE_API_KEY": ""})
        self.env.start()
        self.client = TestClient(app)
    def tearDown(self):
        self.client.close()
        self.env.stop()

    def test_health_and_readiness(self):
        self.assertEqual(self.client.get("/healthz").status_code, 200)
        result = self.client.get("/readyz").json()
        self.assertEqual(result["issues"], 25)
        self.assertGreater(result["kb_chunks"], 0)

    def test_readiness_failure_redacts_error(self):
        with patch.object(mcp_server, "_kb_index", side_effect=ValueError("private path")):
            response = self.client.get("/readyz")
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("private path", response.text)

    def test_token_auth(self):
        with patch.dict(os.environ, {"SERVICE_API_KEY": "test-token"}):
            self.assertEqual(self.client.get("/healthz").status_code, 200)
            self.assertEqual(self.client.get("/readyz").status_code, 401)
            self.assertEqual(self.client.get("/readyz", headers={"Authorization": "Bearer test-token"}).status_code, 200)

    def test_search_filters_and_limits(self):
        self.assertLessEqual(len(mcp_server.search_issues(limit=100)), 50)
        for record in mcp_server.search_issues(state="open", label="bug"):
            self.assertEqual(record["state"], "open")
            self.assertIn("bug", record["labels"])
        with self.assertRaises(ValueError):
            mcp_server.search_issues(state="invalid")
        with self.assertRaises(ValueError):
            mcp_server.summarize_issues(91)
        with self.assertRaises(ValueError):
            mcp_server.ask_contributing(" ")

    def test_slack_dedup_and_thread_reply(self):
        with slack_bot.seen_event_ids_lock:
            slack_bot.seen_event_ids.clear()
        self.assertTrue(slack_bot.claim_event("event-1"))
        self.assertFalse(slack_bot.claim_event("event-1"))
        self.assertTrue(slack_bot.should_ignore({"bot_id": "bot"}))
        self.assertEqual(slack_bot.build_post_args({"channel": "C1", "ts": "1", "thread_ts": "0"}, "reply"),
                         {"channel": "C1", "text": "reply", "thread_ts": "0"})
