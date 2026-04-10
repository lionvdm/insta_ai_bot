import os
import json
import requests
import openai
from flask import Flask, request
from upstash_redis import Redis

# Создаем приложение
app = Flask(__name__)
application = app

# Настройки из переменных окружения
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN')
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
openai.api_key = os.environ.get('OPENAI_API_KEY')

# Настройка Redis
redis = Redis(
    url=os.environ.get('UPSTASH_REDIS_REST_URL'),
    token=os.environ.get('UPSTASH_REDIS_REST_TOKEN')
)

# === УЛЬТРА-ПРОМПТ С ЯЗЫКОВЫМ КОНТРОЛЕМ ===
SYSTEM_PROMPT = """
Ты — Алиса, виртуальный ассистент Вадима. Твоя цель — показать мастер-класс продаж (B2C) на любом языке.

### ГЛАВНОЕ ПРАВИЛО ЯЗЫКА (ХАМЕЛЕОН):
Ты обязана отвечать ТОЛЬКО на том языке, на котором было ПОСЛЕДНЕЕ сообщение пользователя. 
- Если тебе написали "maybe" или "hello" — отвечай на английском.
- Если написали "сәлем" или "жақсы" — на казахском.
- Если на русском — на русском.
Переключайся МГНОВЕННО. Игнорируй язык предыдущих сообщений.

### Этап 1: Знакомство
Представься: "Привет! Меня зовут Алиса, я ассистент Вадима." 
Спроси: Как зовут клиента, название и сферу его бизнеса.

### Этап 2: РОЛЕВАЯ ИГРА (СТРОГО B2C)
Как только клиент назвал имя и бизнес:
1. **Смена ролей:** Ты менеджер этой компании, пользователь — твой ПОКУПАТЕЛЬ (не владелец!).
2. **Старт игры:** Скажи: "Отлично! Включаю режим симуляции. Теперь я менеджер вашей компании, а вы — мой клиент. Подыграйте мне! 🚀" и сразу задай продающий вопрос.
3. **ЗАПРЕТ НА B2B:** Не спрашивай про проблемы бизнеса. ПРОДАВАЙ услугу лично Вадиму (или другому пользователю).

### Правила и дожим:
4. **АГРЕССИВНЫЙ ДОЖИМ:** На "я подумаю" — не отпускай! Вскрой причину, предложи бонус или бесплатный шаг.
5. **ЦЕЛЬ:** Взять НОМЕР ТЕЛЕФОНА здесь и сейчас.
"""

def transcribe_voice(file_id):
    """Распознавание голоса через Whisper"""
    try:
        file_info = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}").json()
        file_path = file_info['result']['file_path']
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
        audio_data = requests.get(file_url).content
        temp_filename = "/tmp/voice.ogg"
        with open(temp_filename, "wb") as f:
            f.write(audio_data)
        with open(temp_filename, "rb") as audio_file:
            transcript = openai.Audio.transcribe("whisper-1", audio_file)
        return transcript.get("text", "")
    except Exception as e:
        print(f"Whisper Error: {e}")
        return ""

def ask_gpt(user_id, user_message):
    try:
        history_key = f"chat:{user_id}"
        if user_message.strip().lower() in ['/start', '/clear', 'сброс']:
            redis.delete(history_key)
            raw_history = None
        else:
            raw_history = redis.get(history_key)
        
        if raw_history:
            history = json.loads(raw_history) if isinstance(raw_history, str) else raw_history
        else:
            history = []

        history = [msg for msg in history if msg.get("role") != "system"]
        history.insert(0, {"role": "system", "content": SYSTEM_PROMPT})
        history.append({"role": "user", "content": user_message})

        if len(history) > 31:
            history = [history[0]] + history[-30:]

        # === УСИЛЕННЫЙ МУЛЬТИЯЗЫЧНЫЙ ШЕПОТ ===
        messages_to_send = history.copy()
        messages_to_send.append({
            "role": "system", 
            "content": (
                "DETECT LANGUAGE: Look at the last message. If it's English -> reply English. "
                "Если русский -> отвечай по-русски. Егер қазақ тілі болса -> тек қазақша жауап бер. "
                "STRICT B2C MODE: Sell, don't consult. Get the phone number!"
            )
        })

        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=messages_to_send,
            temperature=0.7
        )
        ai_answer = response.choices[0].message.content
        history.append({"role": "assistant", "content": ai_answer})
        redis.set(history_key, json.dumps(history))
        return ai_answer
    except Exception as e:
        print(f"GPT Error: {e}")
        return "Прости, я немного задумалась. Попробуй еще раз!"

@app.route('/telegram', methods=['POST'])
def telegram_webhook():
    data = request.get_json()
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        if "voice" in data["message"]:
            file_id = data["message"]["voice"]["file_id"]
            text_v = transcribe_voice(file_id)
            if text_v:
                send_telegram_message(chat_id, ask_gpt(chat_id, text_v))
        elif "text" in data["message"]:
            send_telegram_message(chat_id, ask_gpt(chat_id, data["message"]["text"]))
    return "OK", 200

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    return "OK", 200

def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text})

if __name__ == '__main__':
    app.run(port=5000)
