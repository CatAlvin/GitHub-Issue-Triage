import asyncio
import os
import sys
import unittest
from pathlib import Path

os.environ["APP_MODE"] = "offline"
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]

class McpTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_stdio_handshake_and_tool_calls(self):
        params = StdioServerParameters(
            command=sys.executable, args=[str(ROOT / "mcp_server.py")],
            cwd=str(ROOT), env=dict(os.environ, APP_MODE="offline", PYTHONUTF8="1"))
        async with asyncio.timeout(25):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = (await session.list_tools()).tools
                    self.assertEqual({t.name for t in tools}, {"dataset_info", "search_issues", "scan_risks", "summarize_issues", "ask_contributing"})
                    result = await session.call_tool("dataset_info", {})
                    self.assertFalse(result.isError)
                    answer = await session.call_tool("ask_contributing", {"question": "How do I report a bug?"})
                    self.assertFalse(answer.isError)
                    invalid = await session.call_tool("summarize_issues", {"days": 0} )
                    self.assertTrue(invalid.isError)
