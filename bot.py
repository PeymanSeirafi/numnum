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

# ---------------- LOAD ENV ----------------
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

# 👑 MULTI ADMINS
ADMINS = {639850653}

def is_admin(user_id: int):
    return user_id in ADMINS

# ---------------- DATA STORAGE ----------------
users = set()

events = {}
event_counter = 1

message_event_map = {}

submissions = {}
sub_counter = 1

logging.basicConfig(level=logging.INFO)


# ---------------- START ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users.add(update.effective_chat.id)
    await update.message.reply_text(
        "✅ شما ثبت شدید. از این پس رویدادها و اطلاعیه‌ها را دریافت می‌کنید."
    )


# ---------------- CREATE EVENT ----------------
async def create_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global event_counter

    if not is_admin(update.effective_user.id):
        return

    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("❗ استفاده: /create عنوان، سوال")
        return

    event_id = event_counter
    event_counter += 1

    events[event_id] = {"text": text, "active": True}

    sent = 0

    for user_id in users:
        try:
            msg = await context.bot.send_message(
                chat_id=user_id,
                text=f"🎯 رویداد {event_id}\n\n{text}\n\n📌 پاسخ خود را با عکس + توضیح ارسال کنید."
            )
            message_event_map[(user_id, msg.message_id)] = event_id
            sent += 1
        except:
            pass

    await update.message.reply_text(f"✅ رویداد {event_id} ارسال شد به {sent} کاربر.")


# ---------------- END EVENT ----------------
async def end_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text("❗ استفاده: /end event_id")
        return

    event_id = int(context.args[0])

    if event_id in events:
        events[event_id]["active"] = False
        await update.message.reply_text(f"⛔ رویداد {event_id} بسته شد.")
    else:
        await update.message.reply_text("❌ پیدا نشد.")


# ---------------- ANNOUNCEMENT ----------------
async def announce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("❗ استفاده: /announce متن پیام")
        return

    sent = 0

    for user_id in users:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"📢 اطلاعیه\n\n{text}"
            )
            sent += 1
        except:
            pass

    await update.message.reply_text(f"📢 ارسال شد به {sent} کاربر")


# ---------------- HANDLE SUBMISSIONS ----------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global sub_counter

    msg = update.message
    user = update.effective_user

    users.add(update.effective_chat.id)

    if not msg.reply_to_message:
        return

    key = (update.effective_chat.id, msg.reply_to_message.message_id)

    if key not in message_event_map:
        return

    event_id = message_event_map[key]

    if not events.get(event_id, {}).get("active", False):
        await msg.reply_text("⛔ این رویداد بسته شده است.")
        return

    if not msg.photo or not msg.caption:
        await msg.reply_text("❗ لطفاً عکس + توضیح ارسال کنید.")
        return

    sub_id = sub_counter
    sub_counter += 1

    submissions[sub_id] = {
        "user_id": user.id,
        "username": user.username,
        "event_id": event_id,
        "caption": msg.caption,
        "photo_file_id": msg.photo[-1].file_id,
        "status": "pending"
    }

    await msg.reply_text(f"✅ ارسال ثبت شد (ID: {sub_id})")

    # 👇 SEND PHOTO TO ALL ADMINS
    for admin_id in ADMINS:
        await context.bot.send_photo(
            chat_id=admin_id,
            photo=msg.photo[-1].file_id,
            caption=
                f"📩 ارسال جدید #{sub_id}\n"
                f"🎯 رویداد: {event_id}\n"
                f"👤 کاربر: @{user.username}\n"
                f"📝 توضیح: {msg.caption}\n\n"
                f"/verify {sub_id} accept\n"
                f"/verify {sub_id} reject"
        )


# ---------------- VERIFY ----------------
async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if len(context.args) < 2:
        await update.message.reply_text("❗ استفاده: /verify id accept|reject")
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
            sub["user_id"],
            f"🎉 ارسال شما برای رویداد {sub['event_id']} تأیید شد."
        )

        await update.message.reply_text("✅ تأیید شد.")

    elif decision == "reject":
        sub["status"] = "rejected"

        await context.bot.send_message(
            sub["user_id"],
            f"❌ ارسال شما برای رویداد {sub['event_id']} رد شد."
        )

        await update.message.reply_text("⛔ رد شد.")

    else:
        await update.message.reply_text("❗ فقط accept یا reject")


# ---------------- ADMIN DATABASE COMMANDS ----------------
async def list_submissions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    text = "📊 آخرین ارسال‌ها:\n\n"

    for sid, s in list(submissions.items())[-10:]:
        text += f"ID:{sid} | Event:{s['event_id']} | @{s['username']} | {s['status']}\n"

    await update.message.reply_text(text)


async def list_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    text = "🎯 رویدادها:\n\n"

    for eid, e in events.items():
        status = "فعال" if e["active"] else "بسته"
        text += f"{eid} | {status}\n{e['text']}\n\n"

    await update.message.reply_text(text)


async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    text = f"👥 تعداد کاربران: {len(users)}\n\n"
    text += "\n".join(list(map(str, list(users)[:30])))

    await update.message.reply_text(text)


# ---------------- RUN BOT ----------------
def main():
    if not TOKEN:
        raise ValueError("BOT_TOKEN not set!")

    app = Application.builder().token(TOKEN).build()

    # user commands
    app.add_handler(CommandHandler("start", start))

    # admin commands
    app.add_handler(CommandHandler("create", create_event))
    app.add_handler(CommandHandler("end", end_event))
    app.add_handler(CommandHandler("announce", announce))
    app.add_handler(CommandHandler("verify", verify))

    app.add_handler(CommandHandler("submissions", list_submissions))
    app.add_handler(CommandHandler("eventlist", list_events))
    app.add_handler(CommandHandler("users", list_users))

    # messages
    app.add_handler(MessageHandler(filters.ALL, handle_message))

    print("🤖 Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()