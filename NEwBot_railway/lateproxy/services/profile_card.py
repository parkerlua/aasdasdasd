"""The public profile card for Discord listings: avatar, name, badges, "Member Since" (drawn with Pillow).

Drawn at 2x and shrunk for smooth edges. Hidden fields are grey bars, and the avatar is blurred by default, so a
buyer can't use the image to find the account.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..paths import BADGES, FONTS

W, H, S = 900, 600, 2  # card size, and the supersampling factor

BG_BANNER, BG_BODY = (20, 21, 26), (6, 7, 9)
AVATAR_GREY, RING, BAR = (122, 129, 143), (5, 6, 7), (59, 60, 66)
WHITE, GRAY, TAG = (255, 255, 255), (190, 192, 200), (195, 197, 205)

STATUS_COLORS = {"online": (35, 165, 90), "idle": (240, 178, 50), "dnd": (242, 63, 67), "offline": (128, 132, 142)}
ONLINE_MODES = {"Online": "online", "Idle": "idle", "Do Not Disturb": "dnd", "Offline": "offline"}

# badge name used in the bot -> file in assets/badges (without .png).
BADGE_FILES: dict[str, str] = {
    "HypeSquad Events": "hypesquad_events", "HypeSquad Bravery": "hypesquad_bravery",
    "HypeSquad Brilliance": "hypesquad_brilliance", "HypeSquad Balance": "hypesquad_balance",
    "Early Supporter": "early_supporter", "Moderator": "moderator", "Mod Alumni": "mod_alumni",  # alumni is the orange one
    "Discord Staff": "staff", "Partner": "partnered_server_owner", "Early Verified Dev": "early_verified_developer",
    "Green Bug Hunter": "bug_hunter_level_1", "Golden Bug Hunter": "bug_hunter_level_2",
    "Active Developer": "active_developer", "Quest Completer": "quest_completer",
    "Originally Known As": "originally_known_as", "Nitro": "nitro",
}
for _gift in ("Patron", "Champion", "Hero", "Legend", "Icon", "Luminary"):
    BADGE_FILES[f"Gift — {_gift}"] = f"gift_{_gift.lower()}"
for _m in (1, 2, 3, 6, 9, 12, 15, 18, 24):
    BADGE_FILES[f"Boost — {_m} Month{'s' if _m != 1 else ''}"] = f"boosting_{_m}_months"
for _tier in ("Bronze — 1 Month", "Silver — 3 Months", "Gold — 6 Months", "Platinum — 12 Months",
              "Diamond — 24 Months", "Emerald — 36 Months", "Ruby — 60 Months", "Opal — 72+ Months"):
    BADGE_FILES[f"Nitro {_tier}"] = f"nitro_{_tier.split(' ')[0].lower()}"

DISCORD_LAUNCH = datetime(2015, 5, 13)
DATE_FORMATS = ("%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y")


def parse_date(text: str) -> str:
    """'7/16/2019', '2019-07-16', 'Jul 16 2019' -> 'Jul 16, 2019'. Raises ValueError with a message to show the user."""
    text = " ".join(text.replace(",", ", ").split()).replace(" ,", ",")
    for fmt in DATE_FORMATS:
        try:
            d = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if d < DISCORD_LAUNCH:
            raise ValueError("Discord didn't exist before May 13, 2015.")
        if d > datetime.now():
            raise ValueError("That date is in the future.")
        return f"{d.strftime('%b')} {d.day}, {d.year}"
    raise ValueError("Send the date like Jul 16, 2019 (or 7/16/2019).")


@dataclass
class CardData:
    created: str                          # 'Jul 16, 2019'
    online: str = "offline"               # online | idle | dnd | offline
    display: str = ""                     # empty -> hidden bar
    username: str = ""
    show_username: bool = False           # username listings show it, badge listings hide it
    badges: list[str] = field(default_factory=list)
    tag: str = ""                         # top-right line
    avatar: bytes | None = None
    blur_avatar: bool = True


def _font(size: int, weight: int) -> ImageFont.FreeTypeFont:
    path = FONTS / "Inter.ttf"
    if not path.exists():
        return ImageFont.load_default(size * S)
    f = ImageFont.truetype(str(path), size * S)
    f.set_variation_by_axes([14, weight])
    return f


def _badge_image(name: str) -> Image.Image | None:
    key = BADGE_FILES.get(name)
    path = BADGES / f"{key}.png" if key else None
    return Image.open(path).convert("RGBA") if path and path.exists() else None


def _circle(d: ImageDraw.ImageDraw, cx: int, cy: int, r: int, fill) -> None:
    d.ellipse([(cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S], fill=fill)


def _paste_avatar(img: Image.Image, avatar: bytes, blur: bool) -> bool:
    try:
        av = Image.open(io.BytesIO(avatar)).convert("RGB")
    except Exception:
        return False
    size = 210 * S
    av = av.resize((size, size), Image.LANCZOS)
    if blur:
        av = av.filter(ImageFilter.GaussianBlur(radius=14 * S))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
    img.paste(av, ((157 - 105) * S, (167 - 105) * S), mask)
    return True


def render(card: CardData) -> bytes:
    """PNG bytes of the card."""
    img = Image.new("RGB", (W * S, H * S), BG_BODY)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W * S, 168 * S], fill=BG_BANNER)
    if card.tag:
        d.text((870 * S, 42 * S), card.tag, font=_font(24, 600), fill=TAG, anchor="rm")

    _circle(d, 157, 167, 119, RING)
    _circle(d, 157, 167, 105, AVATAR_GREY)
    if card.avatar:
        _paste_avatar(img, card.avatar, card.blur_avatar)
        d = ImageDraw.Draw(img)

    cx, cy = 240, 248  # status dot
    _circle(d, cx, cy, 27, RING)
    _circle(d, cx, cy, 20, STATUS_COLORS.get(card.online, STATUS_COLORS["offline"]))
    if card.online == "idle":
        _circle(d, cx - 7, cy - 7, 10, RING)
    elif card.online == "dnd":
        d.rounded_rectangle([(cx - 12) * S, (cy - 4) * S, (cx + 12) * S, (cy + 4) * S], radius=4 * S, fill=RING)
    elif card.online != "online":
        _circle(d, cx, cy, 8, RING)

    if card.display.strip():
        d.text((52 * S, 337 * S), card.display.strip(), font=_font(34, 700), fill=WHITE, anchor="lm")
    else:
        d.rounded_rectangle([52 * S, 316 * S, 303 * S, 357 * S], radius=10 * S, fill=BAR)

    x = 52
    if card.show_username and card.username:
        name = card.username.lstrip("@")
        font = _font(22, 500)
        d.text((x * S, 406 * S), name, font=font, fill=GRAY, anchor="lm")
        x += int(d.textlength(name, font=font) / S) + 20
    else:
        d.rounded_rectangle([52 * S, 392 * S, 243 * S, 421 * S], radius=10 * S, fill=BAR)
        x = 265
    for badge_name in dict.fromkeys(card.badges):  # no duplicates, keep order
        icon = _badge_image(badge_name)
        if icon is None:
            continue
        size = 36 * S
        icon = icon.resize((size, size), Image.LANCZOS)
        img.paste(icon, (x * S, 406 * S - size // 2), icon)
        x += 36 + 14

    d.text((52 * S, 500 * S), "Member Since", font=_font(25, 700), fill=WHITE, anchor="lm")
    d.text((52 * S, 547 * S), card.created, font=_font(26, 400), fill=GRAY, anchor="lm")

    out = io.BytesIO()
    img.resize((W, H), Image.LANCZOS).save(out, "PNG", optimize=True)
    return out.getvalue()
