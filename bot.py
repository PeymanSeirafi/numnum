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

ADMIN_ID = 639850653

# ---------------- DATA ----------------
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
        "سلام 👋\n"
        "به HOI Bet خوش اومدی\n"
        "اینجا روی چیز های مختلف شرط بندی میکنیم\n"
        "الان که بات رو start کردی، هر event جدیدی باشه که روش شرط بندی کنیم، از همینجا برات ارسال میشه"
    )


# ---------------- CREATE EVENT ----------------
async def create_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global event_counter

    if update.effective_user.id != ADMIN_ID:
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
                text=f"🎯 رویداد {event_id}\n\n{text}\n\n📌 لطفاً پاسخ را با عکس و توضیح ارسال کنید."
            )
            message_event_map[(user_id, msg.message_id)] = event_id
            sent += 1
        except:
            pass

    await update.message.reply_text(f"✅ رویداد ساخته شد (ID: {event_id}) برای {sent} کاربر ارسال شد.")


# ---------------- END EVENT ----------------
async def end_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:
        await update.message.reply_text("❗ استفاده: /end event_id")
        return

    event_id = int(context.args[0])

    if event_id in events:
        events[event_id]["active"] = False
        await update.message.reply_text(f"⛔ رویداد {event_id} بسته شد.")
    else:
        await update.message.reply_text("❌ رویداد پیدا نشد.")


# ---------------- ANNOUNCEMENT ----------------
async def announce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
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
                text=f"📢 اطلاعیه جدید\n\n{text}"
            )
            sent += 1
        except:
            pass

    await update.message.reply_text(f"✅ اطلاعیه برای {sent} کاربر ارسال شد.")


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

    await context.bot.send_message(
        ADMIN_ID,
        f"📩 ارسال جدید #{sub_id}\n"
        f"🎯 رویداد: {event_id}\n"
        f"👤 کاربر: @{user.username}\n"
        f"📝 توضیح: {msg.caption}\n\n"
        f"برای بررسی: /verify {sub_id} accept|reject"
    )


# ---------------- VERIFY ----------------
async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if len(context.args) < 2:
        await update.message.reply_text("❗ استفاده: /verify id accept|reject")
        return

    sub_id = int(context.args[0])
    decision = context.args[1]

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


# ---------------- RUN BOT ----------------
def main():
    if not TOKEN:
        raise ValueError("BOT_TOKEN is not set in environment variables!")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("create", create_event))
    app.add_handler(CommandHandler("end", end_event))
    app.add_handler(CommandHandler("announce", announce))
    app.add_handler(CommandHandler("verify", verify))

    app.add_handler(MessageHandler(filters.ALL, handle_message))

    print("🤖 Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()