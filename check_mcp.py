"""Verify an MCP endpoint with the official client: handshake, tools/list, and
the free tools (dataset_info, scan_risks, search_issues). --question also calls
ask_contributing, which may use a paid LLM if the server has a key configured.

    python check_mcp.py                                   # local uvicorn
    python check_mcp.py https://<service>.onrender.com/mcp
    SERVICE_API_KEY=... python check_mcp.py <url>          # if auth is enabled

Call one tool directly (skips the default checks):
    python check_mcp.py --tool scan_risks
    python check_mcp.py --tool search_issues --args '{"label": "regression"}'
"""
import argparse
import asyncio
import json
import os

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def _text(result) -> str:
    if result.isError:
        raise RuntimeError(result.content[0].text if result.content else "tool error")
    return "\n".join(c.text for c in result.content if c.type == "text")


async def check(url, question=None, tool=None, tool_args=None):
    headers = {}
    if token := os.getenv("SERVICE_API_KEY"):
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(headers=headers, timeout=300) as http:
        async with streamable_http_client(url, http_client=http) as (read, write, _):
            async with ClientSession(read, write) as session:
                info = await session.initialize()
                print(f"Connected: {info.serverInfo.name}")
                tools = await session.list_tools()
                print("Tools:", ", ".join(t.name for t in tools.tools))
                if tool and tool not in {t.name for t in tools.tools}:
                    print(f"Unknown tool {tool!r}; pick one of the tools listed above.")
                    return 2
                if tool:
                    result = await session.call_tool(tool, tool_args)
                    text = "\n".join(c.text for c in result.content if c.type == "text")
                    label = "tool error" if result.isError else "result"
                    print(f"\n[{tool} {json.dumps(tool_args)}] {label}:\n{text}")
                    return 1 if result.isError else 0
                print("\n[dataset_info]\n" + _text(await session.call_tool("dataset_info", {})))
                risks = json.loads(_text(await session.call_tool("scan_risks", {})))
                print(f"\n[scan_risks] {risks['hits_by_rule']}")
                found = _text(await session.call_tool(
                    "search_issues", {"label": "bug", "state": "open", "limit": 3}))
                print("\n[search_issues label=bug state=open limit=3]\n" + found)
                if question:
                    print("\n[ask_contributing]\n" + _text(await session.call_tool(
                        "ask_contributing", {"question": question})))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", nargs="?", default="http://localhost:8000/mcp")
    parser.add_argument("--question", help="also call ask_contributing")
    parser.add_argument("--tool", help="call only this tool, e.g. scan_risks")
    parser.add_argument("--args", default="{}", help="JSON arguments for --tool")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(check(args.url, args.question, args.tool, json.loads(args.args))))
