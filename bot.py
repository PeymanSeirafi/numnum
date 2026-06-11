import os
import logging
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ---------------- ENV ----------------
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

ADMINS = {639850653}

def is_admin(user_id: int):
    return user_id in ADMINS


# ---------------- DATA ----------------
users = set()

events = {}
event_counter = 1

submissions = {}
sub_counter = 1

# user_id -> event_id (active submission session)
active_submit_session = {}

logging.basicConfig(level=logging.INFO)


# ---------------- UTIL ----------------
def get_username(user):
    return f"@{user.username}" if user.username else user.first_name


# ---------------- START ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users.add(update.effective_chat.id)
    await update.message.reply_text(
        "✅ شما ثبت شدید. از دستور /events برای دیدن رویدادها استفاده کنید."
    )


# ---------------- CREATE EVENT ----------------
async def create_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global event_counter

    if not is_admin(update.effective_user.id):
        return

    raw = " ".join(context.args)

    if "|" not in raw:
        await update.message.reply_text("❗ استفاده: /create عنوان | متن اصلی")
        return

    title, main_text = map(str.strip, raw.split("|", 1))

    event_id = event_counter
    event_counter += 1

    events[event_id] = {
        "title": title,
        "text": main_text,
        "active": True
    }

    await update.message.reply_text(
        f"✅ رویداد ساخته شد\n\nID: {event_id}\nTitle: {title}"
    )


# ---------------- EVENTS LIST ----------------
async def events_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    active_events = [
        (eid, e) for eid, e in events.items() if e["active"]
    ]

    if not active_events:
        await update.message.reply_text("⛔ هیچ رویداد فعالی وجود ندارد.")
        return

    text = "🎯 رویدادهای فعال:\n\n"

    for eid, e in active_events:
        text += f"ID: {eid} | {e['title']}\n"

    await update.message.reply_text(text)


# ---------------- SUBMIT START ----------------
async def submit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id

    if not context.args:
        await update.message.reply_text("❗ استفاده: /submit id")
        return

    event_id = int(context.args[0])

    if event_id not in events or not events[event_id]["active"]:
        await update.message.reply_text("❌ این رویداد وجود ندارد یا بسته شده است.")
        active_submit_session.pop(user_id, None)
        return

    active_submit_session[user_id] = event_id

    e = events[event_id]

    await update.message.reply_text(
        f"🎯 شما وارد رویداد شدید:\n\n"
        f"Title: {e['title']}\n\n"
        f"{e['text']}\n\n"
        f"📌 حالا پیام بعدی شما (عکس + توضیح) ثبت می‌شود."
    )


# ---------------- HANDLE SUBMISSION MESSAGE ----------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global sub_counter

    msg = update.message
    user = update.effective_user
    user_id = update.effective_chat.id

    users.add(user_id)

    # must be in submit session
    if user_id not in active_submit_session:
        return

    event_id = active_submit_session[user_id]

    if event_id not in events or not events[event_id]["active"]:
        await msg.reply_text("⛔ رویداد بسته شده است.")
        active_submit_session.pop(user_id, None)
        return

    if not msg.photo or not msg.caption:
        await msg.reply_text("❗ لطفاً عکس + توضیح ارسال کنید.")
        return

    sub_id = sub_counter
    sub_counter += 1

    submissions[sub_id] = {
        "user": get_username(user),
        "event_id": event_id,
        "caption": msg.caption,
        "photo": msg.photo[-1].file_id,
        "status": "pending"
    }

    active_submit_session.pop(user_id, None)

    await msg.reply_text("✅ ارسال شما ثبت شد.")

    # notify admins
    for admin_id in ADMINS:
        await context.bot.send_photo(
            chat_id=admin_id,
            photo=msg.photo[-1].file_id,
            caption=(
                f"📩 ارسال جدید #{sub_id}\n"
                f"👤 کاربر: {get_username(user)}\n"
                f"🎯 رویداد: {event_id}\n"
                f"📝 کپشن: {msg.caption}\n\n"
                f"/verify {sub_id} accept\n"
                f"/verify {sub_id} reject"
            )
        )


# ---------------- VERIFY ----------------
async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if len(context.args) < 2:
        await update.message.reply_text("❗ /verify id accept|reject")
        return

    sub_id = int(context.args[0])
    decision = context.args[1].lower()

    if sub_id not in submissions:
        await update.message.reply_text("❌ پیدا نشد.")
        return

    sub = submissions[sub_id]

    if decision == "accept":
        sub["status"] = "accepted"

        await context.bot.send_message(
            sub["user"],
            f"🎉 ارسال شما برای رویداد {sub['event_id']} تأیید شد."
        )

        await update.message.reply_text("✅ تأیید شد.")

    elif decision == "reject":
        sub["status"] = "rejected"

        await context.bot.send_message(
            sub["user"],
            f"❌ ارسال شما برای رویداد {sub['event_id']} رد شد."
        )

        await update.message.reply_text("⛔ رد شد.")


# ---------------- SUBMISSIONS LIST (ONLY ACCEPTED) ----------------
async def list_submissions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    accepted = [
        (sid, s) for sid, s in submissions.items()
        if s["status"] == "accepted"
    ]

    if not accepted:
        await update.message.reply_text("هیچ ارسال تایید شده‌ای وجود ندارد.")
        return

    text = "✅ ارسال‌های تایید شده:\n\n"

    for sid, s in accepted:
        text += (
            f"ID: {sid}\n"
            f"👤 {s['user']}\n"
            f"🎯 Event: {s['event_id']}\n"
            f"📝 {s['caption']}\n\n"
        )

    await update.message.reply_text(text)


# ---------------- RUN BOT ----------------
def main():
    if not TOKEN:
        raise ValueError("BOT_TOKEN not set")

    app = Application.builder().token(TOKEN).build()

    # user
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("events", events_list))
    app.add_handler(CommandHandler("submit", submit_start))

    # admin
    app.add_handler(CommandHandler("create", create_event))
    app.add_handler(CommandHandler("verify", verify))
    app.add_handler(CommandHandler("submissions", list_submissions))

    # messages
    app.add_handler(MessageHandler(filters.ALL, handle_message))

    print("🤖 Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()