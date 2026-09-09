import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path


EMOJI_DATABASE = Path(__file__).with_name("emojis.db")
DEFAULT_EMOJI_ID = "[prim_id]"


@dataclass(frozen=True)
class PremiumEmoji:
    tag: str
    emoji_id: str
    fallback: str = "😊"

    def html(self) -> str:
        return f'<tg-emoji emoji-id="{self.emoji_id}">{self.fallback}</tg-emoji>'


EMOJI_TAGS = (
    "GENERAL", "GREETING", "CHANNEL", "GROUP", "DONATION_COUNT",
    "TOTAL_INCOME", "DONATE_TITLE", "USERNAME", "DATE", "PRICE", "MESSAGE",
    "DONATE", "ENGLISH", "PERSIAN", "INCOME", "DELETE_ACCOUNT", "YES", "NO",
    "BACK",
)
DEFAULT_EMOJIS = {
    "BACK": "5253997076169115797",
    "CHANNEL": "5424818078833715060",
    "DATE": "5064709487953183440",
    "DELETE_ACCOUNT": "5395695537687123235",
    "DONATE": "5409048419211682843",
    "DONATE_TITLE": "5116159438062879454",
    "DONATION_COUNT": "4904848288345228262",
    "ENGLISH": "5474446335744680905",
    "GENERAL": "5237764698245450016",
    "GREETING": "4918354603281482671",
    "GROUP": "5443038326535759644",
    "INCOME": "5449683594425410231",
    "MESSAGE": "5076072901971543033",
    "NO": "5210952531676504517",
    "PERSIAN": "5269324659102335906",
    "PRICE": "5409048419211682843",
    "TOTAL_INCOME": "5244837092042750681",
    "USERNAME": "5271604874419647061",
    "YES": "5206607081334906820",
}
EMOJI_CONFIG_VERSION = 4
STANDARD_EMOJI_RE = re.compile(
    "[\\U0001F1E6-\\U0001F1FF\\U0001F300-\\U0001FAFF\\u2600-\\u27BF]"
)


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(EMOJI_DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def init_emoji_db() -> None:
    with _connect() as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS premium_emojis "
            "(tag TEXT PRIMARY KEY, emoji_id TEXT NOT NULL, description TEXT NOT NULL DEFAULT '')"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS emoji_meta "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        for tag, emoji_id in DEFAULT_EMOJIS.items():
            connection.execute(
                "INSERT OR IGNORE INTO premium_emojis(tag, emoji_id) VALUES (?, ?)",
                (tag, emoji_id),
            )
        version = connection.execute(
            "SELECT value FROM emoji_meta WHERE key = 'config_version'"
        ).fetchone()
        if not version:
            for tag, emoji_id in DEFAULT_EMOJIS.items():
                connection.execute(
                    "UPDATE premium_emojis SET emoji_id = ? WHERE tag = ?",
                    (emoji_id, tag),
                )
        elif int(version[0]) < EMOJI_CONFIG_VERSION:
            for tag in (
                "DONATE_TITLE", "USERNAME", "DATE", "PRICE", "MESSAGE",
                "DONATE", "CHANNEL",
            ):
                connection.execute(
                    "UPDATE premium_emojis SET emoji_id = ? WHERE tag = ?",
                    (DEFAULT_EMOJIS[tag], tag),
                )
        if not version or int(version[0]) < EMOJI_CONFIG_VERSION:
            connection.execute(
                "INSERT INTO emoji_meta(key, value) VALUES ('config_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(EMOJI_CONFIG_VERSION),),
            )


def save_emoji(tag: str, emoji_id: str, description: str = "") -> None:
    tag = tag.strip().upper()
    if not tag or not emoji_id.isdigit():
        raise ValueError("tag and numeric emoji id are required")
    init_emoji_db()
    with _connect() as connection:
        connection.execute(
            "INSERT INTO premium_emojis(tag, emoji_id, description) VALUES (?, ?, ?) "
            "ON CONFLICT(tag) DO UPDATE SET emoji_id=excluded.emoji_id, description=excluded.description",
            (tag, emoji_id, description.strip()),
        )


def delete_emoji(tag: str) -> bool:
    init_emoji_db()
    with _connect() as connection:
        cursor = connection.execute("DELETE FROM premium_emojis WHERE tag = ?", (tag.strip().upper(),))
        return cursor.rowcount > 0


def get_emoji(tag: str) -> PremiumEmoji:
    init_emoji_db()
    with _connect() as connection:
        row = connection.execute(
            "SELECT tag, emoji_id FROM premium_emojis WHERE tag = ?", (tag.strip().upper(),)
        ).fetchone()
    return PremiumEmoji(row["tag"], row["emoji_id"]) if row else PremiumEmoji(tag.upper(), DEFAULT_EMOJI_ID)


def premium_emoji(tag: str) -> str:
    return get_emoji(tag).html()


def premium_emoji_id(tag: str) -> str:
    return get_emoji(tag).emoji_id


def replace_standard_emojis(text: str, tag: str = "MESSAGE") -> str:
    return STANDARD_EMOJI_RE.sub(premium_emoji(tag), text)


def get_ai_prm_emojies_list() -> str:
    init_emoji_db()
    with _connect() as connection:
        rows = connection.execute(
            "SELECT tag, emoji_id, description FROM premium_emojis ORDER BY tag"
        ).fetchall()
    return "\n".join(
        f"{row['tag']} | {row['emoji_id']} | {row['description']}" for row in rows
    ) or "لیست ایموجی‌ها خالی است."


def section_emoji(section: str) -> str:
    return premium_emoji(section)


def build_emoji_prompt(text: str) -> str:
    return text


def place_ai_prm_emojies(text: str) -> str:
    return replace_standard_emojis(text)