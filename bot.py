import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.error import Forbidden, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

DB_PATH = "bot.db"
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {
    int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()
}

# If you want to force captions to be non-empty, leave this as True.
REQUIRE_CAPTION = True


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_by INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                photo_file_id TEXT NOT NULL,
                caption TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                reviewed_at TEXT,
                UNIQUE(question_id, user_id),
                FOREIGN KEY(question_id) REFERENCES questions(id),
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            );
            """
        )


def save_user(update: Update) -> None:
    user = update.effective_user
    if not user:
        return

    with db() as conn:
        conn.execute(
            """
            INSERT INTO users (user_id, username, first_name, active, created_at)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name,
                active=1
            """,
            (user.id, user.username, user.first_name, now()),
        )


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def create_question(question_text: str, created_by: int) -> int:
    with db() as conn:
        conn.execute("UPDATE questions SET active = 0 WHERE active = 1")
        cur = conn.execute(
            """
            INSERT INTO questions (text, active, created_by, created_at)
            VALUES (?, 1, ?, ?)
            """,
            (question_text, created_by, now()),
        )
        return int(cur.lastrowid)


def get_active_question() -> Optional[sqlite3.Row]:
    with db() as conn:
        return conn.execute(
            "SELECT * FROM questions WHERE active = 1 ORDER BY id DESC LIMIT 1"
        ).fetchone()


def get_active_users():
    with db() as conn:
        return conn.execute("SELECT * FROM users WHERE active = 1").fetchall()


def save_submission(
    question_id: int,
    user_id: int,
    username: Optional[str],
    photo_file_id: str,
    caption: str,
) -> int:
    with db() as conn:
        existing = conn.execute(
            """
            SELECT id, status
            FROM answers
            WHERE question_id = ? AND user_id = ?
            """,
            (question_id, user_id),
        ).fetchone()

        if existing and existing["status"] == "accepted":
            return int(existing["id"])

        if existing:
            conn.execute(
                """
                UPDATE answers
                SET username = ?, photo_file_id = ?, caption = ?, status = 'pending'
                WHERE id = ?
                """,
                (username, photo_file_id, caption, int(existing["id"])),
            )
            return int(existing["id"])

        cur = conn.execute(
            """
            INSERT INTO answers (
                question_id, user_id, username, photo_file_id, caption,
                status, created_at, reviewed_at
            )
            VALUES (?, ?, ?, ?, ?, 'pending', ?, NULL)
            """,
            (question_id, user_id, username, photo_file_id, caption, now()),
        )
        return int(cur.lastrowid)


def set_answer_status(answer_id: int, status: str) -> bool:
    with db() as conn:
        cur = conn.execute(
            """
            UPDATE answers
            SET status = ?, reviewed_at = ?
            WHERE id = ?
            """,
            (status, now(), answer_id),
        )
        return cur.rowcount > 0


def get_answer(answer_id: int) -> Optional[sqlite3.Row]:
    with db() as conn:
        return conn.execute(
            """
            SELECT a.*, q.text AS question_text, q.id AS question_number
            FROM answers a
            JOIN questions q ON q.id = a.question_id
            WHERE a.id = ?
            """,
            (answer_id,),
        ).fetchone()


def list_pending_answers():
    with db() as conn:
        return conn.execute(
            """
            SELECT
                a.id AS answer_id,
                a.caption,
                a.photo_file_id,
                a.username,
                a.user_id,
                q.id AS question_number,
                q.text AS question_text
            FROM answers a
            JOIN questions q ON q.id = a.question_id
            WHERE a.status = 'pending'
            ORDER BY a.id ASC
            """
        ).fetchall()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    save_user(update)
    await update.message.reply_text(
        "You are registered.\n"
        "When there is an active question, send me a photo with a caption.\n"
        "Admin commands: /newquestion, /pending"
    )


async def newquestion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not is_admin(update.effective_user.id):
        await update.message.reply_text("You are not allowed to use this command.")
        return

    question_text = " ".join(context.args).strip()
    if not question_text:
        await update.message.reply_text("Usage: /newquestion your question here")
        return

    save_user(update)
    question_id = create_question(question_text, update.effective_user.id)
    users = get_active_users()

    sent = 0
    failed = 0

    for user in users:
        try:
            await context.bot.send_message(
                chat_id=user["user_id"],
                text=(
                    f"Question #{question_id}:\n{question_text}\n\n"
                    "Reply with a photo and a caption."
                ),
            )
            sent += 1
        except Forbidden:
            failed += 1
            with db() as conn:
                conn.execute("UPDATE users SET active = 0 WHERE user_id = ?", (user["user_id"],))
        except TelegramError:
            failed += 1

    await update.message.reply_text(
        f"Question #{question_id} sent to {sent} users. Failed for {failed} users."
    )


async def handle_photo_with_caption(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    save_user(update)
    question = get_active_question()
    if not question:
        await update.message.reply_text("There is no active question right now.")
        return

    if not update.message.photo:
        await update.message.reply_text("Please send a photo.")
        return

    caption = (update.message.caption or "").strip()
    if REQUIRE_CAPTION and not caption:
        await update.message.reply_text("Please resend it with a caption.")
        return

    photo_file_id = update.message.photo[-1].file_id
    user = update.effective_user
    username = f"@{user.username}" if user.username else None

    answer_id = save_submission(
        question_id=int(question["id"]),
        user_id=user.id,
        username=username,
        photo_file_id=photo_file_id,
        caption=caption,
    )

    keyboard = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Accept", callback_data=f"accept:{answer_id}"),
            InlineKeyboardButton("Reject", callback_data=f"reject:{answer_id}"),
        ]]
    )

    review_text = (
        f"Review #{answer_id}\n"
        f"Question #{question['id']}: {question['text']}\n"
        f"User: {username or user.first_name or user.id}\n"
        f"Caption: {caption or '(no caption)'}"
    )

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_photo(chat_id=admin_id, photo=photo_file_id)
            await context.bot.send_message(
                chat_id=admin_id,
                text=review_text,
                reply_markup=keyboard,
            )
        except TelegramError:
            pass

    await update.message.reply_text("Received. Waiting for admin approval.")


async def handle_photo_without_caption(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    question = get_active_question()
    if not question:
        await update.message.reply_text("There is no active question right now.")
        return

    await update.message.reply_text("Please send the photo again with a caption.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    question = get_active_question()
    if not question:
        return

    await update.message.reply_text("Please reply with a photo and a caption, not text only.")


async def pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    rows = list_pending_answers()
    if not rows:
        await update.message.reply_text("No pending submissions.")
        return

    lines = []
    for r in rows[:30]:
        who = r["username"] or str(r["user_id"])
        lines.append(
            f"ID {r['answer_id']} | Q{r['question_number']} | {who} | {r['caption']}"
        )

    await update.message.reply_text("\n".join(lines))


async def review_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.from_user:
        return

    if not is_admin(query.from_user.id):
        await query.answer("Not allowed.", show_alert=True)
        return

    try:
        action, answer_id_str = query.data.split(":", 1)
        answer_id = int(answer_id_str)
    except Exception:
        await query.answer("Bad callback data.", show_alert=True)
        return

    row = get_answer(answer_id)
    if not row:
        await query.answer("Answer not found.", show_alert=True)
        return

    if action == "accept":
        ok = set_answer_status(answer_id, "accepted")
        if ok:
            await query.answer("Accepted.")
            await query.edit_message_reply_markup(reply_markup=None)

            try:
                await context.bot.send_message(
                    chat_id=int(row["user_id"]),
                    text="Your photo was accepted.",
                )
            except TelegramError:
                pass
        else:
            await query.answer("Could not accept.", show_alert=True)

    elif action == "reject":
        ok = set_answer_status(answer_id, "rejected")
        if ok:
            await query.answer("Rejected.")
            await query.edit_message_reply_markup(reply_markup=None)

            try:
                await context.bot.send_message(
                    chat_id=int(row["user_id"]),
                    text="Your photo was rejected. Please send another one.",
                )
            except TelegramError:
                pass
        else:
            await query.answer("Could not reject.", show_alert=True)


def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")
    if not ADMIN_IDS:
        raise RuntimeError("ADMIN_IDS is missing")

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newquestion", newquestion))
    app.add_handler(CommandHandler("pending", pending))
    app.add_handler(CallbackQueryHandler(review_action, pattern=r"^(accept|reject):"))
    app.add_handler(MessageHandler(filters.PHOTO & filters.CAPTION, handle_photo_with_caption))
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.CAPTION, handle_photo_without_caption))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling()


if __name__ == "__main__":
    main()