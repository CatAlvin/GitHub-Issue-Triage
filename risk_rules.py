"""Independent risk signals combining labels, age, keywords and comment counts."""
import re
from datetime import datetime, timezone

SEVERITY_KEYWORDS = re.compile(r"crash|data loss|corrupt|CVE|freeze", re.IGNORECASE)
SEVERITY_LABELS = {"freeze-slow-crash-leak", "regression"}

SECURITY_STALE_DAYS = 14
FAST_ESCALATION_WINDOW_HOURS = 72
FAST_ESCALATION_MIN_COMMENTS = 5


def _age_days(timestamp: str, now: datetime) -> float:
    created = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return (now - created).total_seconds() / 86400


def _age_hours(timestamp: str, now: datetime) -> float:
    return _age_days(timestamp, now) * 24


def rule_unaddressed_security(issue: dict, now: datetime) -> dict | None:
    """Rule A: security-labeled, open, stale, and nobody has replied."""
    if "security" not in issue.get("labels", []):
        return None
    if issue.get("state") != "open":
        return None
    age = _age_days(issue["timestamp"], now)
    if age <= SECURITY_STALE_DAYS or issue.get("comments_count", 0) != 0:
        return None
    return {
        "rule": "unaddressed_security",
        "thread_id": issue["thread_id"],
        "evidence": f"label=security, state=open, age={age:.1f}d (>{SECURITY_STALE_DAYS}), comments=0",
    }


def rule_severity_keyword_match(issue: dict, now: datetime) -> dict | None:
    """Rule B: severity keyword in the text AND a severity label — the label
    is a second, independent confirmation, not just a keyword hit."""
    hit_labels = SEVERITY_LABELS & set(issue.get("labels", []))
    if not hit_labels:
        return None
    match = SEVERITY_KEYWORDS.search(issue.get("text", ""))
    if not match:
        return None
    return {
        "rule": "severity_keyword_match",
        "thread_id": issue["thread_id"],
        "evidence": f"keyword={match.group(0)!r}, labels={sorted(hit_labels)}",
    }


def rule_fast_escalating_regression(issue: dict, now: datetime) -> dict | None:
    """Rule C: a 'regression' issue getting a lot of comments very fast —
    comment velocity is the signal, independent of any keyword match."""
    if "regression" not in issue.get("labels", []):
        return None
    age_hours = _age_hours(issue["timestamp"], now)
    comments = issue.get("comments_count", 0)
    if not 0 <= age_hours <= FAST_ESCALATION_WINDOW_HOURS or comments < FAST_ESCALATION_MIN_COMMENTS:
        return None
    return {
        "rule": "fast_escalating_regression",
        "thread_id": issue["thread_id"],
        "evidence": f"age={age_hours:.1f}h (<={FAST_ESCALATION_WINDOW_HOURS}), comments={comments} "
                    f"(>={FAST_ESCALATION_MIN_COMMENTS})",
    }


RULES = (rule_unaddressed_security, rule_severity_keyword_match, rule_fast_escalating_regression)


def evaluate(issues: list[dict], now: datetime | None = None) -> list[dict]:
    """Run every rule against every issue. One issue can trigger more than one
    rule; each hit is reported separately (see module docstring)."""
    now = now or datetime.now(timezone.utc)
    hits = []
    for issue in issues:
        for rule in RULES:
            hit = rule(issue, now)
            if hit:
                hits.append({**hit, "url": issue.get("url", "")})
    return hits


def summary_by_rule(hits: list[dict]) -> dict:
    counts = {rule.__name__.removeprefix("rule_"): 0 for rule in RULES}
    for hit in hits:
        counts[hit["rule"]] = counts.get(hit["rule"], 0) + 1
    return counts


def self_test():
    """Synthetic issues, one built to trip each rule, verified offline."""
    now = datetime(2026, 9, 23, tzinfo=timezone.utc)
    fixtures = [
        {"thread_id": 1, "labels": ["security"], "state": "open", "comments_count": 0,
         "timestamp": "2026-08-01T00:00:00Z", "text": "auth bypass", "url": "u1"},
        {"thread_id": 2, "labels": ["freeze-slow-crash-leak"], "state": "open", "comments_count": 2,
         "timestamp": "2026-09-20T00:00:00Z", "text": "editor freeze on large file, data loss risk",
         "url": "u2"},
        {"thread_id": 3, "labels": ["regression"], "state": "open", "comments_count": 8,
         "timestamp": "2026-09-22T12:00:00Z", "text": "extensions stopped loading after update",
         "url": "u3"},
        {"thread_id": 4, "labels": ["bug"], "state": "open", "comments_count": 0,
         "timestamp": "2026-09-22T00:00:00Z", "text": "minor typo in settings UI", "url": "u4"},
    ]
    hits = evaluate(fixtures, now=now)
    fired = {h["rule"] for h in hits}
    assert fired == {"unaddressed_security", "severity_keyword_match", "fast_escalating_regression"}, fired
    assert not any(h["thread_id"] == 4 for h in hits), "clean issue must not fire any rule"
    for h in hits:
        print(f"[test] #{h['thread_id']} -> {h['rule']}: {h['evidence']}")
    print(f"[test] summary: {summary_by_rule(hits)}")
    print("[test] risk_rules self-test passed (no network calls)")


if __name__ == "__main__":
    self_test()
