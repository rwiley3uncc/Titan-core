from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from typing import Any

from titan_core.action_log import load_action_log


def get_recent_actions(limit: int = 10) -> list[dict[str, Any]]:
    entries = load_action_log()
    if limit <= 0:
        return []
    return [asdict(entry) for entry in entries[-limit:]]


def get_action_summary() -> dict[str, Any]:
    entries = load_action_log()
    approved_counts: Counter[str] = Counter()
    cancelled_counts: Counter[str] = Counter()
    last_failure = ""

    for entry in entries:
        if entry.status == "approved":
            approved_counts[entry.action_name] += 1
        elif entry.status == "cancelled":
            cancelled_counts[entry.action_name] += 1
        elif entry.status == "failed" and entry.result:
            last_failure = entry.result

    return {
        "recent": get_recent_actions(),
        "most_approved": approved_counts.most_common(1)[0][0] if approved_counts else "",
        "most_cancelled": cancelled_counts.most_common(1)[0][0] if cancelled_counts else "",
        "last_failure": last_failure,
    }
