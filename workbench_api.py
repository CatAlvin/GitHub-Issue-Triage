"""Presentation adapters over the issue assistant's business operations."""
import os
from pathlib import Path
from collections import Counter
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

router = APIRouter(prefix="/workspace", tags=["Workbench"])
ROOT = Path(__file__).resolve().parent

class Ask(BaseModel):
    question: str = Field(min_length=3, max_length=2000)

    @field_validator("question")
    @classmethod
    def trim(cls, value):
        if len(value.strip()) < 3:
            raise ValueError("Enter at least three characters")
        return value.strip()

class Brief(BaseModel):
    days: int = Field(default=7, ge=1, le=90)

def documents():
    return [{"name": path.name, "title": path.read_text(encoding="utf-8").splitlines()[0].lstrip("# ")}
            for path in sorted((ROOT / "kb").glob("*.md"))]

@router.get("/documents/{name}")
def document(name: str):
    allowed = {item["name"] for item in documents()}
    if name not in allowed:
        raise HTTPException(404, "Document not found")
    return {"name": name, "text": (ROOT / "kb" / name).read_text(encoding="utf-8")}

def projects(kind):
    choices = [{"id": kind, "title": "团队知识助手" if kind == "team" else "Issue 分诊助手", "url": "/"}]
    other = os.getenv("WORKBENCH_OTHER_URL", "")
    if other:
        choices.append({"id": "triage" if kind == "team" else "team",
                        "title": "Issue 分诊助手" if kind == "team" else "团队知识助手", "url": other})
    return choices

from datetime import datetime, timedelta
import assistant
from common import llm
from risk_rules import evaluate, summary_by_rule

def snapshot_time(issues):
    return max((datetime.fromisoformat(i["timestamp"].replace("Z", "+00:00"))
                for i in issues), default=datetime.fromisoformat("2026-01-01T00:00:00+00:00")) + timedelta(days=1)

@router.get("")
def workspace():
    issues = assistant.load_issues()
    records = [{"id": str(i["thread_id"]), "title": i["text"].splitlines()[0], "text": i["text"],
                "author": i["sender"], "time": i["timestamp"], "channel": i["channel"],
                "labels": i["labels"], "state": i["state"], "comments": i["comments_count"],
                "url": i.get("url", "")} for i in issues]
    now = snapshot_time(issues)
    risks = evaluate(issues, now=now)
    return {"kind": "triage", "title": "Issue 分诊助手", "records": records, "tasks": [],
            "risks": risks, "groups": dict(Counter(label for i in issues for label in i["labels"])),
            "briefs": [], "documents": documents(),
            "period_start": min((i["timestamp"] for i in issues), default=""),
            "period_end": max((i["timestamp"] for i in issues), default=""),
            "reference_time": now.isoformat(), "projects": projects("triage")}

@router.post("/brief")
def brief(request: Brief):
    issues = assistant.load_issues()
    now = snapshot_time(issues)
    window = assistant.recent_issues(issues, request.days, now)
    risks = evaluate(window, now=now)
    return {"period_days": request.days, "reference_time": now.isoformat(),
            "issue_count": len(window),
            "labels": dict(Counter(label for i in window for label in i["labels"])),
            "items": [{"id": str(i["thread_id"]), "title": i["text"].splitlines()[0],
                       "url": i.get("url", "")} for i in window[:40]],
            "risks": risks, "hits_by_rule": summary_by_rule(risks)}

@router.post("/ask")
def ask(request: Ask):
    try:
        index = assistant.build_kb_index()
        hits = index.search(request.question, k=3)
        overlap = assistant._content_tokens(request.question) & assistant._content_tokens(hits[0]["text"]) if hits else set()
        if not hits or hits[0]["score"] < assistant.RAG_MIN_SCORE or not overlap:
            return {"question": request.question, "answer": "", "sources": [], "refused": True}
        text = assistant.answer_question(request.question, index) if llm.llm_available() else hits[0]["text"]
        return {"question": request.question, "answer": text,
                "sources": list(dict.fromkeys(h["meta"]["source"] for h in hits)), "refused": False}
    except Exception as exc:
        raise HTTPException(502, "Question processing failed") from exc
