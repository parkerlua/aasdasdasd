"""Category-specific questions and private proof attachments."""

import json


RARE = ("HypeSquad Events", "Early Supporter", "Mod Alumni", "Moderator", "Discord Staff",
        "Partner", "Early Verified Dev", "Green Bug Hunter", "Golden Bug Hunter")
BADGES = {
    "Rare": RARE,
    "Nitro": ("Nitro", *(f"Nitro · {months} months" for months in (1, 3, 6, 12, 24, 36, 60, 72))),
    "Boosts": tuple(f"Boost · {months} months" for months in (1, 2, 3, 6, 9, 12, 15, 18, 24)),
    "Other": ("HypeSquad Bravery", "HypeSquad Brilliance", "HypeSquad Balance",
              "Active Developer", "Quest Completer"),
}

SINGLE_SELECT_BADGE_GROUPS = ('Nitro', 'Boosts')

NITRO_DISPLAY = (
    ("Nitro", 16), ("Bronze", 17), ("Silver", 16), ("Gold", 18),
    ("Platinum", 19), ("Diamond", 20), ("Emerald", 21), ("Ruby", 22), ("Opal", 23),
)

QUESTIONS = {
    "oge": ("Original email", "Does the account still have its original email?", ("Yes", "No")),
    "email": ("Email provider", "Which email provider is it on?", ("Gmail", "Outlook", "Hotmail", "Yahoo", "iCloud", "ProtonMail", "Other")),
    "domain": ("Email domain", "Enter the provider or domain only.", ()),
    "pb": ("Pullback test", "Do you accept a pullback test?", ("Yes", "No")),
    "rare": ("Rare badges", "Does the account have any rare badges?", ("Yes", "No")),
    "standing": ("Account standing", "How is the account standing?", ("All Good", "Limited", "Heavily Limited", "At Risk")),
    "access": ("Passkey / number", "Does the TikTok account have a passkey or phone number?", ("Passkey", "Number", "Both", "Neither")),
    "tiktok_type": ("Username type", "Is the username fonted or duped?", ("Fonted / Duped", "Neither")),
}
PHOTOS = {
    "proof": "Put @Floral in your Discord status and send a screenshot cropped to the profile card. Only the reviewer sees it.",
    "offer_proof": "Send a screenshot of the current offer for private review.",
    "tiktok_proof": "Send a screenshot of the TikTok listing for private review.",
}
BUTTON = "vanity_detail:"


def load(db, user_id):
    row = db.execute("SELECT details FROM vanity_drafts WHERE user_id = ?", (user_id,)).fetchone()
    values = json.loads(row[0]) if row else {}
    if values.get("_group") not in BADGES:
        values.pop("_group", None)
    if "badges" in values:
        values["badges"] = [badge for badge in values["badges"] if badge != "Originally Known As"
                             and not badge.startswith("Gift · ")]
        for group in SINGLE_SELECT_BADGE_GROUPS:
            chosen = values["badges"]
            tiers = [badge for badge in chosen if badge in BADGES[group]]
            if len(tiers) > 1:
                values["badges"] = [badge for badge in chosen if badge not in BADGES[group]] + tiers[-1:]
    return values


def questions(category, values):
    if category in ("discord_username", "discord_badges"):
        return [
            "oge",
            * (["email", *(["domain"] if values.get("email") == "Other" else []), "pb"]
               if values.get("oge") == "Yes" else []),
            "discord_id",
            * (["rare", *(["badges"] if values.get("rare") == "Yes" else [])]
               if category == "discord_username" else ["badges"]),
            "proof", "standing",
        ]
    if category == "tiktok_username":
        return ["access", "tiktok_type"]
    return []


def screen(key, category, values):
    if key in PHOTOS:
        return PHOTOS[key], []
    if key != "badges":
        _, prompt, choices = QUESTIONS[key]
        return prompt, [(label, f"{BUTTON}{key}:{index}") for index, label in enumerate(choices)]

    groups = ("Rare",) if category == "discord_username" else tuple(BADGES)
    group = values.get("_group")
    if group not in groups:
        group = groups[0]
    chosen = values.get("badges", [])
    buttons = [(other, f"{BUTTON}group:{other}") for other in groups] if len(groups) > 1 else []
    buttons.extend(
        (f"{'✓ ' if label in chosen else ''}{NITRO_DISPLAY[index][0] if group == 'Nitro' else label}", f"{BUTTON}badges:{group}:{index}")
        for index, label in enumerate(BADGES[group])
    )
    buttons.append(("Done", f"{BUTTON}badges:done"))
    selected = ", ".join(chosen) if chosen else "None"
    return f"Select badges · {group}\n\nSelected ({len(chosen)}): {selected}", buttons


def describe(values):
    lines = [f"{label}: {values[key]}" for key, (label, _, _) in QUESTIONS.items()
             if key in values and key != "rare"]
    if values.get("badges"):
        lines.append("Badges: " + ", ".join(values["badges"]))
    return "\n".join(lines)
