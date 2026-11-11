"""Telegram-HTML -> (plain text, entities).

The bot builds every post as Telegram HTML (<b>, <a>, <tg-emoji>...). The Bot API understands that, but the
Premium userbot (Telethon) sends raw entities, and Telethon's own HTML parser doesn't know custom emojis.
This converts the HTML itself, with correct UTF-16 offsets (Telegram counts in UTF-16 code units).
"""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser

_KINDS = {
    "b": "bold", "strong": "bold", "i": "italic", "em": "italic", "u": "underline", "ins": "underline",
    "s": "strike", "strike": "strike", "del": "strike", "code": "code", "pre": "pre",
    "a": "url", "tg-emoji": "custom_emoji", "tg-spoiler": "spoiler",
}


@dataclass(frozen=True)
class Ent:
    kind: str          # bold | italic | underline | strike | code | pre | url | custom_emoji | spoiler
    offset: int        # UTF-16 code units
    length: int
    value: str = ""    # url, or the custom emoji id


def utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.pos = 0
        self.open: list[tuple[str, int, dict]] = []
        self.ents: list[Ent] = []

    def handle_starttag(self, tag, attrs):
        if tag in _KINDS:
            self.open.append((tag, self.pos, dict(attrs)))

    def handle_endtag(self, tag):
        for i in range(len(self.open) - 1, -1, -1):  # close the innermost matching tag
            name, start, attrs = self.open[i]
            if name == tag:
                del self.open[i]
                length = self.pos - start
                if length > 0:
                    kind = _KINDS[tag]
                    value = attrs.get("href", "") if kind == "url" else attrs.get("emoji-id", "") if kind == "custom_emoji" else ""
                    if kind == "url" and not value:
                        return
                    if kind == "custom_emoji" and not value.isdigit():
                        return
                    self.ents.append(Ent(kind, start, length, value))
                return

    def handle_data(self, data):
        self.parts.append(data)
        self.pos += utf16_len(data)


def parse_html(html_text: str) -> tuple[str, list[Ent]]:
    c = _Collector()
    c.feed(html_text)
    c.close()
    return "".join(c.parts), sorted(c.ents, key=lambda e: (e.offset, -e.length))


def to_telethon(ents: list[Ent]) -> list:
    """Entity objects for Telethon's send_message / send_file / edit_message (formatting_entities=...)."""
    from telethon.tl import types as t

    out = []
    for e in ents:
        if e.kind == "bold":
            out.append(t.MessageEntityBold(e.offset, e.length))
        elif e.kind == "italic":
            out.append(t.MessageEntityItalic(e.offset, e.length))
        elif e.kind == "underline":
            out.append(t.MessageEntityUnderline(e.offset, e.length))
        elif e.kind == "strike":
            out.append(t.MessageEntityStrike(e.offset, e.length))
        elif e.kind == "code":
            out.append(t.MessageEntityCode(e.offset, e.length))
        elif e.kind == "pre":
            out.append(t.MessageEntityPre(e.offset, e.length, ""))
        elif e.kind == "spoiler":
            out.append(t.MessageEntitySpoiler(e.offset, e.length))
        elif e.kind == "url":
            out.append(t.MessageEntityTextUrl(e.offset, e.length, e.value))
        elif e.kind == "custom_emoji":
            out.append(t.MessageEntityCustomEmoji(e.offset, e.length, int(e.value)))
    return out


def html_to_telethon(html_text: str) -> tuple[str, list]:
    text, ents = parse_html(html_text)
    return text, to_telethon(ents)
