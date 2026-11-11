"""Listing flow definitions: the questions a seller is asked for each category.

Add or reorder steps here; the wizard (handlers/wizard.py) just walks them.

Data keys that start with "_" are wizard-only scratch values (never saved with the listing).
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from ..services.profile_card import parse_date
from ..ui.buttons import GREEN, RED


@dataclass
class Step:
    key: str
    kind: str  # choice | multi | text | amount | photo | confirm
    prompt: str
    label: str = ""  # shown in the summary; empty = hidden
    options: list = field(default_factory=list)  # [(button label, stored value, icon key, style)]
    skip: tuple | None = None  # (button label, stored value, icon key, style) for optional steps
    validate: Callable | None = None  # raw text -> value, raises ValueError(msg)
    when: Callable | None = None  # data -> bool, step is skipped if False
    sub: bool = False  # follow-up step: no Back button
    example: str | None = None  # image (inside assets/) sent along with the prompt
    per_row: int = 0  # choice buttons per row (0 = automatic)
    groups: dict = field(default_factory=dict)  # multi: {group name: [(text, icon key)]}
    hook: str = ""  # named action the wizard runs right after this step is answered (see handlers/wizard.py)


@dataclass
class Flow:
    key: str
    name: str
    emoji: str
    icon: str  # key in assets/icons.json
    title_key: str  # which answer is used as the listing's title
    steps: list
    card: bool = False  # the public image is a generated profile card (services/profile_card.py)


# ---------- validators ----------
def amount(text: str) -> float:
    try:
        value = float(text.replace("$", "").replace(",", "").strip())
    except ValueError:
        raise ValueError("Send a number, e.g. 40") from None
    if value <= 0:
        raise ValueError("Amount must be greater than 0")
    return int(value) if value == int(value) else round(value, 2)


def discord_id(text: str) -> str:
    text = text.strip()
    if not re.fullmatch(r"\d{17,20}", text):
        raise ValueError("A Discord user ID is 17–20 digits.")
    return text


def lines(text: str) -> str:
    items = [line.strip() for line in text.splitlines() if line.strip()]
    if not items:
        raise ValueError("Send at least one line.")
    return "\n".join(items)


def nonempty(text: str) -> str:
    text = text.strip()
    if not text:
        raise ValueError("Can't be empty.")
    return text


def vanity(item: str) -> str:
    """Whatever comes after the last "/" is the vanity; with no slash the whole text is. Always shown as .gg/<vanity>:
    discord.gg/vcs, https://discord.gg/vcs, asdfasd.gg/vcs, gg/vcs, vcs -> .gg/vcs"""
    name = item.strip().rstrip("/").rsplit("/", 1)[-1].strip()
    return f".gg/{name}" if name else item.strip()


def vanity_lines(text: str) -> str:
    """One vanity per line, every one shortened to .gg/xxx."""
    return "\n".join(vanity(line) for line in lines(text).splitlines())


def gift_link(text: str) -> str:
    text = text.strip()
    if not re.fullmatch(r"(?:https?://)?(?:t|telegram)\.me/\S+", text, re.I):
        raise ValueError("Send the gift link, e.g. t.me/nft/PlushPepe-1234")
    return text if text.lower().startswith("http") else f"https://{text}"


# ---------- shared step groups ----------
def _co_steps():
    return [
        Step("co_amount", "amount", "💰 <b>Any C/O on it?</b>\nType the amount, or tap <b>No C/O</b>.",
             label="C/O", skip=("No C/O", None, "no_co", "primary")),
        Step("co_proof", "photo", "📸 <b>Show the C/O</b>\nUpload a screenshot of the offer.",
             label="C/O proof", when=lambda d: d.get("co_amount") is not None, sub=True),
    ]


def _tail_steps(notes_prompt="📝 <b>Anything else?</b>\nAdd details buyers should know."):
    return [
        Step("price", "amount", "💵 <b>What's your BIN?</b>\nType a price, or tap <b>Open to offers</b> if you'd rather negotiate.",
             label="BIN", skip=("Open to offers", "Highest Offer", "offers", "primary")),
        Step("notes", "text", notes_prompt, label="Notes", skip=("No notes", None, "skip", "primary")),
        Step("confirm", "confirm", "Here's your listing. Good to go?"),
    ]


EMAIL_DOMAINS = ["Gmail", "Outlook", "Hotmail", "Yahoo", "iCloud", "ProtonMail", "Other"]


def _oge_steps():
    return [
        Step("oge", "choice", "Does the account still have its original email (OGE)?", label="OGE",
             options=[("Yes, OGE", "OGE", None, GREEN), ("No, changed", "Not OGE", None, RED)]),
        Step("email_domain", "choice", "Nice. Which email provider is it on?", label="Email",
             options=[(d, d, None, None) for d in EMAIL_DOMAINS], when=lambda d: d.get("oge") == "OGE"),
        Step("email_domain_other", "text", "Reply to this with what domain it is:", label="Domain",
             validate=nonempty, sub=True,
             when=lambda d: d.get("oge") == "OGE" and d.get("email_domain") == "Other"),
        Step("pb_test", "choice", "Do you accept a <b>Pullback (PB) test</b>?", label="PB test",
             options=[("Yes, accepted", "Accepted", None, GREEN), ("No", "Not accepted", None, RED)],
             when=lambda d: d.get("oge") == "OGE"),
    ]


def _id_step():
    return Step("discord_id", "text",
                "Drop the account's <b>Discord user ID</b> (17–20 digits).\n"
                '<a href="https://support.discord.com/hc/en-us/articles/206346498">How to find it</a>',
                label="User ID", validate=discord_id, hook="discord_lookup")


def _standing_step():
    return Step("standing", "choice", "How is the account's <b>standing</b>?", label="Standing", per_row=2,
                options=[("All Good", "All Good", "all_good", "success"), ("Limited", "Limited", "limited", None),
                         ("Heavily Limited", "Heavily Limited", "very_limited", None),
                         ("At Risk", "At Risk", "at_risk", "danger")])


def _profile_steps():
    """The seller builds the profile card. Anything the Discord ID already told us is skipped.
    Their real screenshot is a private proof that only the reviewers see."""
    return [
        Step("display", "text", "🪪 <b>Display name</b>\nWhat's the account's display name? Or tap <b>Hide it</b>.",
             label="Display name", validate=nonempty, skip=("Hide it", "", None, None),
             when=lambda d: not d.get("_display_known")),
        Step("created", "text", "📅 <b>Account creation date</b>\nWhen was the account created? e.g. <b>Jul 16, 2019</b>",
             label="Created", validate=parse_date, when=lambda d: not d.get("created")),
        Step("online", "choice", "🟢 <b>Online mode</b>\nWhich status dot should the profile show?", label="Online mode", per_row=2,
             options=[("Online", "Online", None, None), ("Idle", "Idle", None, None),
                      ("Do Not Disturb", "Do Not Disturb", None, None), ("Offline", "Offline", None, None)]),
        Step("proof_image", "photo",
             "📸 <b>Proof screenshot</b>\nPut <b>@late</b> in your status and send a real screenshot of the account "
             "<b>1:1 like the example</b>: only the profile card, nothing else and no extra UI.\n"
             "<i>Only the reviewer sees this. The public post uses the profile card you just built.</i>",
             label="Proof (private)", example="images/example_profile.png"),
    ]


# ---------- badges ----------
def _slug(text: str) -> str:
    return "badge_" + re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _tiers(prefix, months):
    return [f"{prefix} — {m} Month{'s' if m != 1 else ''}" for m in months]


BADGE_GROUPS = {
    "Rare": ["HypeSquad Events", "Early Supporter", "Mod Alumni", "Moderator", "Discord Staff", "Partner",
             "Early Verified Dev", "Green Bug Hunter", "Golden Bug Hunter"],
    "Nitro": ["Nitro", "Nitro Bronze — 1 Month", "Nitro Silver — 3 Months", "Nitro Gold — 6 Months",
              "Nitro Platinum — 12 Months", "Nitro Diamond — 24 Months", "Nitro Emerald — 36 Months",
              "Nitro Ruby — 60 Months", "Nitro Opal — 72+ Months"],
    "Boosts": _tiers("Boost", [1, 2, 3, 6, 9, 12, 15, 18, 24]),
    "Other": ["HypeSquad Bravery", "HypeSquad Brilliance", "HypeSquad Balance", "Active Developer",
              "Quest Completer", "Originally Known As"],
    "Gift": ["Gift — Patron", "Gift — Champion", "Gift — Hero", "Gift — Legend", "Gift — Icon", "Gift — Luminary"],
}
BADGE_GROUP_ICONS = {g: f"group_{g.lower()}" for g in BADGE_GROUPS}


def _rare_badge_steps():
    """Username listings: ask if the account has rare badges, then show only the Rare list."""
    return [
        Step("has_rare", "choice", "Does the account have any <b>rare badges</b>?",
             options=[("Yes", "Yes", None, None), ("No", "No", None, None)]),
        Step("rare_badges", "multi", "Pick the rare badges on the account.", label="Rare badges",
             when=lambda d: d.get("has_rare") == "Yes",
             groups={"Rare": [(t, _slug(t)) for t in BADGE_GROUPS["Rare"]]}),
    ]


def _badge_step():
    return Step("badges", "multi", "Pick every badge on the account.", label="Badges",
                groups={g: [(t, _slug(t)) for t in items] for g, items in BADGE_GROUPS.items()})


# ---------- the flows ----------
DISCORD_USERNAME = Flow(
    "discord_username", "Discord Usernames", "🎮", "discord", "username",
    [
        *_oge_steps(),
        _id_step(),
        Step("username", "text", "What's the <b>username</b>?", label="Username", validate=nonempty,
             when=lambda d: not d.get("_username_known")),
        *_rare_badge_steps(),
        *_profile_steps(),
        _standing_step(),
        *_co_steps(),
        *_tail_steps(),
    ],
    card=True,
)

DISCORD_BADGE = Flow(
    "discord_badge", "Discord Badges", "🎮", "discord", "badges",
    [
        *_oge_steps(),
        _id_step(),
        _badge_step(),
        *_profile_steps(),
        _standing_step(),
        *_co_steps(),
        *_tail_steps(),
    ],
    card=True,
)

TELEGRAM_USERNAME = Flow(
    "telegram_username", "Telegram Usernames", "✈️", "telegram", "usernames",
    [
        Step("usernames", "text", "Which username(s) are you selling? One per line.", label="Username(s)", validate=lines),
        *_co_steps(),
        *_tail_steps(),
    ],
)


def _generic(key, name, emoji, icon, what, validate=nonempty):
    return Flow(key, name, emoji, icon, "item", [
        Step("item", "text", f"Send the {what}.", label="Item", validate=validate),
        *_co_steps(),
        *_tail_steps(),
    ])


def _tiktok_steps():
    tail = _tail_steps()
    price, confirm = tail[0], tail[-1]  # no notes question for TikToks
    return [
        Step("tt_access", "choice", "🔐 <b>Passkey / number</b>\nDoes the account have a passkey or a phone number on it?",
             label="Passkey/Number", per_row=2,
             options=[("Passkey", "Passkey", None, None), ("Number", "Number", None, None),
                      ("Both", "Both", None, None), ("Neither", "Neither", None, None)]),
        Step("username", "text", "What's the <b>TikTok username</b>?", label="Username", validate=nonempty),
        Step("tt_type", "choice", "Is the username fonted / duped?", label="Type", per_row=1,
             options=[("Fonted / Duped", "Fonted / Duped", None, None),
                      ("Not Fonted / Duped", "Not Fonted / Duped", None, None)]),
        *_co_steps(),
        price,
        Step("account_image", "photo", "📸 <b>Listing screenshot</b>\nSend a screenshot of the listing for the proxy.",
             label="Screenshot"),
        confirm,
    ]


TIKTOK_USERNAME = Flow("tiktok_username", "TikTok Usernames", "🎵", "tiktok", "username", _tiktok_steps())

FLOWS: dict[str, Flow] = {f.key: f for f in [
    _generic("discord_vanity", "Discord Vanities", "🎮", "discord", "vanity link(s) — one per line",
             validate=vanity_lines),
    DISCORD_USERNAME,
    DISCORD_BADGE,
    TELEGRAM_USERNAME,
    Flow("telegram_gift", "Telegram Gifts", "✈️", "telegram", "gift", [
        Step("gift", "text", "🎁 <b>Telegram gift link?</b>\nSend the gift's link (t.me/nft/…).",
             label="Gift link", validate=gift_link),
        *_co_steps(),
        *_tail_steps("📝 <b>Notes</b>\nWhatever you type here <b>will be shown</b> in the public post.\n"
                     "Type your notes, or tap <b>No notes</b>."),
    ]),
    TIKTOK_USERNAME,
    _generic("other_usernames", "Other Handles", "👤", "other_usernames", "username(s) and platform"),
    _generic("other_stock", "Other Items", "📦", "other_stock", "item description"),
]}

# still defined (old listings may use them) but not offered in the category menu
HIDDEN = {"other_usernames", "other_stock"}
MENU_FLOWS = [f for f in FLOWS.values() if f.key not in HIDDEN]

# saved with a card listing even though no (visible) step owns them
PERSIST_EXTRA = ("account_image", "verified_badges", "username", "display", "created")


def visible(flow: Flow, data: dict) -> list[Step]:
    return [s for s in flow.steps if s.when is None or s.when(data)]


def next_index(flow: Flow, idx: int, data: dict) -> int:
    for i in range(idx + 1, len(flow.steps)):
        step = flow.steps[i]
        if step.when is None or step.when(data):
            return i
    return len(flow.steps) - 1

