"""Premium Telegram emoji storage, prompt instructions, and HTML rendering."""

import html
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv

load_dotenv()
EMOJI_DB_PATH = os.getenv("DATABASE_PATH", "bot.db")
SECTION_EMOJI_TAGS = {
    "greeting": "GREETING",
    "channel": "CHANNEL",
    "donation_count": "DONATION_COUNT",
    "total_income": "TOTAL_INCOME",
    "donate_title": "DONATE_TITLE",
    "username": "USERNAME",
    "date": "DATE",
    "price": "PRICE",
    "message": "MESSAGE",
}
SECTION_EMOJI_FALLBACKS = {
    "greeting": "😊",
    "channel": "📢",
    "donation_count": "🔢",
    "total_income": "💰",
    "donate_title": "📱",
    "username": "🔗",
    "date": "🌟",
    "price": "💵",
    "message": "💲",
}
DEFAULT_PREMIUM_EMOJIS = {
    "DONATE_TITLE": ("5116159438062879454", "📱"),
    "USERNAME": ("5271604874419647061", "🔗"),
    "DATE": ("5064709487953183440", "🌟"),
    "PRICE": ("5409048419211682843", "💵"),
    "MESSAGE": ("5076072901971543033", "💲"),
    "BUTTON_DONATE": ("5409048419211682843", "💵"),
    "BUTTON_CHANNEL": ("5424818078833715060", "📢"),
    "BUTTON_ENGLISH": ("5474446335744680905", "🇬🇧"),
    "BUTTON_PERSIAN": ("5269324659102335906", "🇮🇷"),
}
EMOJI_PROMPT = """استفاده از لیست ایموجی‌ها:
از کلیدهای متنی مشخص‌شده در لیست زیر برای علامت‌گذاری احساسات/واکنش‌ها در متن خروجی استفاده کن (مثلاً `CONFIRM`, `LAUGHING`, `EMBARRASSED` و ...).

لیست ایموجی:
{emoji_list}

قوانین:
1. هنگام نیاز به نشان‌دادن احساس یا واکنش، به‌جای درج ایموجی یا توضیح احساس، کلید مربوطه را در متن قرار بده.
2. ایموجی‌ها خودکار جایگزین تگ اسم انگلیسی خودشان می‌شوند؛ پس مطمئن شو فقط از تگ‌های داخل لیست استفاده کنی.
3. می‌توانی چند کلید را پشت سر هم قرار دهی تا چند واکنش ترکیبی نشان داده شود (مثلاً: `CONFIRM LAUGHING`). یا حتی می‌توانی تگ را چندبار در متن استفاده کنی.
"""


@dataclass(frozen=True)
class PremiumEmoji:
    tag: str
    emoji_id: str
    description: str


def emoji_db():
    connection = sqlite3.connect(EMOJI_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_emoji_db():
    with emoji_db() as connection:
        connection.execute("""CREATE TABLE IF NOT EXISTS premium_emojis (
            tag TEXT PRIMARY KEY COLLATE NOCASE,
            emoji_id TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT ''
        )""")
        connection.executemany(
            "INSERT OR IGNORE INTO premium_emojis(tag, emoji_id, description) VALUES (?, ?, ?)",
            [(tag, emoji_id, fallback) for tag, (emoji_id, fallback) in DEFAULT_PREMIUM_EMOJIS.items()],
        )


def _tag(tag: str) -> str:
    value = tag.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,31}", value):
        raise ValueError("tag must contain only English letters, numbers, and underscores")
    return value


def save_emoji(tag: str, emoji_id: str | int, description: str = ""):
    normalized_tag = _tag(tag)
    value = str(emoji_id).strip()
    if not value.isdigit():
        raise ValueError("emoji_id must be numeric")
    with emoji_db() as connection:
        connection.execute(
            "INSERT INTO premium_emojis(tag, emoji_id, description) VALUES (?, ?, ?) "
            "ON CONFLICT(tag) DO UPDATE SET emoji_id=excluded.emoji_id, description=excluded.description",
            (normalized_tag, value, description.strip()),
        )


def delete_emoji(tag: str) -> bool:
    with emoji_db() as connection:
        result = connection.execute("DELETE FROM premium_emojis WHERE tag = ?", (_tag(tag),))
        return result.rowcount > 0


def get_emojis() -> list[PremiumEmoji]:
    init_emoji_db()
    with emoji_db() as connection:
        rows = connection.execute("SELECT tag, emoji_id, description FROM premium_emojis ORDER BY tag").fetchall()
    return [PremiumEmoji(row["tag"], row["emoji_id"], row["description"]) for row in rows]


def get_emoji(tag: str) -> PremiumEmoji | None:
    normalized_tag = _tag(tag)
    return next((item for item in get_emojis() if item.tag == normalized_tag), None)


def section_emoji(section: str) -> str:
    item = get_emoji(SECTION_EMOJI_TAGS[section])
    if not item:
        return ""
    fallback = SECTION_EMOJI_FALLBACKS[section]
    return f'<tg-emoji emoji-id="{item.emoji_id}">{fallback}</tg-emoji>'


def get_ai_prm_emojies_list() -> str:
    return "\n".join(
        f"`{item.tag}`: emoji-id=`{item.emoji_id}`; توضیح: {item.description or '-'}"
        for item in get_emojis()
    ) or "(هیچ ایموجی‌ای تنظیم نشده است)"


def build_emoji_prompt(user_prompt: str) -> str:
    return f"{user_prompt.strip()}\n\n{EMOJI_PROMPT.format(emoji_list=get_ai_prm_emojies_list())}"


def place_ai_prm_emojies(text: str) -> str:
    """Replace configured English tags with Telegram HTML tg-emoji elements."""
    replacements = {item.tag: item for item in get_emojis()}
    if not replacements:
        return text

    pattern = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9_]*)(?![A-Za-z0-9_])")

    def replace(match: re.Match[str]) -> str:
        item = replacements.get(match.group(1).upper())
        if not item:
            return match.group(0)
        fallback = html.escape(item.description or "🙂")
        return f'<tg-emoji emoji-id="{item.emoji_id}">{fallback}</tg-emoji>'

    return pattern.sub(replace, text)


def render_html(text: str) -> str:
    """Apply premium emoji replacement while keeping the result Telegram HTML."""
    return place_ai_prm_emojies(text)


init_emoji_db()

