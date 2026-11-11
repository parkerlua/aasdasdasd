"""The review summary: what the seller sees before submitting, and what the approvers see."""
from __future__ import annotations

import html

from ..services.emoji import emoji_html
from .flows import Flow

ATTACHMENT_KEYS = ("co_proof", "account_image", "proof_image")
# answered automatically from the Discord ID, so their steps are skipped, but they still belong in the summary
AUTO_FILLED_KEYS = ("username", "display", "created")


def fmt(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, list):
        return ", ".join(html.escape(v) for v in value)
    return html.escape(str(value))


def summary(flow: Flow, data: dict) -> str:
    lines = [f"{emoji_html(flow.icon, flow.emoji)} <b>{flow.name}</b>"]
    for s in flow.steps:
        skipped = s.when is not None and not s.when(data)
        if skipped and not (s.key in AUTO_FILLED_KEYS and s.key in data):
            continue
        if not s.label or s.key not in data:
            continue
        v = data[s.key]
        if s.key in ATTACHMENT_KEYS:
            v = "attached ✔"
        elif s.key == "display" and not v:
            v = "Hidden"
        elif s.key == "price" and v != "Highest Offer":
            v = f"${v}"
        elif s.key == "co_amount":
            v = "None" if v is None else f"${v}"
        elif s.key == "notes" and v is None:
            v = "None"
        label = s.label
        if s.key == "usernames":  # "Username" or "Usernames" depending on how many were sent
            label = "Usernames" if len(str(v).splitlines()) > 1 else "Username"
        lines.append(f"{label}: <b>{fmt(v)}</b>")
    if data.get("verified_badges"):
        lines.append(f"Verified by Discord: <b>{fmt(data['verified_badges'])}</b> ✔")
    return "\n".join(lines)
