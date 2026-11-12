"""Turn an existing channel post back into listing data (so old posts can be added to the database)."""
from __future__ import annotations

import re

from .flows import BADGE_GROUPS, amount
from ..services.emoji import ITEM
from .post import DISCORD_ACCOUNTS, PLURAL_TITLES, POST_TITLES, SHORT_BADGES

TITLE_TO_FLOW = {**{v: k for k, v in POST_TITLES.items()}, **{v: k for k, v in PLURAL_TITLES.items()}}
BADGE_BY_SHORT = {v: k for k, v in SHORT_BADGES.items()}


def _num(text: str):
    try:
        return amount(text)
    except ValueError:
        return text


def parse_post(text: str, image: str | None):
    """Returns (flow key, data) or None if the text isn't a post this bot made."""
    lines = [ln.replace("⠀", "").strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    if lines:
        lines[0] = re.sub(r"^[^A-Za-z]+|[^A-Za-z]+$", "", lines[0])  # platform emoji after the title (before, in old posts)
    if not lines or lines[0] not in TITLE_TO_FLOW:
        return None
    key = TITLE_TO_FLOW[lines[0]]
    names, bullets, link, data = [], [], "", {"notes": None}
    items = []  # lines led by the item emoji: a vanity ("/late") or a badge line
    for ln in lines[1:]:
        if ln.startswith(ITEM + " "):
            items.append(ln[len(ITEM) + 1:].strip())
        elif ln.startswith("BIN:"):
            data["price"] = _num(ln[4:].strip())
        elif ln.startswith("C/O:"):
            v = ln[4:].strip()
            data["co_amount"] = None if v.lower() == "none" else _num(v)
        elif ln.startswith("- "):
            bullets.append(ln[2:].strip())
        elif ln.startswith("@"):
            names.append(ln)
        elif ln.lower().startswith("http"):
            link = ln
    if "price" not in data:
        return None
    data.setdefault("co_amount", None)
    if image:
        data["account_image"] = image

    if key in DISCORD_ACCOUNTS:
        extra, oge = [], False
        for b in bullets:
            m = re.fullmatch(r"OGE(?: \((.+)\))?", b)
            if m:
                oge, data["oge"] = True, "OGE"
                if m.group(1):
                    data["email_domain"] = m.group(1)
            elif b == "Pullback Test Accepted":
                data["pb_test"] = "Accepted"
            elif b.startswith("Standing "):
                data["standing"] = b[len("Standing "):]
            else:
                extra.append(b)
        if not oge:
            data["oge"] = "Not OGE"
        else:
            data.setdefault("pb_test", "Not accepted")
        if key == "discord_username":
            data["username"] = names[0].lstrip("@") if names else ""
            rare = [BADGE_BY_SHORT.get(x.strip(), x.strip()) for x in ", ".join(extra).split(",") if x.strip()]
            if rare and all(x in BADGE_GROUPS["Rare"] for x in rare):
                data["has_rare"], data["rare_badges"] = "Yes", rare
            else:
                data["has_rare"] = "No"
        elif items or extra:
            first, rest = (items[0], extra) if items else (extra[0], extra[1:])  # old posts: badges were a "- " line
            data["badges"] = [x.strip() for x in first.split(",")]
            data["notes"] = ", ".join(rest) or None
    elif key == "tiktok_username":
        data["username"] = names[0].lstrip("@") if names else ""
        passkey, number = "Passkey" in bullets, "Number" in bullets
        data["tt_access"] = "Both" if passkey and number else "Passkey" if passkey else "Number" if number else "Neither"
        data["tt_type"] = next((b for b in bullets if b in ("Fonted / Duped", "Not Fonted / Duped")), None)
    elif key == "telegram_username":
        data["usernames"] = "\n".join(names)
        data["notes"] = ", ".join(bullets) or None
    elif key == "telegram_gift":
        data["gift"] = link
        data["notes"] = ", ".join(bullets) or None
    elif key == "discord_vanity":
        # current posts list each vanity on its own line (".gg/x", bold); older ones had a "- " in front
        found = [f".gg{ln}" for ln in items if re.fullmatch(r"/\S+", ln)]
        found += [ln for ln in [*bullets, *lines[1:]] if re.fullmatch(r"\.?gg/\S+", ln)]
        data["item"] = "\n".join(dict.fromkeys(found))
    else:
        return None
    return key, data
