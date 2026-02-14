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
from telegram.ext import Application, MessageHandler, filters, ContextTypes

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

# --- Shared state for conversation ---
manager = Manager()
conv_state = manager.dict()
conv_state['active'] = False          # May ongoing conversation ba?
conv_state['chat_id'] = None
conv_state['last_bot'] = None
conv_state['last_message_time'] = 0
conv_state['message_count'] = 0

# ==================== BOT WORKER ====================
def run_bot(bot_name, bot_token, system_prompt, state):
    logging.basicConfig(format=f"%(asctime)s - {bot_name} - %(levelname)s - %(message)s", level=logging.INFO)
    logger = logging.getLogger(__name__)

    chat_histories = {}
    last_reply_time = {}  # Para sa cooldown

    def generate_response(user_input: str, chat_id: int, context_type="normal") -> str:
        if chat_id not in chat_histories:
            chat_histories[chat_id] = [{"role": "system", "content": system_prompt}]

        chat_histories[chat_id].append({"role": "user", "content": user_input})

        if len(chat_histories[chat_id]) > 15:
            chat_histories[chat_id] = [chat_histories[chat_id][0]] + chat_histories[chat_id][-14:]

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

        # --- Check if this message is from another bot ---
        is_from_bot = update.effective_user and update.effective_user.is_bot
        is_from_our_bot = is_from_bot and update.effective_user.username in [f"{b['name'].lower()}_bot" for b in bots_config]

        # --- Conversation logic ---
        if is_from_our_bot:
            # Isa sa tatlong bots ang nag-message
            if state['active'] and state['chat_id'] == chat_id:
                # May ongoing conversation
                if state['last_bot'] != bot_name:  # Hindi ito ang huling sumagot
                    # Random chance to continue (70%)
                    if random.random() < 0.7 and state['message_count'] < 8:
                        # Random delay (15-45 seconds)
                        delay = random.uniform(15, 45)
                        await asyncio.sleep(delay)
                        
                        # Generate response na natural
                        prompt = f"May kausap ka sa group. Natural na sumagot, parang totoong tao. {text}"
                        response = generate_response(prompt, chat_id, "conversation")
                        
                        await message.reply_text(response)
                        
                        # Update state
                        state['last_bot'] = bot_name
                        state['message_count'] += 1
                        state['last_message_time'] = time.time()
                        logger.info(f"{bot_name} continued conversation")
                        
                        # 10% chance to end conversation
                        if random.random() < 0.1 or state['message_count'] >= 8:
                            state['active'] = False
                            logger.info("Conversation ended naturally")
            return

        # --- Start new conversation (random chance) ---
        if not state['active'] and random.random() < 0.1:  # 10% chance per message
            state['active'] = True
            state['chat_id'] = chat_id
            state['last_bot'] = None
            state['message_count'] = 0
            state['last_message_time'] = now
            logger.info(f"🎭 New conversation started by random chance in chat {chat_id}")
            
            # This bot might start the conversation (50% chance)
            if random.random() < 0.5:
                await context.bot.send_chat_action(chat_id=chat_id, action="typing")
                await asyncio.sleep(random.uniform(5, 10))
                
                topics = [
                    "Uy musta na kayo?",
                    "May bagong slots ba?",
                    "Na-miss ko kayo!",
                    "Ang tahimik dito ah",
                    "May chika ba?"
                ]
                starter = random.choice(topics)
                response = generate_response(starter, chat_id, "starter")
                await message.reply_text(response)
                
                state['last_bot'] = bot_name
                state['message_count'] += 1
                state['last_message_time'] = time.time()
            return

        # --- Normal reply to users (mention or reply) ---
        is_reply_to_bot = message.reply_to_message and message.reply_to_message.from_user.id == context.bot.id
        is_mention = context.bot.username and f"@{context.bot.username}" in text

        if is_reply_to_bot or is_mention:
            # Check cooldown para iwas spam
            last_time = last_reply_time.get(chat_id, 0)
            if now - last_time > 30:  # Minimum 30 seconds between replies
                last_reply_time[chat_id] = now
                
                await context.bot.send_chat_action(chat_id=chat_id, action="typing")
                await asyncio.sleep(random.uniform(5, 10))
                
                response = generate_response(text, chat_id, "targeted")
                await message.reply_text(response)
                logger.info(f"{bot_name} replied to targeted message")

    async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.warning(f"Update {update} caused error {context.error}")

    # --- Retry mechanism ---
    max_retries = 3
    for attempt in range(max_retries):
        try:
            tg_app = Application.builder().token(bot_token).connect_timeout(30).read_timeout(30).build()
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
