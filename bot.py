import html
import hashlib
import json
import logging
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from emoji_manager import delete_emoji, get_ai_prm_emojies_list, init_emoji_db, premium_emoji_id, replace_standard_emojis, save_emoji, section_emoji

load_dotenv()

DB_PATH = os.getenv("DATABASE_PATH", "bot.db")
API_ROOT = "https://daramet.com/api/v2"
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
LANGUAGE, TOKEN, LINK, INITIAL_CHAT_ID, DESTINATIONS, CHAT_IDS = range(6)
EMOJI_VALUE = 6


@dataclass
class Donate:
    username: str
    date: str
    price: int
    message: str
    external_id: str


def db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    init_emoji_db()
    with db() as connection:
        connection.execute("""CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY, language TEXT NOT NULL DEFAULT 'en',
            api_token TEXT, donation_link TEXT, destinations TEXT NOT NULL DEFAULT '{}',
            last_donation_id TEXT, registered INTEGER NOT NULL DEFAULT 0)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS notified_donations (
            telegram_id INTEGER NOT NULL,
            donation_key TEXT NOT NULL,
            PRIMARY KEY (telegram_id, donation_key))""")


def get_user(telegram_id: int):
    with db() as connection:
        return connection.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()


def save_user(telegram_id: int, **values):
    with db() as connection:
        if not get_user(telegram_id):
            connection.execute("INSERT INTO users (telegram_id) VALUES (?)", (telegram_id,))
        for key, value in values.items():
            if key == "destinations":
                value = json.dumps(value)
            connection.execute(f"UPDATE users SET {key} = ? WHERE telegram_id = ?", (value, telegram_id))


def esc(value: Any) -> str:
    return html.escape(str(value or "-"))


def html_value(value: Any, emoji_tag: str = "MESSAGE") -> str:
    return replace_standard_emojis(esc(value), emoji_tag)


def section_line(section: str, text: str) -> str:
    emoji = section_emoji(section)
    return f"{emoji} {text}".strip() if emoji else text


def normalize_donation(raw: dict[str, Any]) -> Donate:
    donator = raw.get("donator", {})
    donator_data = raw.get("donator_data", {})
    if not isinstance(donator, dict):
        donator = {"username": donator}
    if not isinstance(donator_data, dict):
        donator_data = {}

    username = (donator.get("daramet_username") or donator.get("donator_name")
                or donator.get("username") or raw.get("Username")
                or raw.get("username") or raw.get("UserName") or "-")
    date = (donator_data.get("timestamp") or raw.get("Date")
            or raw.get("date") or raw.get("CreatedAt") or "-")
    price = (donator_data.get("amount") if "amount" in donator_data else
             raw.get("Price", raw.get("price", raw.get("Amount", raw.get("amount", 0)))))
    message = (donator_data.get("message") or raw.get("Message")
               or raw.get("message") or raw.get("text") or "-")
    external_id = (donator_data.get("id") or raw.get("Id") or raw.get("id")
                   or raw.get("Code") or raw.get("trackingCode") or "")
    if isinstance(date, (int, float)):
        date = datetime.fromtimestamp(date).strftime("%Y-%m-%d %H:%M")
    try:
        price = int(float(price))
    except (TypeError, ValueError):
        price = 0
    return Donate(str(username or "-"), str(date or "-"), price, str(message), str(external_id or ""))


def donation_key(donation: Donate) -> str:
    if donation.external_id:
        return f"id:{donation.external_id}"
    value = "|".join((donation.username, donation.date, str(donation.price), donation.message))
    return "hash:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def has_notified_donation(telegram_id: int, key: str) -> bool:
    with db() as connection:
        return connection.execute(
            "SELECT 1 FROM notified_donations WHERE telegram_id = ? AND donation_key = ?",
            (telegram_id, key),
        ).fetchone() is not None


def mark_donation_notified(telegram_id: int, key: str):
    with db() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO notified_donations(telegram_id, donation_key) VALUES (?, ?)",
            (telegram_id, key),
        )


def donation_text(donation: Donate, title=None, language="en") -> str:
    labels = {
        "en": {"title": "New Donate", "username": "Username", "date": "Date", "price": "Price", "message": "Message", "currency": "Toman"},
        "fa": {"title": "دونیت جدید", "username": "نام کاربری", "date": "تاریخ", "price": "مبلغ", "message": "پیام", "currency": "تومن"},
    }.get(language, TEXT["en"])
    title = title or labels["title"]
    lines = []
    if title:
        lines.append(section_line("donate_title", f"<b>{esc(title)}</b>"))
    lines.extend((
        section_line("username", f"<b>{labels['username']}:</b> {esc(donation.username).lstrip('@')}"),
        section_line("date", f"<b>{labels['date']}:</b> {esc(donation.date)}"),
        section_line("price", f"<b>{labels['price']}:</b> {donation.price:,} {labels['currency']}"),
        section_line("message", f"<b>{labels['message']}:</b> {html_value(donation.message)}"),
    ))
    return "\n\n".join(lines)


TEXT = {
    "en": {"language": "Choose your Language:", "token": "Send your Daramet API token.",
            "link": "Send your donation link, for example: daramet.com/username",
            "dest": "Where should donation notifications be sent?", "initial_id": "First send the channel or group ID that the bot should use.", "ids": "Send the chat ID for {kind}.",
            "done": "Your settings are connected successfully.", "dashboard": "Hello {name}\n\nChannel: {channel}\nDonations: {count}\nTotal income: {total:,} Toman",
        "income": "Income status", "delete_account": "Delete account", "delete_confirm": "Are you sure you want to disconnect your account from the bot?", "yes": "Yes", "no": "No", "back": "Back", "donate": "Donate", "channel": "Channel", "group": "Group", "test_unregistered": "Your account is not registered.", "bad": "Invalid input. Please try again."},
    "fa": {"language": "زبان خود را انتخاب کنید", "token": "توکن API اختصاصی دارمتان را ارسال کنید.",
            "link": "لینک دونیت را ارسال کنید، مثال: daramet.com/username",
            "dest": "اطلاع‌رسانی دونیت در کجا انجام شود؟", "initial_id": "ابتدا آیدی چنل یا گروهی که ربات باید در آن اطلاع‌رسانی کند را ارسال کنید.", "ids": "آیدی {kind} را ارسال کنید.",
        "done": "اطلاعات شما با موفقیت ثبت و متصل شد.", "dashboard": "سلام {name}\n\nچنل شما: {channel}\nتعداد دونیت دریافتی: {count}\nمجموع کل درآمد: {total:,} تومن",
        "income": "وضعیت درآمد", "delete_account": "حذف حساب کاربری", "delete_confirm": "آیا مطمئن هستید که می‌خواهید حساب خود را از ربات قطع کنید؟", "yes": "بله", "no": "خیر", "back": "بازگشت", "donate": "دونیت", "channel": "چنل", "group": "گروه", "test_unregistered": "حساب شما ثبت نشده است.", "bad": "ورودی نامعتبر است. دوباره تلاش کنید."},
}


def t(language, key, **kwargs):
    return TEXT.get(language, TEXT["en"])[key].format(**kwargs)


def plain_t(language, key, **kwargs):
    return TEXT.get(language, TEXT["en"])[key].format(**kwargs)


BUTTON_EMOJI = {
    "donate": "DONATE",
    "channel": "CHANNEL",
    "group": "GROUP",
    "english": "ENGLISH",
    "persian": "PERSIAN",
}


def button_text(language, key, text):
    return text


def button_emoji_id(key: str) -> str:
    return premium_emoji_id(BUTTON_EMOJI[key])


def language_keyboard():
    return InlineKeyboardMarkup([[
        inline_button(button_text("fa", "persian", "فارسی"), "lang:fa", "primary", "PERSIAN"),
        inline_button(button_text("en", "english", "English"), "lang:en", "primary", "ENGLISH"),
    ]])


def main_keyboard(language):
    return InlineKeyboardMarkup([
        [inline_button(plain_t(language, "income"), "income", "success", "INCOME")],
        [inline_button(plain_t(language, "delete_account"), "delete_account", "danger", "DELETE_ACCOUNT")],
    ])


async def edit_flow_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None):
    query = update.callback_query
    if query and query.message:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        return
    message_id = context.user_data.get("start_message_id")
    chat_id = context.user_data.get("start_chat_id") or update.effective_chat.id
    if message_id:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
            )
            if update.message:
                try:
                    await update.message.delete()
                except BadRequest:
                    pass
            return
        except BadRequest as error:
            logging.warning("Could not edit flow message %s in chat %s: %s", message_id, chat_id, error)
    if update.message:
        await update.message.delete()


def inline_button(text: str, callback_data: str, style: str, emoji_tag: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text,
        callback_data=callback_data,
        api_kwargs={
            "style": style,
            "icon_custom_emoji_id": premium_emoji_id(emoji_tag),
        },
    )


def inline_link_button(text: str, url: str, style: str, emoji_tag: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text,
        url=url,
        api_kwargs={
            "style": style,
            "icon_custom_emoji_id": premium_emoji_id(emoji_tag),
        },
    )


def delete_confirmation_keyboard(language):
    return InlineKeyboardMarkup([[
        inline_button(plain_t(language, "yes"), "delete_account:yes", "success", "YES"),
        inline_button(plain_t(language, "no"), "delete_account:no", "danger", "NO"),
    ]])


async def donation_keyboard(user, language, bot):
    destinations = json.loads(user["destinations"] or "{}")
    buttons = []
    if user["donation_link"]:
        buttons.append(inline_link_button(
            button_text(language, "donate", plain_t(language, "donate")),
            f"https://daramet.com/{user['donation_link'].lstrip('/')}",
            "success",
            "DONATE",
        ))
    destination = destinations.get("channel") or destinations.get("group")
    if destination:
        kind = "channel" if destinations.get("channel") else "group"
        try:
            chat = await bot.get_chat(int(destination))
            if chat.username:
                destination_url = f"https://t.me/{chat.username}"
            else:
                chat_id = str(destination)
                chat_id = chat_id[4:] if chat_id.startswith("-100") else chat_id.lstrip("-")
                destination_url = f"https://t.me/c/{chat_id}"
            buttons.append(inline_link_button(
                button_text(language, kind, plain_t(language, kind)),
                destination_url,
                "primary",
                "CHANNEL",
            ))
        except Exception:
            logging.warning("Could not build destination link for %s", destination)
    return InlineKeyboardMarkup([buttons]) if buttons else None


def admin_ids() -> set[int]:
    return {int(value) for value in os.getenv("ADMIN_IDS", "").split(",") if value.strip().isdigit()}


def emoji_admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("افزودن / ویرایش ایموجی", callback_data="emoji:save")],
        [InlineKeyboardButton("حذف ایموجی", callback_data="emoji:delete")],
        [InlineKeyboardButton("لیست ایموجی‌ها", callback_data="emoji:list")],
    ])


async def emoji_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in admin_ids():
        return
    context.user_data["start_message_id"] = update.message.id
    context.user_data["start_chat_id"] = update.effective_chat.id
    await edit_flow_message(update, context, "پنل مدیریت ایموجی‌های پرمیوم", emoji_admin_keyboard())


async def emoji_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id not in admin_ids():
        await query.answer("دسترسی ندارید", show_alert=True)
        return
    await query.answer()
    action = query.data.split(":", 1)[1]
    if action == "list":
        items = get_ai_prm_emojies_list()
        await query.edit_message_text(f"لیست ایموجی‌ها:\n\n{items}", parse_mode=ParseMode.HTML, reply_markup=emoji_admin_keyboard())
        return
    context.user_data["emoji_action"] = action
    instruction = "TAG | EMOJI_ID | توضیح را ارسال کنید." if action == "save" else "تگ ایموجی را ارسال کنید."
    await query.edit_message_text(instruction, parse_mode=ParseMode.HTML)


async def emoji_admin_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in admin_ids():
        return
    action = context.user_data.pop("emoji_action", "")
    value = update.message.text.strip()
    try:
        if action == "save":
            parts = [part.strip() for part in value.split("|", 2)]
            if len(parts) != 3:
                raise ValueError
            save_emoji(*parts)
            result = "ایموجی با موفقیت ذخیره شد."
        elif action == "delete":
            result = "ایموجی حذف شد." if delete_emoji(value) else "این تگ پیدا نشد."
        else:
            return
    except ValueError:
        result = "فرمت نادرست است. نمونه: CONFIRM | 5296742257146241213 | توضیح"
    await edit_flow_message(update, context, result, emoji_admin_keyboard())


def destination_keyboard(language):
    labels = {"fa": ("چنل", "گروه", "پیوی"), "en": ("Channel", "Group", "Private")}[language]
    names = ("channel", "group", "private")

    def button(destination_set):
        title = " / ".join(labels[names.index(kind)] for kind in destination_set)
        return InlineKeyboardButton(title, callback_data="dest:" + ",".join(destination_set))

    return InlineKeyboardMarkup([
        [button(("channel",)), button(("group",)), button(("private",))],
        [button(("channel", "group")), button(("channel", "private")), button(("group", "private"))],
        [button(("channel", "group", "private"))],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    init_db()
    context.user_data["start_message_id"] = update.message.id
    context.user_data["start_chat_id"] = update.effective_chat.id
    user = get_user(update.effective_user.id)
    if user and user["registered"]:
        await update.message.reply_text(await dashboard_text(user, update.effective_user), parse_mode=ParseMode.HTML, reply_markup=main_keyboard(user["language"]))
        return ConversationHandler.END
    message = await update.message.reply_text(
        "Choose your Language:\nزبان خود را انتخاب کنید",
        parse_mode=ParseMode.HTML,
        reply_markup=language_keyboard(),
    )
    context.user_data["start_message_id"] = message.id
    return LANGUAGE


async def choose_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    language = query.data.split(":", 1)[1]
    save_user(query.from_user.id, language=language)
    await query.edit_message_text(t(language, "token"), parse_mode=ParseMode.HTML)
    return TOKEN


async def receive_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["api_token"] = update.message.text.strip()
    language = get_user(update.effective_user.id)["language"]
    await edit_flow_message(update, context, t(language, "link"))
    return LINK


async def receive_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text.strip()
    match = re.search(r"(?:daramet\.com/)?([A-Za-z0-9_]+)", link)
    if not match:
        await edit_flow_message(update, context, t(get_user(update.effective_user.id)["language"], "bad"))
        return LINK
    context.user_data["donation_link"] = match.group(1)
    language = get_user(update.effective_user.id)["language"]
    await edit_flow_message(update, context, t(language, "initial_id"))
    return INITIAL_CHAT_ID


async def receive_initial_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    chat_id = update.message.text.strip()
    try:
        chat = await context.bot.get_chat(chat_id)
        member = await context.bot.get_chat_member(chat.id, context.bot.id)
        if member.status not in ("administrator", "creator"):
            raise ValueError("bot is not an administrator")
        if chat.type not in ("channel", "group", "supergroup"):
            raise ValueError("expected channel or group")
    except Exception:
        await edit_flow_message(update, context, t(user["language"], "bad"))
        return INITIAL_CHAT_ID
    context.user_data["initial_chat"] = {"id": str(chat.id), "kind": "channel" if chat.type == "channel" else "group"}
    await edit_flow_message(update, context, t(user["language"], "dest"), destination_keyboard(user["language"]))
    return DESTINATIONS


async def choose_destinations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    destinations = query.data.split(":", 1)[1].split(",")
    context.user_data["destinations"] = {kind: None for kind in destinations}
    context.user_data["pending_destinations"] = [kind for kind in destinations if kind != "private"]
    initial_chat = context.user_data.get("initial_chat")
    if initial_chat and initial_chat["kind"] in context.user_data["destinations"]:
        context.user_data["destinations"][initial_chat["kind"]] = initial_chat["id"]
        context.user_data["pending_destinations"].remove(initial_chat["kind"])
    if "private" in destinations:
        context.user_data["destinations"]["private"] = str(query.from_user.id)
    language = get_user(query.from_user.id)["language"]
    if not context.user_data["pending_destinations"]:
        return await finish_registration(update, context)
    kind = context.user_data["pending_destinations"][0]
    await query.edit_message_text(t(language, "ids", kind=("channel" if kind == "channel" else "group")), parse_mode=ParseMode.HTML)
    return CHAT_IDS


async def receive_chat_ids(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    kind = context.user_data["pending_destinations"][0]
    chat_id = update.message.text.strip()
    try:
        chat = await context.bot.get_chat(chat_id)
        member = await context.bot.get_chat_member(chat.id, context.bot.id)
        if member.status not in ("administrator", "creator"):
            raise ValueError("bot is not an administrator")
        if kind == "channel" and chat.type != "channel":
            raise ValueError("expected channel")
        if kind == "group" and chat.type not in ("group", "supergroup"):
            raise ValueError("expected group")
        chat_id = str(chat.id)
    except Exception:
        await edit_flow_message(update, context, t(user["language"], "bad"))
        return CHAT_IDS
    context.user_data["pending_destinations"].pop(0)
    context.user_data["destinations"][kind] = chat_id
    if context.user_data["pending_destinations"]:
        next_kind = context.user_data["pending_destinations"][0]
        await edit_flow_message(update, context, t(user["language"], "ids", kind=("channel" if next_kind == "channel" else "group")))
        return CHAT_IDS
    await edit_flow_message(update, context, t(user["language"], "done"))
    return await finish_registration(update, context)


async def finish_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    save_user(user_id, api_token=context.user_data["api_token"], donation_link=context.user_data["donation_link"], destinations=context.user_data["destinations"], registered=1)
    user = get_user(user_id)
    text = await dashboard_text(user, update.effective_user)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=main_keyboard(user["language"]))
    else:
        await edit_flow_message(update, context, text, main_keyboard(user["language"]))
    return ConversationHandler.END


async def api_request(token, endpoint, method="GET", payload=None):
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.request(method, API_ROOT + endpoint, headers={"Authorization": token}, json=payload)
        response.raise_for_status()
        return response.json()


def as_list(data):
    if isinstance(data, list): return data
    if isinstance(data, dict):
        for key in ("Donates", "donates", "data", "Data", "items", "Items"):
            if isinstance(data.get(key), list): return data[key]
    return []


async def fetch_donations(token):
    return [normalize_donation(item) for item in as_list(await api_request(token, "/Donates/All", "POST", {"page": 1}))]


async def dashboard_text(user, telegram_user):
    donations = []
    try: donations = await fetch_donations(user["api_token"])
    except (httpx.HTTPError, KeyError, TypeError): pass
    channel = json.loads(user["destinations"]).get("channel", "-")
    name = telegram_user.username or telegram_user.first_name
    name = f"@{name.lstrip('@')}" if telegram_user.username else name
    dashboard = t(user["language"], "dashboard", name=esc(name), channel=esc(channel), count=len(donations), total=sum(item.price for item in donations))
    sections = ("greeting", "channel", "donation_count", "total_income")
    rendered_lines = []
    section_index = 0
    for line in dashboard.splitlines():
        if line.strip():
            rendered_lines.append(section_line(sections[section_index], line))
            section_index += 1
        else:
            rendered_lines.append(line)
    return "\n".join(rendered_lines)


async def income(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        user = get_user(query.from_user.id)
    else:
        user = get_user(update.effective_user.id)
    try: donations = await fetch_donations(user["api_token"])
    except (httpx.HTTPError, KeyError, TypeError): donations = []
    title = "حمایت" if user["language"] == "fa" else "Donate"
    blocks = [donation_text(item, f"{title} {index}", user["language"]) for index, item in enumerate(reversed(donations), 1)]
    text = "\n\n--------------------------------------\n\n".join(blocks) or "-"
    markup = InlineKeyboardMarkup([[
        inline_button(plain_t(user["language"], "back"), "back", "danger", "BACK")
    ]])
    if query:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    else:
        await edit_flow_message(update, context, text, main_keyboard(user["language"]))


async def back_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        user = get_user(query.from_user.id)
        await query.edit_message_text(await dashboard_text(user, query.from_user), parse_mode=ParseMode.HTML, reply_markup=main_keyboard(user["language"]))
    else:
        user = get_user(update.effective_user.id)
        await edit_flow_message(update, context, await dashboard_text(user, update.effective_user), main_keyboard(user["language"]))


async def delete_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        user = get_user(query.from_user.id)
        await query.edit_message_text(t(user["language"], "delete_confirm"), parse_mode=ParseMode.HTML, reply_markup=delete_confirmation_keyboard(user["language"]))
    else:
        user = get_user(update.effective_user.id)
        await edit_flow_message(update, context, t(user["language"], "delete_confirm"), delete_confirmation_keyboard(user["language"]))


async def delete_account_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        user_id = query.from_user.id
        user = get_user(user_id)
        is_no = query.data.endswith(":no")
    else:
        user_id = update.effective_user.id
        user = get_user(user_id)
        is_no = update.message.text in (TEXT["en"]["no"], TEXT["fa"]["no"])
    if is_no:
        dashboard = await dashboard_text(user, query.from_user if query else update.effective_user)
        if query:
            await query.edit_message_text(dashboard, parse_mode=ParseMode.HTML, reply_markup=main_keyboard(user["language"]))
        else:
            await edit_flow_message(update, context, dashboard, main_keyboard(user["language"]))
        return
    with db() as connection:
        connection.execute("DELETE FROM users WHERE telegram_id = ?", (user_id,))
        connection.execute("DELETE FROM notified_donations WHERE telegram_id = ?", (user_id,))
    text = "Choose your Language:\nزبان خود را انتخاب کنید"
    if query:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=language_keyboard())
    else:
        await edit_flow_message(update, context, text, language_keyboard())


def test_donation() -> Donate:
    return Donate("test_user", datetime.now().strftime("%Y-%m-%d %H:%M"), 1000, "Test donation", "test")


async def testdan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if not user or not user["registered"]:
        await edit_flow_message(update, context, t(user["language"] if user else "en", "test_unregistered"))
        return
    markup = await donation_keyboard(user, user["language"], context.bot)
    text = donation_text(test_donation(), language=user["language"])
    sent = False
    for chat_id in json.loads(user["destinations"] or "{}").values():
        if not chat_id:
            continue
        try:
            await context.bot.send_message(int(chat_id), text, parse_mode=ParseMode.HTML, reply_markup=markup)
            sent = True
        except BadRequest as error:
            if "Entity" not in str(error):
                logging.error("Could not send test donation to %s: %s", chat_id, error)
                continue
            logging.error("Could not send test donation to %s: %s", chat_id, error)
    if sent:
        await edit_flow_message(update, context, "Test donation sent." if user["language"] == "en" else "پیام تست دونیت ارسال شد.")
    else:
        await edit_flow_message(update, context, t(user["language"], "test_unregistered"))


async def poll_donations(context: ContextTypes.DEFAULT_TYPE):
    for row in (db().execute("SELECT * FROM users WHERE registered = 1").fetchall()):
        try: donations = await fetch_donations(row["api_token"])
        except (httpx.HTTPError, KeyError, TypeError): continue
        previous = row["last_donation_id"]
        fresh = []
        if not previous:
            for donation in donations:
                mark_donation_notified(row["telegram_id"], donation_key(donation))
            if donations:
                save_user(row["telegram_id"], last_donation_id=donation_key(donations[0]))
            continue
        if previous:
            found_previous = False
            for donation in reversed(donations):
                if donation.external_id == previous or donation_key(donation) == previous:
                    found_previous = True
                    break
                fresh.append(donation)
            if not found_previous:
                fresh = []
        if donations:
            save_user(row["telegram_id"], last_donation_id=donation_key(donations[0]))
        targets = json.loads(row["destinations"])
        for donation in fresh:
            key = donation_key(donation)
            if has_notified_donation(row["telegram_id"], key):
                continue
            mark_donation_notified(row["telegram_id"], key)
            markup = await donation_keyboard(row, row["language"], context.bot)
            for chat_id in targets.values():
                if not chat_id:
                    continue
                try:
                    await context.bot.send_message(int(chat_id), donation_text(donation, language=row["language"]), parse_mode=ParseMode.HTML, reply_markup=markup)
                except BadRequest as error:
                    if "Entity" in str(error):
                        logging.error("Could not send donation %s to %s: %s", donation.external_id, chat_id, error)
                    else:
                        logging.error("Could not send donation %s to %s: %s", donation.external_id, chat_id, error)


def build_application():
    init_db()
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    application = Application.builder().token(token).build()
    conversation = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={LANGUAGE: [CallbackQueryHandler(choose_language, pattern=r"^lang:")], TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_token)], LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_link)], INITIAL_CHAT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_initial_chat_id)], DESTINATIONS: [CallbackQueryHandler(choose_destinations, pattern=r"^dest:")], CHAT_IDS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_chat_ids)]},
        fallbacks=[CommandHandler("start", start)], allow_reentry=True)
    application.add_handler(conversation)
    application.add_handler(CommandHandler("emoji", emoji_admin))
    application.add_handler(CommandHandler("testdan", testdan))
    application.add_handler(CallbackQueryHandler(emoji_admin_action, pattern=r"^emoji:"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, emoji_admin_value))
    application.add_handler(CallbackQueryHandler(income, pattern="^income$"))
    application.add_handler(CallbackQueryHandler(back_dashboard, pattern="^back$"))
    application.add_handler(CallbackQueryHandler(delete_account, pattern="^delete_account$"))
    application.add_handler(CallbackQueryHandler(delete_account_action, pattern=r"^delete_account:(yes|no)$"))
    application.job_queue.run_repeating(poll_donations, interval=30, first=5)
    return application


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    build_application().run_polling()