"""Start a temporary local service, verify HTTP, and always stop the child process."""
import asyncio
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


async def check_mcp(url):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    async with httpx.AsyncClient(headers={"Authorization": "Bearer local-test-token"},
                                 trust_env=False, timeout=10) as client:
        async with streamable_http_client(url, http_client=client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                assert len((await session.list_tools()).tools) == 5
                result = await session.call_tool("dataset_info", {})
                assert not result.isError
                result = await session.call_tool("ask_contributing", {"question": "How do I report a bug?"})
                assert not result.isError

def main():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = dict(os.environ, APP_MODE="offline", SERVICE_API_KEY="local-test-token", PYTHONUTF8="1")
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "api:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT, env=env, stdout=log, stderr=log)
        try:
            base = f"http://127.0.0.1:{port}"
            with httpx.Client(trust_env=False, timeout=2) as client:
                deadline = time.monotonic() + 15
                while True:
                    try:
                        response = client.get(base + "/healthz")
                        if response.status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("Local server failed to start")
                    time.sleep(0.1)
                assert client.get(base + "/readyz").status_code == 401
                headers = {"Authorization": "Bearer local-test-token"}
                ready = client.get(base + "/readyz", headers=headers)
                assert ready.status_code == 200
                assert client.get(base + "/").status_code == 200
                for asset in ("app.js", "app.css", "markdown.js"):
                    assert client.get(base + "/assets/" + asset).status_code == 200
                assert client.get(base + "/workspace").status_code == 401
                workspace = client.get(base + "/workspace", headers=headers).json()
                assert workspace["records"] and workspace["documents"]
                answer = client.post(base + "/workspace/ask", headers=headers,
                                     json={"question": 'How do I report a bug?'}).json()
                assert answer["sources"] and not answer["refused"]
            asyncio.run(check_mcp(base + "/mcp"))
            print("PASS: real local HTTP, authentication, MCP handshake and tools")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
