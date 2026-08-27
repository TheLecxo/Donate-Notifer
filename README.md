# Daramet Notifier

ربات پس از انتخاب زبان، توکن API دارمت، نام کاربری لینک دونیت و مقصدهای اطلاع‌رسانی را ثبت می‌کند. برای چنل یا گروه، ربات با `getChat` و `getChatMember` بررسی می‌کند که خودش ادمین باشد. مقصد پیوی به‌صورت خودکار همان صاحب ربات است.

## اجرا

1. ربات را در BotFather بسازید و آن را در هر چنل یا گروه مقصد ادمین کنید.
2. وابستگی‌ها را نصب کنید:

```powershell
python -m pip install -r requirements.txt
```

3. متغیر توکن را تنظیم و اجرا کنید:

```powershell
$env:TELEGRAM_BOT_TOKEN = "توکن-ربات"
python bot.py
```

`aiogram` برای ساخت Reply Keyboard رنگی استفاده می‌شود. برای آزمایش آن، `/testcolor` را بفرستید. شناسه‌های API برای کلاینت کاربری Telegram هستند و برای Bot API الزامی نیستند؛ در صورت نیاز آن‌ها را در `.env` قرار دهید:

```env
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=your-api-hash
```

رنگ‌های `ButtonStyle` فقط روی Reply Keyboard کار می‌کنند. دکمه‌های لینک‌دار اعلان دونیت از نوع Inline Keyboard هستند و Telegram برای آن‌ها رنگ سفارشی ارائه نمی‌کند.

ربات هر ۳۰ ثانیه endpoint `POST https://daramet.com/api/v2/Donates/All` را با هدر `Authorization` بررسی می‌کند. داده‌های `Username`, `Date`, `Price`, `Message`, `Id` و نام‌های قدیمی `username`, `amount`, `text` پشتیبانی می‌شوند.

## اتصال در دارمت

در پنل دارمت از بخش «وب سرویس توسعه دهندگان» توکن API را بسازید. لینک دونیت باید مانند `https://daramet.com/username` باشد. در مرحله ثبت‌نام، شناسه عددی چنل یا گروه را ارسال کنید؛ ربات همان‌جا دسترسی ادمین خود را اعتبارسنجی می‌کند. سپس یک دونیت آزمایشی بزنید تا پیام `New Donate` در مقصدهای انتخاب‌شده ارسال شود.

`DATABASE_PATH` اختیاری است و مسیر فایل SQLite را تعیین می‌کند.

برای فعال‌کردن پنل مدیریت ایموجی، شناسه عددی ادمین را در `.env` قرار دهید:

```env
ADMIN_IDS=123456789,987654321
```

سپس در ربات `/emoji` را بفرستید. افزودن یا ویرایش با قالب `TAG | EMOJI_ID | توضیح` و حذف با ارسال `TAG` انجام می‌شود. برای اضافه‌کردن لیست ایموجی‌ها به هر پرامپت، از `build_emoji_prompt(text)` استفاده کنید؛ پاسخ تولیدشده را پیش از ارسال با `place_ai_prm_emojies(text)` رندر کنید و حتماً `parse_mode=ParseMode.HTML` بگذارید.

برای ایموجی مستقل هر بخش، این تگ‌ها را جداگانه ثبت کنید: `GREETING`, `CHANNEL`, `DONATION_COUNT`, `TOTAL_INCOME`, `DONATE_TITLE`, `USERNAME`, `DATE`, `PRICE`, `MESSAGE`. هر تگ می‌تواند `emoji_id` متفاوت داشته باشد.