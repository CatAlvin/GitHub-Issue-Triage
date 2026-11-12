import os
import unittest
from unittest.mock import patch

os.environ["APP_MODE"] = "offline"
from fastapi.testclient import TestClient
from api import app
import workbench_api

class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"APP_MODE": "offline", "SERVICE_API_KEY": ""})
        self.env.start()
        self.client = TestClient(app)
    def tearDown(self):
        self.client.close()
        self.env.stop()

    def test_frontend_and_assets(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn('lang="zh-CN"', page.text)
        self.assertIn("app.js", page.text)
        self.assertEqual(self.client.get("/assets/app.js").status_code, 200)

    def test_workspace_does_not_call_model(self):
        with patch.object(workbench_api.llm, "call_llm", side_effect=AssertionError("model called")):
            response = self.client.get("/workspace")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["records"]), 25)
        self.assertTrue(response.json()["documents"])

    def test_document_allowlist(self):
        data = self.client.get("/workspace").json()
        name = data["documents"][0]["name"]
        self.assertEqual(self.client.get("/workspace/documents/" + name).status_code, 200)
        self.assertEqual(self.client.get("/workspace/documents/.env").status_code, 404)
        self.assertEqual(self.client.get("/workspace/documents/missing.md").status_code, 404)

    def test_question_and_brief_contract(self):
        answer = self.client.post("/workspace/ask", json={"question": "How do I report a bug?"}).json()
        self.assertFalse(answer["refused"])
        self.assertTrue(answer["sources"])
        self.assertTrue(self.client.post("/workspace/ask", json={"question": "Best pizza topping in Naples?"}).json()["refused"])
        self.assertEqual(self.client.post("/workspace/ask", json={"question": " "}).status_code, 422)
        self.assertEqual(self.client.post("/workspace/brief", json={"days": 0}).status_code, 422)
        self.assertEqual(self.client.post("/workspace/brief", json={"days": 7}).status_code, 200)

    def test_public_shell_private_workspace(self):
        with patch.dict(os.environ, {"SERVICE_API_KEY": "ui-test-token"}):
            self.assertEqual(self.client.get("/").status_code, 200)
            self.assertEqual(self.client.get("/assets/app.css").status_code, 200)
            self.assertEqual(self.client.get("/workspace").status_code, 401)
            self.assertEqual(self.client.get("/workspace", headers={"Authorization": "Bearer ui-test-token"}).status_code, 200)
