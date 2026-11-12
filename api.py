#!/usr/bin/env python3
"""HTTP health checks and Streamable HTTP MCP transport."""
import os
import secrets
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from starlette.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from workbench_api import router as workbench_router

import mcp_server

remote_mcp = mcp_server.create_mcp()
mcp_app = remote_mcp.streamable_http_app()


@asynccontextmanager
async def lifespan(app):
    async with remote_mcp.session_manager.run():
        yield


app = FastAPI(title="vscode Issue Triage MCP",
              description="Read-only MCP tools over public microsoft/vscode issues. "
                          "MCP endpoint: /mcp (Streamable HTTP).",
              version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def authenticate(request, call_next):
    token = os.getenv("SERVICE_API_KEY", "")
    public = request.url.path in {"/healthz", "/"} or request.url.path.startswith("/assets/")
    if token and not public:
        supplied = request.headers.get("authorization", "").encode()
        if not secrets.compare_digest(supplied, f"Bearer {token}".encode()):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401,
                                headers={"WWW-Authenticate": "Bearer"})
    return await call_next(request)


class Health(BaseModel):
    status: str
    version: str


class Ready(BaseModel):
    status: str
    repo: str
    source_file: str
    issues: int
    oldest: str | None
    newest: str | None
    by_state: dict[str, int]
    top_labels: dict[str, int]
    kb_chunks: int


@app.get("/healthz", response_model=Health)
def healthz():
    """Liveness only — no data load, no LLM call."""
    return {"status": "ok", "version": app.version}


@app.get("/readyz", response_model=Ready)
def readyz():
    try:
        info = mcp_server.dataset_info()
        chunks = len(mcp_server._kb_index().docs)
        if not info["issues"] or not chunks:
            raise ValueError("empty data or knowledge base")
        return {"status": "ready", **info, "kb_chunks": chunks}
    except Exception as exc:                                     # noqa: BLE001
        raise HTTPException(status_code=503, detail="Dataset unavailable") from exc


app.include_router(workbench_router)
WEB = Path(__file__).resolve().parent / "web"
app.mount("/assets", StaticFiles(directory=WEB, check_dir=False), name="assets")


@app.get("/", include_in_schema=False)
def workbench():
    return FileResponse(WEB / "index.html")


# Mount last: REST routes win, the SDK app serves its exact /mcp path.
app.mount("/", mcp_app)
