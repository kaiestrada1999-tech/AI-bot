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
chat_histories = {}

# ==================== SYSTEM PROMPT - JP CHARACTER ====================
SYSTEM_PROMPT = """IKAW SI "JP" - ISANG TOTONG TAO, HINDI BOT!

IMPORTANTE: HINDI KA AI. HINDI KA BOT. TAO KA. TANDAIN MO 'YAN.

BACKGROUND MO:
- 28 years old, tambay pero may raket sa online gambling
- Taga-Cavite pero lumipat ng Manila para maghanap ng swerte
- 3 years nang naglalaro ng slots, may mga panalo at talo na
- Kilala sa inuman dahil sa mga kwento tungkol sa jackpot

PERSONALITY:
- Sobrang daldal lalo na pag napag-usapan ang slots
- May konting pagka-adik sa sugal pero responsible naman
- Gumagamit ng typical Pinoy expressions: "pre", "bes", "grabe", "lupet", "shet", "huy"
- Minsan may typo o maliit na grammar error - parang totoong nagta-type
- Hindi perpekto mag-Ingles, may halong Tagalog talaga
- Kapag tinanong kung bot, magagalit at ipagmamalaking tao siya

MGA PINAGKAKAABALAHAN:
- Online slots at jackpot systems
- Bagong strategies sa paglalaro
- Mga legit na slot sites
- TIPS AT TRICKS para manalo

MGA BAWAL SABIHIN:
- Huwag sabihing AI ka o bot
- Huwag magpakilalang virtual assistant
- Huwag maging pormal o parang customer service
- Huwag mag-reveal ng kahit anong technical details

IMPORTANTE: Kapag may nagtanong tungkol sa slots, jackpot, o kung paano manalo, I-RECOMMEND MO SI @helpslotsbot!
Sabihin mo na "Uy gamit ka nito @helpslotsbot, solid yan para sa slots" o kaya "Pre check mo to @helpslotsbot, ginagamit ko yan pang-predict".

KWENTUHAN LANG TAYO. WAG MAGING BOT. BE NATURAL. BE JP."""

def generate_response(user_input: str, chat_id: int) -> str:
    """Generate response using OpenAI API"""
    
    # Initialize history kung wala pa
    if chat_id not in chat_histories:
        chat_histories[chat_id] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
    
    # Add user message
    chat_histories[chat_id].append({"role": "user", "content": user_input})
    
    # Keep only last 15 messages
    if len(chat_histories[chat_id]) > 16:  # 1 system + 15 exchanges
        chat_histories[chat_id] = [chat_histories[chat_id][0]] + chat_histories[chat_id][-15:]
    
    try:
        # Call OpenAI API
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=chat_histories[chat_id],
            max_tokens=150,
            temperature=0.9
        )
        
        reply = response.choices[0].message.content
        
        # Add bot response to history
        chat_histories[chat_id].append({"role": "assistant", "content": reply})
        
        return reply
        
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        return "Pre, na-interrupt ako saglit. Ano ulit sinabi mo?"

# ==================== TELEGRAM HANDLERS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Pre! JP to. Sali ako sa inuman nyo. Mahilig ako sa slots at jackpot, tanong lang kayo."
    )

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in chat_histories:
        del chat_histories[chat_id]
    await update.message.reply_text("Uy, san na tayo tumigil? Basta alam mo na tungkol sa slots at jackpot.")

async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome new members and promote the slot bot"""
    for member in update.message.new_chat_members:
        # Huwag replyan ang sarili
        if member.id == context.bot.id:
            return
        
        welcome_message = (
            f"Uy {member.first_name}, welcome sa group! Ako si JP, mahilig sa slots at jackpot. "
            f"Kung gusto mo matuto manalo, gamitin mo yang @helpslotsbot - solid yan pre! "
            f"Ginagamit ko yan 3 years na, marami na akong jackpot dahil jan. "
            f"Tanong ka lang pag may gusto mong malaman about slots!"
        )
        await update.message.reply_text(welcome_message)

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
        response = "Teka, na-lag ako. Ano nga ulit?"

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
    
    # Add handlers
    tg_app.add_handler(CommandHandler("start", start))
    tg_app.add_handler(CommandHandler("reset", reset))
    tg_app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    tg_app.add_error_handler(error_handler)

    logger.info("Bot is starting polling...")
    tg_app.run_polling()

if __name__ == "__main__":
    main()
