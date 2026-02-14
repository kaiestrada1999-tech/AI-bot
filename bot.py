import os
import logging
import time
import threading
from flask import Flask
from openai import OpenAI
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ==================== CONFIGURATION ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

if not BOT_TOKEN:
    raise ValueError("No BOT_TOKEN environment variable set")
if not OPENAI_API_KEY:
    raise ValueError("No OPENAI_API_KEY environment variable set")

DELAY_SECONDS = 10  # Delay bago sumagot

# ==================== LOGGING ====================
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== OPENAI CLIENT ====================
client = OpenAI(api_key=OPENAI_API_KEY)

# ==================== CONVERSATION HISTORY ====================
# Simple dictionary: chat_id -> list of messages
chat_histories = {}

# System prompt para maging casual at Filipino
SYSTEM_PROMPT = """Ikaw ay isang kaibigang Pinoy na nakikipagkwentuhan sa group chat. 
Maging natural, casual, at conversational. 
Gumamit ng konting Taglish (Tagalog-English) at mga Filipino expressions like 'pre', 'bes', 'kasi', 'ano ba'.
Huwag maging formal o parang bot. Parang tropa lang."""

def generate_response(user_input: str, chat_id: int) -> str:
    """Generate response using OpenAI API"""
    
    # Initialize history kung wala pa
    if chat_id not in chat_histories:
        chat_histories[chat_id] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
    
    # Add user message
    chat_histories[chat_id].append({"role": "user", "content": user_input})
    
    # Keep only last 10 messages (para tipid sa tokens)
    if len(chat_histories[chat_id]) > 11:  # 1 system + 10 exchanges
        chat_histories[chat_id] = [chat_histories[chat_id][0]] + chat_histories[chat_id][-10:]
    
    try:
        # Call OpenAI API
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",  # Pwedeng "gpt-4" kung meron
            messages=chat_histories[chat_id],
            max_tokens=150,
            temperature=0.8
        )
        
        reply = response.choices[0].message.content
        
        # Add bot response to history
        chat_histories[chat_id].append({"role": "assistant", "content": reply})
        
        return reply
        
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        return "Sorry pre, na-ERROR ako saglit. Try mo ulit?"

# ==================== TELEGRAM HANDLERS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Pre! Ako si 'Kaibigan' – kasama niyo sa group. Tanong lang kayo, sasagot ako after 10 seconds! 😅"
    )

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in chat_histories:
        del chat_histories[chat_id]
    await update.message.reply_text("🔄 Nakalimutan ko na usapan natin. Sige, simula ulit!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Huwag replyan ang sarili
    if update.effective_user and update.effective_user.id == context.bot.id:
        return

    if not update.message or not update.message.text:
        return

    # Ipakita ang typing at maghintay
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    time.sleep(DELAY_SECONDS)

    try:
        response = generate_response(update.message.text, update.effective_chat.id)
    except Exception as e:
        logger.error(f"Error: {e}")
        response = "Sorry, may error. Paki-ulit?"

    await update.message.reply_text(response)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.warning(f"Update {update} caused error {context.error}")

# ==================== FLASK HEALTH CHECK ====================
app = Flask(__name__)

@app.route('/')
@app.route('/health')
def health():
    return "Bot is alive!", 200

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# ==================== MAIN ====================
def main():
    # Start Flask
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Setup Telegram bot
    tg_app = Application.builder().token(BOT_TOKEN).build()
    tg_app.add_handler(CommandHandler("start", start))
    tg_app.add_handler(CommandHandler("reset", reset))
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    tg_app.add_error_handler(error_handler)

    logger.info("Bot is starting polling...")
    tg_app.run_polling()

if __name__ == "__main__":
    main()
