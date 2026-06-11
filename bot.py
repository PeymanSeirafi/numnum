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

ADMINS = {123456789, 987654321}

def is_admin(user_id: int):
    return user_id in ADMINS


# ---------------- DATA ----------------
users = set()

events = {}
event_counter = 1

submissions = {}
sub_counter = 1

active_submit_session = {}

logging.basicConfig(level=logging.INFO)


# ---------------- UTIL ----------------
def username(user):
    return f"@{user.username}" if user.username else user.first_name


# ---------------- START ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users.add(update.effective_chat.id)
    await update.message.reply_text("✅ شما ثبت شدید.")


# ---------------- CREATE EVENT (BROADCAST FIXED) ----------------
async def create_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global event_counter

    if not is_admin(update.effective_user.id):
        return

    raw = " ".join(context.args)

    if "|" not in raw:
        await update.message.reply_text("❗ /create عنوان | متن اصلی")
        return

    title, main_text = map(str.strip, raw.split("|", 1))

    eid = event_counter
    event_counter += 1

    events[eid] = {
        "title": title,
        "text": main_text,
        "active": True
    }

    sent = 0

    # 🔥 FIX: broadcast like before
    for user_id in users:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"🎯 رویداد {eid}\n"
                    f"📌 {title}\n\n"
                    f"{main_text}\n\n"
                    f"برای پاسخ: /submit {eid}"
                )
            )
            sent += 1
        except:
            pass

    await update.message.reply_text(f"✅ رویداد {eid} ارسال شد به {sent} کاربر")


# ---------------- SHOW EVENT ----------------
async def show_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ /show id")
        return

    eid = int(context.args[0])

    if eid not in events:
        await update.message.reply_text("❌ پیدا نشد")
        return

    e = events[eid]

    await update.message.reply_text(
        f"🎯 رویداد {eid}\n"
        f"📌 {e['title']}\n\n"
        f"{e['text']}"
    )


# ---------------- EVENTS LIST ----------------
async def events_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    active = [(eid, e) for eid, e in events.items() if e["active"]]

    if not active:
        await update.message.reply_text("⛔ هیچ رویدادی فعال نیست")
        return

    text = "🎯 رویدادهای فعال:\n\n"

    for eid, e in active:
        text += f"{eid} | {e['title']}\n"

    await update.message.reply_text(text)


# ---------------- SUBMIT START ----------------
async def submit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_chat.id

    if not context.args:
        await update.message.reply_text("❗ /submit id")
        return

    eid = int(context.args[0])

    if eid not in events or not events[eid]["active"]:
        await update.message.reply_text("❌ رویداد نامعتبر")
        active_submit_session.pop(uid, None)
        return

    active_submit_session[uid] = eid

    e = events[eid]

    await update.message.reply_text(
        f"🎯 وارد رویداد شدید:\n\n"
        f"{e['title']}\n\n"
        f"{e['text']}\n\n"
        f"📌 حالا عکس + توضیح ارسال کنید"
    )


# ---------------- HANDLE SUBMISSION ----------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global sub_counter

    msg = update.message
    user = update.effective_user
    uid = update.effective_chat.id

    users.add(uid)

    if uid not in active_submit_session:
        return

    eid = active_submit_session[uid]

    if eid not in events or not events[eid]["active"]:
        await msg.reply_text("⛔ رویداد بسته شده")
        active_submit_session.pop(uid, None)
        return

    if not msg.photo or not msg.caption:
        await msg.reply_text("❗ عکس + توضیح لازم است")
        return

    sid = sub_counter
    sub_counter += 1

    # ✅ FIX: store real user_id
    submissions[sid] = {
        "user_id": uid,
        "username": username(user),
        "event_id": eid,
        "caption": msg.caption,
        "photo": msg.photo[-1].file_id,
        "status": "pending"
    }

    active_submit_session.pop(uid, None)

    await msg.reply_text("✅ ارسال ثبت شد")

    for admin in ADMINS:
        await context.bot.send_photo(
            chat_id=admin,
            photo=msg.photo[-1].file_id,
            caption=(
                f"📩 ارسال #{sid}\n"
                f"👤 {username(user)}\n"
                f"🎯 {eid}\n"
                f"📝 {msg.caption}\n\n"
                f"/verify {sid} accept\n"
                f"/verify {sid} reject"
            )
        )


# ---------------- VERIFY (FIXED NOTIFICATION) ----------------
async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if len(context.args) < 2:
        await update.message.reply_text("❗ /verify id accept|reject")
        return

    sid = int(context.args[0])
    decision = context.args[1].lower()

    if sid not in submissions:
        await update.message.reply_text("❌ پیدا نشد")
        return

    sub = submissions[sid]

    if decision == "accept":
        sub["status"] = "accepted"

        # ✅ FIXED: now user gets notification correctly
        await context.bot.send_message(
            chat_id=sub["user_id"],
            text=f"🎉 ارسال شما برای رویداد {sub['event_id']} تایید شد!"
        )

        await update.message.reply_text("✅ تایید شد")

    elif decision == "reject":
        sub["status"] = "rejected"

        await context.bot.send_message(
            chat_id=sub["user_id"],
            text=f"❌ ارسال شما برای رویداد {sub['event_id']} رد شد"
        )

        await update.message.reply_text("⛔ رد شد")


# ---------------- USERS LIST (RESTORED) ----------------
async def users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    text = f"👥 کاربران: {len(users)}\n\n"

    for u in list(users)[:30]:
        text += f"{u}\n"

    await update.message.reply_text(text)


# ---------------- RUN ----------------
def main():
    if not TOKEN:
        raise ValueError("BOT_TOKEN missing")

    app = Application.builder().token(TOKEN).build()

    # user
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("events", events_list))
    app.add_handler(CommandHandler("submit", submit_start))
    app.add_handler(CommandHandler("show", show_event))

    # admin
    app.add_handler(CommandHandler("create", create_event))
    app.add_handler(CommandHandler("verify", verify))
    app.add_handler(CommandHandler("users", users_list))

    # messages
    app.add_handler(MessageHandler(filters.ALL, handle_message))

    print("🤖 running...")
    app.run_polling()


if __name__ == "__main__":
    main()