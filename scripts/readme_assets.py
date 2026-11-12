"""Build README figures and their source metrics from the bundled project data."""
import argparse
import ast
from collections import Counter
from html import escape
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["APP_MODE"] = "offline"
from common.retriever import paragraph_chunks


def metrics():
    team = (ROOT / "data/sample_messages.jsonl").exists()
    source = ROOT / "data" / ("sample_messages.jsonl" if team else "sample_issues.jsonl")
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    documents = list((ROOT / "kb").glob("*.md"))
    tests = {}
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        tests[path.stem.removeprefix("test_")] = sum(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))))
    result = {
        "project": "Team Knowledge Assistant" if team else "GitHub Issue Triage",
        "records": len(rows), "dataset": source.relative_to(ROOT).as_posix(),
        "knowledge_documents": len(documents),
        "knowledge_chunks": sum(len(paragraph_chunks(doc.read_text(encoding="utf-8"))) for doc in documents),
        "tests_by_module": tests, "test_count": sum(tests.values()),
    }
    if team:
        from common.assistant import run_pipeline
        digest = run_pipeline(rows)
        result.update(channels=dict(Counter(row["channel"] for row in rows)),
                      tasks=len(digest["tasks"]), summaries=len(digest["summaries"]),
                      alerts=len(digest["alerts"]),
                      alerts_by_severity=dict(Counter(alert["severity"] for alert in digest["alerts"])),
                      period_start=min(row["sim_ts"] for row in rows),
                      period_end=max(row["sim_ts"] for row in rows))
    else:
        result.update(states=dict(Counter(row["state"] for row in rows)),
                      labels=dict(Counter(label for row in rows for label in row["labels"])),
                      unlabeled=sum(not row["labels"] for row in rows),
                      risk_rules=3,
                      period_start=min(row["timestamp"] for row in rows),
                      period_end=max(row["timestamp"] for row in rows))
    schema = json.loads((ROOT / "specs/api-spec.yaml").read_text(encoding="utf-8"))
    result["mcp_tools"] = [tool["name"] for tool in schema["x-mcp"]["tools"]]
    return result


def svg_start(height, dark):
    colors = {"bg": "#17231e", "text": "#edf4ef", "muted": "#adc0b3", "line": "#3a5043", "accent": "#a5cdb5", "track": "#293d31"} if dark else {
        "bg": "#f5f7f1", "text": "#213c2b", "muted": "#56695c", "line": "#d3dfd4", "accent": "#32694a", "track": "#e1e8dc"}
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="{height}" viewBox="0 0 1100 {height}" role="img">',
            '<style>text{font-family:Segoe UI,Arial,sans-serif}</style>',
            f'<rect width="1100" height="{height}" rx="18" fill="{colors["bg"]}"/>'], colors


def text(x, y, value, color, size=16, weight=400):
    return f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" font-weight="{weight}">{escape(str(value))}</text>'


def header(data, dark=False):
    parts, c = svg_start(270, dark)
    team = "channels" in data
    parts += [f'<title>{escape(data["project"])}</title>',
              text(40, 43, "CHENGLAN  /  PYTHON APPLICATIONS", c["muted"], 12, 600),
              text(40, 103, data["project"], c["text"], 42, 650),
              text(40, 136, "Messages, action items and cited knowledge" if team else "Issue search, risk evidence and cited answers", c["muted"], 18),
              f'<path d="M40 165H1060" stroke="{c["line"]}"/>']
    stats = [(data["records"], "sample messages"), (len(data["channels"]), "channels"), (data["tasks"], "action items"), (data["test_count"], "Python tests")] if team else [
        (data["records"], "public issues"), (data["risk_rules"], "risk rules"), (len(data["mcp_tools"]), "MCP tools"), (data["test_count"], "Python tests")]
    for i, (value, label) in enumerate(stats):
        x = 40 + i * 263
        parts += [text(x, 214, value, c["accent"], 32, 650), text(x + 65, 210, label, c["muted"], 15)]
    parts += [text(40, 247, "Bundled dataset and discovered tests  |  scripts/readme_assets.py", c["muted"], 12), "</svg>"]
    return "\n".join(parts) + "\n"


def bars(parts, c, entries, x, y, width=430):
    maximum = max(value for _, value in entries)
    for index, (label, value) in enumerate(entries):
        top = y + index * 49
        parts += [text(x, top, label, c["text"], 14), text(x + width - 24, top, value, c["accent"], 14, 600),
                  f'<rect x="{x}" y="{top+9}" width="{width}" height="7" rx="3" fill="{c["track"]}"/>',
                  f'<rect x="{x}" y="{top+9}" width="{width*value/maximum:.2f}" height="7" rx="3" fill="{c["accent"]}"/>']


def chart(data, dark=False):
    parts, c = svg_start(470, dark)
    team = "channels" in data
    parts += [text(40, 44, "MESSAGE DISTRIBUTION" if team else "ISSUE SNAPSHOT", c["text"], 20, 650),
              text(40, 72, data["period_start"][:10] + " to " + data["period_end"][:10], c["muted"], 13),
              f'<path d="M548 100V422" stroke="{c["line"]}"/>']
    if team:
        left = sorted(data["channels"].items(), key=lambda pair: -pair[1])
        right = [("Channel summaries", data["summaries"]), ("Assigned action items", data["tasks"]),
                 ("High-priority signals", data["alerts_by_severity"].get("high", 0)),
                 ("Medium-priority signals", data["alerts_by_severity"].get("medium", 0)),
                 ("Knowledge documents", data["knowledge_documents"])]
        subtitle, right_title = "Messages per channel", "Pipeline outputs"
    else:
        left = [("Open", data["states"]["open"]), ("Closed", data["states"]["closed"])]
        right = Counter(data["labels"]).most_common(6)
        subtitle, right_title = "Issue status", "Most frequent labels"
    parts += [text(40, 116, subtitle, c["muted"], 14, 600), text(590, 116, right_title, c["muted"], 14, 600)]
    bars(parts, c, left, 40, 151)
    bars(parts, c, right, 590, 151)
    note = f"{data['records']} sample messages; signals are grouped by the first matching severity." if team else f"{data['records']} public issues; an issue can carry multiple labels. {data['unlabeled']} issues have no label."
    parts += [text(40, 448, note, c["muted"], 13), "</svg>"]
    return "\n".join(parts) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = metrics()
    outputs = {"metrics.json": json.dumps(data, ensure_ascii=False, indent=2) + "\n"}
    for name, build in (("header", header), ("snapshot", chart)):
        for dark in (False, True):
            outputs[name + ("-dark" if dark else "-light") + ".svg"] = build(data, dark)
    destination = ROOT / "docs/assets"
    destination.mkdir(parents=True, exist_ok=True)
    for name, content in outputs.items():
        path = destination / name
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                raise SystemExit(f"README asset drift: {name}")
        else:
            path.write_text(content, encoding="utf-8")
    print(json.dumps(data, ensure_ascii=False))


if __name__ == "__main__":
    main()
