#!/usr/bin/env python3
"""Slack Socket Mode commands with threaded replies and event deduplication."""
import os
import re
import sys
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from assistant import HELP_TEXT, answer_question, build_kb_index, load_issues, risk_report, weekly_summary  # noqa: E402

seen_event_ids = set()
seen_event_ids_lock = threading.Lock()

_SUMMARY_RE = re.compile(r"^summary(?:\s+(\d+))?$", re.IGNORECASE)
_ASK_RE = re.compile(r"^ask\s+(.+)$", re.IGNORECASE | re.DOTALL)


def require_env(name: str) -> str:
    """Return a required environment variable or stop with a useful message."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Set {name} before starting Socket Mode (see .env.example).")
    return value


def claim_event(event_id) -> bool:
    """Atomically claim an event ID so a Slack redelivery is processed only once."""
    if not event_id:
        return True
    with seen_event_ids_lock:
        if event_id in seen_event_ids:
            return False
        seen_event_ids.add(event_id)
        return True


def should_ignore(event: dict) -> bool:
    """Ignore messages created by bots to prevent self-reply loops."""
    return bool(event.get("bot_id") or event.get("subtype"))


def strip_mention(text: str, bot_user_id: str | None) -> str:
    if bot_user_id:
        text = text.replace(f"<@{bot_user_id}>", "")
    return text.strip()


class Session:
    """Loads the issue set + KB index once per process, not once per message.

    `mock=None` lets each call auto-detect a live LLM key (normal runtime
    behavior); self_test() pins it to True so the offline test never depends
    on — or accidentally spends — whatever key happens to be in the ambient
    .env.
    """

    def __init__(self, mock: bool | None = None):
        self.issues = load_issues()
        self.kb_index = build_kb_index()
        self.mock = mock

    def route(self, command: str) -> str:
        command = command.strip()
        if not command or command.lower() == "help":
            return HELP_TEXT
        match = _SUMMARY_RE.match(command)
        if match:
            days = int(match.group(1)) if match.group(1) else 7
            return weekly_summary(self.issues, days=days, mock=self.mock)
        if command.lower() == "risk":
            return risk_report(self.issues)
        match = _ASK_RE.match(command)
        if match:
            return answer_question(match.group(1).strip(), self.kb_index, mock=self.mock)
        return f"Not sure what you mean by {command!r}.\n\n{HELP_TEXT}"


def build_post_args(event: dict, reply_text: str) -> dict:
    channel = event.get("channel")
    if not channel:
        raise ValueError("Slack event has no channel")
    args = {"channel": channel, "text": reply_text}
    # Keep the response in the original thread. A top-level mention starts one.
    thread_ts = event.get("thread_ts") or event.get("ts")
    if thread_ts:
        args["thread_ts"] = thread_ts
    return args


def process_event_async(event: dict, client, session: Session, bot_user_id: str | None):
    """Runs OFF the request thread: an LLM-backed answer can take seconds,
    and Slack requires the event to be acknowledged within 3s."""
    command = strip_mention(event.get("text", ""), bot_user_id)
    print(f"  [worker] {event.get('user', '?')} -> {command!r}")
    try:
        reply_text = session.route(command)
    except Exception as exc:  # keep the bot alive; report the failure into the thread
        reply_text = f"Something went wrong answering that ({type(exc).__name__})."
        print(f"  [worker] error: {exc}", file=sys.stderr)
    if len(reply_text) > 3000:
        reply_text = reply_text[:2900] + "\n[truncated; full result would live in outputs/]"
    args = build_post_args(event, reply_text)
    client.chat_postMessage(**args)
    print(f"  [worker] replied in {args['channel']}")


def dispatch_event(body: dict, event: dict, client, session: Session,
                   bot_user_id: str | None, logger=None) -> bool:
    """Validate/dedupe quickly and hand the actual work to a background thread."""
    if should_ignore(event):
        return False
    if not claim_event(body.get("event_id")):
        return False

    def work():
        try:
            process_event_async(event, client, session, bot_user_id)
        except Exception:
            if logger:
                logger.exception("Failed to process Slack event %s", body.get("event_id"))
            else:
                raise

    threading.Thread(target=work, daemon=True).start()
    return True


def create_app(session: Session | None = None):
    """Build the Bolt app without opening a network connection."""
    from slack_bolt import App

    session = session or Session()
    app = App(token=require_env("SLACK_BOT_TOKEN"))

    @app.event("app_mention")
    def on_app_mention(body, event, client, logger, context):
        # Bolt acknowledges the Events API envelope; this listener returns
        # quickly after starting the worker, keeping ack comfortably <3s.
        dispatch_event(body, event, client, session, context.bot_user_id, logger)

    return app


def run_socket_mode():
    from slack_bolt.adapter.socket_mode import SocketModeHandler

    app_token = require_env("SLACK_APP_TOKEN")
    print("Connecting to Slack via Socket Mode; no public endpoint is required...")
    SocketModeHandler(create_app(), app_token).start()


def self_test():
    class FakeClient:
        def __init__(self):
            self.posts = []

        def chat_postMessage(self, **kwargs):
            self.posts.append(kwargs)
            return {"ok": True, "ts": "1700000000.000002"}

    session = Session(mock=True)  # hermetic regardless of ambient .env LLM keys
    client = FakeClient()
    bot_user_id = "UBOT"

    texts = ["<@UBOT> help", "<@UBOT> summary", "<@UBOT> risk",
            "<@UBOT> ask How do I report a bug?", "<@UBOT> whatever"]
    for text in texts:
        event = {"type": "app_mention", "user": "U42", "channel": "C42",
                 "ts": str(time.time()), "text": text}
        process_event_async(event, client, session, bot_user_id)

    assert len(client.posts) == len(texts)
    assert "Commands" in client.posts[0]["text"]
    assert "issues" in client.posts[1]["text"]
    assert "risk" in client.posts[2]["text"].lower()
    assert "CONTRIBUTING.md" in client.posts[3]["text"]
    assert "Not sure" in client.posts[4]["text"]
    print(f"[test] {len(client.posts)}/{len(texts)} commands routed and replied correctly")

    # Redelivery of the same event_id (Slack retries within 3s) must not double-post.
    dup_event = {"type": "app_mention", "user": "U42", "channel": "C42",
                "ts": "1", "text": "<@UBOT> help"}
    dup_body = {"event_id": "Ev-dup-1"}
    started_first = dispatch_event(dup_body, dup_event, client, session, bot_user_id)
    started_second = dispatch_event(dup_body, dup_event, client, session, bot_user_id)
    assert started_first and not started_second, "duplicate event_id must be ignored"
    time.sleep(0.2)  # let the one legitimate background reply land before asserting
    assert len(client.posts) == len(texts) + 1
    print("[test] duplicate event_id correctly deduped")

    # A bot's own message must never be routed (self-reply loop guard).
    bot_event = {**dup_event, "bot_id": "B123"}
    assert not dispatch_event({"event_id": "Ev-bot"}, bot_event, client, session, bot_user_id)
    print("[test] bot-authored event correctly ignored")

    print("[test] slack_bot self-test passed (no network/Slack calls)")


if __name__ == "__main__":
    if "--test" in sys.argv:
        self_test()
    else:
        run_socket_mode()
