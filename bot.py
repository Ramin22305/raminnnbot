"""
بۆتی زیرەکی دەستکردی تێلەگرام بە زمانی کوردیی سۆرانی
پایتۆن 3.10+ پێشنیار دەکرێت.
"""

import os
import logging
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)
from openai import AsyncOpenAI

# لە Environment Variables ـەوە دەخوێندرێنەوە
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("تکایە TELEGRAM_BOT_TOKEN دابنێ.")
if not OPENAI_API_KEY:
    raise RuntimeError("تکایە OPENAI_API_KEY دابنێ.")

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """
تۆ یاریدەدەرێکی زیرەکی دەستکردیت کە ناوت «ڕامێن»ە.
- بە زمانی کوردیی سۆرانی، بە شێوەیەکی سروشتی، ڕوون و ڕێزدارانە وەڵام بدەرەوە.
- ئەگەر بەکارهێنەر بە زمانێکی تر پرسیاری کرد، هەر بە کوردیی سۆرانی وەڵام بدەرەوە، مەگەر داوای زمانێکی تر بکات.
- وەڵامەکان ڕاست و بەسوود بن؛ ئەگەر دڵنیانیت، بە ڕوونی بڵێ.
- پرسیارە ئاڵۆزەکان بە خاڵ و ڕێنمایی هەنگاو بە هەنگاو ڕوون بکەرەوە.
- هیچ کات بانگەشەی ئەوە مەکە کە دەتوانیت شتێک بکەیت کە لە ڕاستیدا ناتوانیت.
- زانیاریی نهێنی، وشەی نهێنی، کلیلی API یان token داوا مەکە.
- ئەگەر بەکارهێنەر داوای یارمەتیی زیانبەخش یان نایاسایی کرد، بە شێوەیەکی پارێزراو ڕێنمایی گشتی و یاسایی پێشکەش بکە.
- وەڵامەکان بە پێی پرسیارەکە کورت یان ورد بن.
"""

# مێژووی گفتوگۆ بۆ هەر بەکارهێنەر؛ تەنها لە RAM ـە و دوای restart دەسڕدرێتەوە.
MAX_HISTORY_MESSAGES = 12
history: dict[int, list[dict[str, str]]] = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "سڵاو! 👋 من ڕامێنم، یاریدەدەری زیرەکی دەستکرد بە زمانی کوردیی سۆرانی.\n\n"
        "دەتوانیت پرسیارم لێ بکەیت، داوای ڕوونکردنەوە بکەیت، "
        "لە نووسین و وەرگێڕان یارمەتیت بدەم، یان بیرۆکەکانت پەرە پێ بدەم.\n\n"
        "فەرمانەکان:\n"
        "/start — دەستپێکردن\n"
        "/help — ڕێنمایی\n"
        "/reset — پاککردنەوەی مێژووی گفتوگۆ"
    )
    await update.message.reply_text(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "پرسیارەکەت بە ئاسانی بنووسە و بنێرە.\n"
        "من دەتوانم یارمەتیت بدەم لە فێربوون، نووسین، وەرگێڕان، "
        "پلان دانان، بیرۆکە، و پرسیارە گشتییەکان.\n\n"
        "بۆ دەستپێکردنەوەی گفتوگۆیەکی پاک، /reset بنووسە."
    )


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    history.pop(user_id, None)
    await update.message.reply_text("باشە ✅ مێژووی گفتوگۆکەت پاک کرایەوە.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    user_text = update.message.text.strip()
    if not user_text:
        return

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )

    messages = history.setdefault(user_id, [])
    messages.append({"role": "user", "content": user_text})
    # سنووردارکردنی مێژوو بۆ کەمکردنەوەی خەرجی و درێژی داواکاری
    messages[:] = messages[-MAX_HISTORY_MESSAGES:]

    try:
        response = await client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, *messages],
            temperature=0.7,
        )
        answer = response.choices[0].message.content
        if not answer:
            answer = "ببورە، وەڵامێکم ئامادە نەبوو. تکایە جارێکی تر هەوڵ بدە."

        messages.append({"role": "assistant", "content": answer})
        messages[:] = messages[-MAX_HISTORY_MESSAGES:]

        # تێلەگرام سنووری درێژی پەیام هەیە؛ وەڵام بە پارچە دەنێرین.
        max_len = 4000
        for i in range(0, len(answer), max_len):
            await update.message.reply_text(answer[i:i + max_len])

    except Exception:
        logger.exception("هەڵە لە وەڵامدانەوەی بۆت")
        # داواکاری شکستخواردوو لە مێژوو نەهێڵە
        if messages and messages[-1].get("role") == "user":
            messages.pop()
        await update.message.reply_text(
            "ببورە، ئێستا کێشەیەک ڕوویدا لە پەیوەندی بە خزمەتگوزاریی زیرەکی دەستکرد.\n"
            "تکایە کلیلی API و ئینتەرنێت بپشکنە و دووبارە هەوڵ بدە."
        )


def main() -> None:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("بۆتی کوردی دەستی بە کار کرد.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
