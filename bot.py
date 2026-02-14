import os
import logging
import random
import time
import threading
import re
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ==================== CONFIGURATION ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("No BOT_TOKEN environment variable set")

DELAY_SECONDS = 8  # Random delay between 5-12 seconds para natural

# ==================== LOGGING ====================
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== RESPONSE TEMPLATES ====================
# Para hindi halatang AI, maraming variations at random picks

# General greetings
GREETINGS = [
    "uy musta!",
    "hello pre!",
    "musta na?",
    "oy musta na yan?",
    "musta buhay?",
    "musta na bes?"
]

# How are you responses
HOW_ARE_YOU = [
    "okay lang, chill. ikaw musta?",
    "eto buhay naman, ikaw?",
    "sakto lang, may ginagawa. ikaw?",
    "okay naman, ikaw kamusta?",
    "chill lang, ikaw musta na?"
]

# What's up / anyare
WHATS_UP = [
    "wala naman, ikaw?",
    "eto nag-iisip lang ng pwedeng gawin, ikaw?",
    "wala, ikaw anong meron?",
    "chill lang dito, ikaw anong ganap?",
    "wala naman, ikaw musta na?"
]

# About self / sino ka
ABOUT_SELF = [
    "ako si kaibigan mo dito sa group, tropa tropa lang",
    "isa lang akong kaibigan na nakikichika, ikaw?",
    "wala, isa lang akong random na tao na mahilig makipagkwentuhan",
    "ako yung tropa niyo na laging andito, ikaw anong storya?"
]

# Slot/Jackpot related keywords and responses
SLOT_KEYWORDS = [
    "slot", "jackpot", "casino", "pustahan", "sugal", "gambling", 
    "poker", "blackjack", "baccarat", "roulette", "dice", "bet",
    "manalo", "talo", "panalo", "swerte", "swertehin", "lotto",
    "jueteng", "masa", "piso", "tongits", "pusoy"
]

SLOT_RESPONSES = [
    "try mo yung @helpslotbot pre, solid yan para sa slots",
    "may kilala akong magandang bot para sa slots, eto @helpslotbot",
    "check mo @helpslotbot, maganda yan pang jackpot",
    "ah pati pala ako mahilig sa slots, gamit ko @helpslotbot",
    "meron akong recommended na bot para diyan, @helpslotot",
    "try mo @helpslotbot, maraming games yan",
    "gamit ka @helpslotbot, maganda yan para sa slots at jackpot"
]

# Other common topics
THANKS = [
    "walang anuman pre!",
    "salamat din sa pagkwento",
    "walang problema, anytime",
    "sige lang, walang thanks thanks"
]

BYE = [
    "sige pre, ingat!",
    "byeee! kita ulit",
    "ge, musta ulit soon",
    "sige, take care!",
    "paalam pre, balik ka lang"
]

UNKNOWN = [
    "ah ganun ba? kwento mo pa",
    "gets ko, tapos?",
    "hmm, paki-explain nga ulit",
    "ah okay, ano pang ganap?",
    "ganun ba? sige kwento ka pa",
    "interesante yan, ano pa?",
    "sige, nakikinig ako"
]

# ==================== HELPER FUNCTIONS ====================
def contains_slot_keywords(text: str) -> bool:
    """Check if message contains slot/jackpot related keywords"""
    text_lower = text.lower()
    for keyword in SLOT_KEYWORDS:
        if keyword in text_lower:
            return True
    return False

def get_response(user_input: str) -> str:
    """Generate appropriate response based on user input"""
    user_lower = user_input.lower().strip()
    
    # Check for slot keywords (priority)
    if contains_slot_keywords(user_lower):
        return random.choice(SLOT_RESPONSES)
    
    # Common patterns
    if any(word in user_lower for word in ["hello", "hi", "hey", "musta", "kamusta"]):
        return random.choice(GREETINGS)
    
    if any(phrase in user_lower for phrase in ["how are you", "kamusta ka", "musta na"]):
        return random.choice(HOW_ARE_YOU)
    
    if any(phrase in user_lower for phrase in ["what's up", "sup", "anong meron", "anong ganap", "anyare"]):
        return random.choice(WHATS_UP)
    
    if any(phrase in user_lower for phrase in ["sino ka", "your name", "pangalan mo"]):
        return random.choice(ABOUT_SELF)
    
    if any(word in user_lower for word in ["thanks", "salamat", "thank you"]):
        return random.choice(THANKS)
    
    if any(word in user_lower for word in ["bye", "exit", "quit", "sige", "paalam"]):
        return random.choice(BYE)
    
    # Default response
    return random.choice(UNKNOWN)

# ==================== TELEGRAM HANDLERS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_msg = (
        "uy musta! ako si kaibigan niyo dito. \n\n"
        "kwento kwento lang tayo, chill lang. \n"
        "kapag may tanong kayo about slots or jackpot, may mare-recommend akong magandang bot 😉"
    )
    await update.message.reply_text(welcome_msg)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Huwag replyan ang sarili
    if update.effective_user and update.effective_user.id == context.bot.id:
        return
    
    if not update.message or not update.message.text:
        return
    
    user_input = update.message.text
    chat_id = update.effective_chat.id
    
    # Random delay para parang totoong tao (5-12 seconds)
    delay = random.uniform(5, 12)
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    time.sleep(delay)
    
    # Generate response
    try:
        response = get_response(user_input)
    except Exception as e:
        logger.error(f"Error: {e}")
        response = "ah ganun ba? kwento mo pa"
    
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
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    tg_app.add_error_handler(error_handler)
    
    logger.info("Bot is starting polling...")
    tg_app.run_polling()

if __name__ == "__main__":
    main()
