import os
import json
import logging
import time
import threading
import random
import asyncio
from multiprocessing import Process, Manager
from flask import Flask
from openai import OpenAI
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- Load configuration ---
with open('config.json', 'r') as f:
    config = json.load(f)

# --- Read sensitive data from environment variables ---
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable not set")

TOKEN_TAWA = os.environ.get("BOT_TOKEN_TAWA")
TOKEN_ISIP = os.environ.get("BOT_TOKEN_ISIP")
TOKEN_BOBO = os.environ.get("BOT_TOKEN_BOBO")

if not all([TOKEN_TAWA, TOKEN_ISIP, TOKEN_BOBO]):
    raise ValueError("Missing bot tokens. Set BOT_TOKEN_TAWA, BOT_TOKEN_ISIP, BOT_TOKEN_BOBO")

bots_config = [
    {"name": "Tawa", "token": TOKEN_TAWA, "system_prompt": config["bots"][0]["system_prompt"]},
    {"name": "Isip", "token": TOKEN_ISIP, "system_prompt": config["bots"][1]["system_prompt"]},
    {"name": "Bobo", "token": TOKEN_BOBO, "system_prompt": config["bots"][2]["system_prompt"]},
]

# --- Shared OpenAI Client ---
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# --- Settings ---
SLOTS_KEYWORDS = [
    'slot', 'jackpot', 'casino', 'manalo', 'talo', 'sugal', 'pustahan',
    'bigballer', 'agilaclub', 'quantumbbc', 'fortuneplay', 'helpslotsbot',
    'panalo', 'spin', 'bonus', 'free spin', 'gambling', 'pano manalo',
    'paano manalo', 'ano maganda', 'saan maganda', 'anong maganda'
]

# --- Shared state for conversation control ---
manager = Manager()
conv_state = manager.dict()
conv_state['enabled'] = True
conv_state['active'] = False
conv_state['chat_id'] = None
conv_state['last_bot'] = None
conv_state['message_count'] = 0
conv_state['last_message_time'] = 0

# ==================== BOT WORKER ====================
def run_bot(bot_name, bot_token, system_prompt, state):
    logging.basicConfig(format=f"%(asctime)s - {bot_name} - %(levelname)s - %(message)s", level=logging.INFO)
    logger = logging.getLogger(__name__)

    chat_histories = {}
    last_spontaneous_time = {}

    def is_question(text):
        text_lower = text.lower()
        has_question_mark = '?' in text
        has_keyword = any(kw in text_lower for kw in SLOTS_KEYWORDS)
        return has_question_mark and has_keyword

    def generate_response(user_input: str, chat_id: int) -> str:
        if chat_id not in chat_histories:
            chat_histories[chat_id] = [{"role": "system", "content": system_prompt}]

        chat_histories[chat_id].append({"role": "user", "content": user_input})

        if len(chat_histories[chat_id]) > 11:
            chat_histories[chat_id] = [chat_histories[chat_id][0]] + chat_histories[chat_id][-10:]

        try:
            response = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=chat_histories[chat_id],
                max_tokens=70,
                temperature=0.9
            )
            reply = response.choices[0].message.content
            chat_histories[chat_id].append({"role": "assistant", "content": reply})
            return reply
        except Exception as e:
            logger.error(f"OpenAI error: {e}")
            return "Pre, na-lag ako. Ano ulit?"

    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user and update.effective_user.id == context.bot.id:
            return
        if not update.message or not update.message.text:
            return

        chat_id = update.effective_chat.id
        message = update.message
        text = message.text
        now = time.time()

        # --- Handle /tahimik and /galaw commands ---
        if text.startswith('/tahimik'):
            state['enabled'] = False
            state['active'] = False
            await message.reply_text(f"🤫 Sige, tahimik muna kami.")
            return

        if text.startswith('/galaw'):
            state['enabled'] = True
            await message.reply_text(f"🎮 G na! Pwede na ulit mag-usap.")
            return

        # --- Check if this is a question that should trigger conversation ---
        if state['enabled'] and is_question(text) and not state['active']:
            state['active'] = True
            state['chat_id'] = chat_id
            state['last_bot'] = None
            state['message_count'] = 0
            state['last_message_time'] = now
            logger.info(f"🎭 Conversation triggered by question in chat {chat_id}")
            
            # Random chance for this bot to start (50%)
            if random.random() < 0.5:
                await context.bot.send_chat_action(chat_id=chat_id, action="typing")
                await asyncio.sleep(random.uniform(4, 8))
                
                # Simple prompt without mentioning names
                prompt = f"May nagtanong: '{text}'. Ano masasabi mo dito?"
                response = generate_response(prompt, chat_id)
                await message.reply_text(response)
                
                state['last_bot'] = bot_name
                state['message_count'] += 1
                state['last_message_time'] = time.time()
            return

        # --- Continue ongoing conversation (without mentioning names) ---
        if state['enabled'] and state['active'] and state['chat_id'] == chat_id:
            time_diff = now - state['last_message_time']
            if time_diff > random.uniform(20, 60) and state['last_bot'] != bot_name and state['message_count'] < 6:
                if random.random() < 0.8:
                    # Random topics - no names mentioned
                    topics = [
                        "ako sa Bigballer ako nanalo eh",
                        "gamit kayo @helpslotsbot solid yan",
                        "haha true yan",
                        "ano ba yan",
                        "sabi ko na eh",
                        "talaga ba?",
                        "sa AgilaClub din maganda",
                        "QuantumBBC okay din",
                        "ako naniniwala jan",
                        "haha tawa ako nang tawa"
                    ]
                    prompt = random.choice(topics)
                    
                    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
                    await asyncio.sleep(random.uniform(5, 10))
                    
                    response = generate_response(prompt, chat_id)
                    await message.reply_text(response)
                    
                    state['last_bot'] = bot_name
                    state['message_count'] += 1
                    state['last_message_time'] = time.time()
                    logger.info(f"{bot_name} continued conversation")
                    
                    if state['message_count'] >= 6 or random.random() < 0.15:
                        state['active'] = False
                        logger.info("Conversation ended")
            return

        # --- Normal reply logic (targeted or spontaneous) ---
        is_reply_to_bot = message.reply_to_message and message.reply_to_message.from_user.id == context.bot.id
        is_mention = context.bot.username and f"@{context.bot.username}" in text

        should_reply = False

        if is_reply_to_bot or is_mention:
            should_reply = True
            logger.info(f"{bot_name} replying to targeted message")
        else:
            if not state['active'] and any(kw in text.lower() for kw in SLOTS_KEYWORDS):
                last_time = last_spontaneous_time.get(chat_id, 0)
                if now - last_time > 300:
                    if random.random() < 0.25:
                        should_reply = True
                        last_spontaneous_time[chat_id] = now
                        logger.info(f"{bot_name} spontaneous reply triggered")

        if not should_reply:
            return

        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        await asyncio.sleep(random.uniform(5, 10))

        try:
            response = generate_response(text, chat_id)
            await message.reply_text(response)
        except Exception as e:
            logger.error(f"Error: {e}")
            await message.reply_text("Teka, na-lag ako.")

    async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.warning(f"Update {update} caused error {context.error}")

    # --- Retry mechanism ---
    max_retries = 3
    for attempt in range(max_retries):
        try:
            tg_app = Application.builder().token(bot_token).connect_timeout(30).read_timeout(30).build()
            tg_app.add_handler(CommandHandler("tahimik", handle_message))
            tg_app.add_handler(CommandHandler("galaw", handle_message))
            tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
            tg_app.add_error_handler(error_handler)
            
            logger.info(f"{bot_name} starting (attempt {attempt+1})...")
            tg_app.run_polling()
            break
        except Exception as e:
            logger.error(f"{bot_name} failed to start: {e}")
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 5
                logger.info(f"{bot_name} retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logger.error(f"{bot_name} failed after {max_retries} attempts. Giving up.")
                raise

# ==================== FLASK HEALTH CHECK ====================
app = Flask(__name__)

@app.route('/')
@app.route('/health')
def health():
    return "Bot Trio is alive!", 200

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# ==================== MAIN ====================
if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    processes = []
    for i, bot in enumerate(bots_config):
        if i > 0:
            delay = random.uniform(3, 7)
            print(f"⏱️ Waiting {delay:.1f} seconds before starting {bot['name']}...")
            time.sleep(delay)
        
        p = Process(target=run_bot, args=(bot["name"], bot["token"], bot["system_prompt"], conv_state))
        p.start()
        processes.append(p)
        print(f"✅ Started {bot['name']} in process {p.pid}")

    try:
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        print("🛑 Shutting down...")
        for p in processes:
            p.terminate()
            p.join()
