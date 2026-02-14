import os
import logging
import random
import time
import threading
import torch
from flask import Flask
from transformers import AutoModelForCausalLM, AutoTokenizer
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ==================== CONFIGURATION ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("No BOT_TOKEN environment variable set")

# Para hindi mag-compile ng Rust packages (gagamit ng pre-built wheels)
os.environ["CARGO_HOME"] = "/tmp/.cargo"
os.environ["RUSTUP_HOME"] = "/tmp/.rustup"

# Force CPU at memory optimization
torch.set_num_threads(1)
torch.set_num_interop_threads(1)
os.environ["OMP_NUM_THREADS"] = "1"

REPLY_TO_ALL = True           # True = sa lahat ng message sasagot; False = sa tanong lang
QUESTION_ONLY = not REPLY_TO_ALL
DELAY_SECONDS = 10             # Delay bago sumagot
USE_PER_CHAT_HISTORY = True    # True = iisa lang history per group; False = per user

# ==================== LOGGING ====================
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== LOAD MODEL (once) ====================
logger.info("Loading DialoGPT model...")
model_name = "microsoft/DialoGPT-small"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(model_name)
tokenizer.pad_token = tokenizer.eos_token
logger.info("Model loaded successfully!")

# ==================== CONVERSATION HISTORY ====================
chat_histories = {}

# Filipino fillers at prefixes
FILLERS = ["", " hmm", " ah", " e", " o", " ha", " no?", " diba?"]
PREFIXES = ["", "Sa tingin ko ", "Para sa akin ", "Siguro ", "Ewan ko ha, pero "]

QUESTION_WORDS = ["ano", "sino", "bakit", "paano", "saan", "kailan", "magkano", "alin",
                  "what", "who", "why", "how", "where", "when", "which"]

# ==================== HELPER FUNCTIONS ====================
def is_question(text: str) -> bool:
    text_lower = text.lower().strip()
    if "?" in text:
        return True
    words = text_lower.split()
    if words and words[0] in QUESTION_WORDS:
        return True
    return False

def generate_response(user_input: str, history_key: int) -> str:
    new_ids = tokenizer.encode(user_input + tokenizer.eos_token, return_tensors='pt')
    history = chat_histories.get(history_key)

    if history is not None:
        bot_input_ids = torch.cat([history, new_ids], dim=-1)
    else:
        bot_input_ids = new_ids

    attention_mask = torch.ones_like(bot_input_ids)
    with torch.no_grad():
        history = model.generate(
            bot_input_ids,
            attention_mask=attention_mask,
            max_length=1000,
            pad_token_id=tokenizer.eos_token_id,
            do_sample=True,
            top_k=50,
            top_p=0.95,
            temperature=0.8,
            no_repeat_ngram_size=3,
        )

    chat_histories[history_key] = history

    response_ids = history[:, bot_input_ids.shape[-1]:]
    response = tokenizer.decode(response_ids[0], skip_special_tokens=True)

    if random.random() < 0.3:
        response = random.choice(PREFIXES) + response.lower()
    if random.random() < 0.4:
        response += random.choice(FILLERS)

    return response

# ==================== TELEGRAM HANDLERS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Ako si 'Kaibigan' – kasama ninyo sa group. Magtatanong lang kayo, sasagot ako… pero antagal ko mag-isip, mga 10 seconds! 😅"
    )

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in chat_histories:
        del chat_histories[chat_id]
    await update.message.reply_text("🔄 Nakalimutan ko na ang pinag-usapan natin. Sige, magsimula tayong muli.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Huwag replyan ang sarili
    if update.effective_user and update.effective_user.id == context.bot.id:
        return

    if not update.message or not update.message.text:
        return

    message_text = update.message.text

    if QUESTION_ONLY and not is_question(message_text):
        return

    if USE_PER_CHAT_HISTORY:
        history_key = update.effective_chat.id
    else:
        history_key = update.effective_user.id if update.effective_user else update.effective_chat.id

    # Ipakita ang typing at maghintay
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    time.sleep(DELAY_SECONDS)  # Blocking, pero okay lang dahil isa lang bot instance

    try:
        response = generate_response(message_text, history_key)
    except Exception as e:
        logger.error(f"Error: {e}")
        response = "Sorry, may error. Paki-ulit?"

    await update.message.reply_text(response)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.warning(f"Update {update} caused error {context.error}")

# ==================== FLASK WEB SERVER (for health checks) ====================
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
    # Start Flask in a background thread
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
