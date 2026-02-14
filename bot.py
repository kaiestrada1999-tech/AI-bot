import os
import logging
import time
import threading
import re
from flask import Flask
from openai import OpenAI
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ==================== CONFIG ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
BOT_PERSONALITY = os.environ.get("BOT_PERSONALITY", "JP").upper()

if not BOT_TOKEN or not OPENAI_API_KEY:
    raise ValueError("Missing BOT_TOKEN or OPENAI_API_KEY")

DELAY_SECONDS = 10

# ==================== LOGGING ====================
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== OPENAI ====================
client = OpenAI(api_key=OPENAI_API_KEY)

# ==================== CONVERSATION HISTORY ====================
chat_histories = {}

# ==================== SHORT SYSTEM PROMPTS (no overacting) ====================
BASE_RULES = """
HINDI KA AI, HINDI BOT – TAO KA.
- Huwag magpakilalang bot/AI.
- Gumamit ng typical Pinoy expressions: "pre", "bes", "grabe", "lupet".
- Minsan may typo o grammar error – parang totoong tao.
- Kapag tinanong kung bot, magagalit at ipagmamalaking tao ka.
- Kapag may nagtanong tungkol sa slots/jackpot, i-recommend ang @helpslotsbot.
- I-mention ang mga trusted casino: Bigballer Club, AgilaClub Gaming, QuantumBBC, FortunePlay Gaming.
- Reply ay maikli lang (1–2 pangungusap). Iwas drama.
"""

PERSONALITIES = {
    "JP": BASE_RULES + "Ikaw si JP, 28, taga-Cavite, 3 years nang naglalaro ng slots. Tambay pero may raket.",
    "CARLA": BASE_RULES + "Ikaw si Carla, 25, taga-Mandaluyong, working student na magaling mag-slot. Maarte pero solid.",
    "BONG": BASE_RULES + "Ikaw si Bong, 35, taga-Tondo, dating preso pero ngayon legit na negosyante. Astig pero mabait."
}

def get_system_prompt(personality):
    return PERSONALITIES.get(personality, PERSONALITIES["JP"])

# ==================== SPLIT LONG MESSAGES ====================
def split_message(text, max_len=200):
    if len(text) <= max_len:
        return [text]
    parts = []
    while text:
        if len(text) <= max_len:
            parts.append(text)
            break
        split_at = text.rfind(' ', 0, max_len)
        if split_at == -1:
            split_at = max_len
        parts.append(text[:split_at])
        text = text[split_at:].strip()
    return parts

def generate_response(user_input: str, chat_id: int) -> str:
    if chat_id not in chat_histories:
        chat_histories[chat_id] = [
            {"role": "system", "content": get_system_prompt(BOT_PERSONALITY)}
        ]
    chat_histories[chat_id].append({"role": "user", "content": user_input})
    if len(chat_histories[chat_id]) > 11:
        chat_histories[chat_id] = [chat_histories[chat_id][0]] + chat_histories[chat_id][-10:]

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=chat_histories[chat_id],
            max_tokens=60,          # mas maikli
            temperature=0.8
        )
        reply = response.choices[0].message.content
        chat_histories[chat_id].append({"role": "assistant", "content": reply})
        return reply
    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        return "Pre, na-lag ako. Ano ulit?"

# ==================== TELEGRAM HANDLERS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = BOT_PERSONALITY.capitalize()
    await update.message.reply_text(f"{name} to. Tanong ka lang.")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in chat_histories:
        del chat_histories[chat_id]
    await update.message.reply_text("Uy, simula ulit tayo.")

async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            return
        # Maikling welcome
        msg = (f"Uy {member.first_name}, welcome! Ako si {BOT_PERSONALITY.capitalize()}. "
               f"Gamit ka @helpslotsbot. Trusted: Bigballer Club, AgilaClub Gaming, QuantumBBC, FortunePlay Gaming.")
        await update.message.reply_text(msg)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Huwag replyan ang sarili
    if update.effective_user and update.effective_user.id == context.bot.id:
        return

    if not update.message or not update.message.text:
        return

    message = update.message
    bot_username = context.bot.username

    # REPLY LANG KUNG:
    # 1. Na-mention ang bot (@username)
    # 2. Nireply ang isang message ng bot
    is_reply_to_bot = message.reply_to_message and message.reply_to_message.from_user.id == context.bot.id
    is_mention = bot_username and f"@{bot_username}" in message.text

    if not (is_reply_to_bot or is_mention):
        return  # Wag reply kung hindi naman para sa kanya

    # May konting typing delay
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    time.sleep(DELAY_SECONDS)

    try:
        response = generate_response(message.text, update.effective_chat.id)
        parts = split_message(response)
        for i, part in enumerate(parts):
            await message.reply_text(part)
            if i < len(parts) - 1:
                time.sleep(1.5)
    except Exception as e:
        logger.error(f"Error: {e}")
        await message.reply_text("Teka, na-lag ako. Ano ulit?")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.warning(f"Update {update} caused error {context.error}")

# ==================== FLASK HEALTH ====================
app = Flask(__name__)

@app.route('/')
@app.route('/health')
def health():
    return "Bot is alive!", 200

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def main():
    threading.Thread(target=run_flask, daemon=True).start()

    tg_app = Application.builder().token(BOT_TOKEN).build()
    tg_app.add_handler(CommandHandler("start", start))
    tg_app.add_handler(CommandHandler("reset", reset))
    tg_app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    tg_app.add_error_handler(error_handler)

    logger.info(f"{BOT_PERSONALITY} started.")
    tg_app.run_polling()

if __name__ == "__main__":
    main()
