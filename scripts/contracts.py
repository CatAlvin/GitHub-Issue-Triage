"""Export or check the runtime HTTP and MCP schemas."""
import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from api import app
from mcp_server import create_mcp


async def document():
    schema = app.openapi()
    schema["x-mcp"] = {
        "transports": ["stdio", "streamable-http"],
        "tools": [tool.model_dump(mode="json", exclude_none=True)
                  for tool in await create_mcp().list_tools()],
    }
    schema["x-authentication"] = {
        "environment": "SERVICE_API_KEY",
        "header": "Authorization: Bearer <token>",
        "public_paths": ["/healthz", "/", "/assets/*"],
        "when_unset": "local access without authentication",
    }
    return schema


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    expected = asyncio.run(document())
    path = ROOT / "specs" / "api-spec.yaml"
    if args.write:
        # JSON is valid YAML 1.2 and avoids a second serialization dependency.
        path.write_text(json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("Wrote specs/api-spec.yaml")
    else:
        if json.loads(path.read_text(encoding="utf-8")) != expected:
            raise SystemExit("Contract drift: review specs and run scripts/contracts.py --write")
        print("HTTP and MCP contracts match runtime")


if __name__ == "__main__":
    main()
