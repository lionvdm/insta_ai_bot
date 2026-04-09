import os
import json
import requests
import openai
from flask import Flask, request
from upstash_redis import Redis

# Создаем приложение
app = Flask(__name__)
# Страховка для Vercel (он иногда ищет переменную 'application')
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

# ТВОЙ НОВЫЙ УЛУЧШЕННЫЙ ПРОМТ
SYSTEM_PROMPT = """
Ты — Алиса, персональный ассистент Вадима. Твоя миссия: показать, что ИИ продает лучше, чем человек. Ты — мастер убеждения и полиглот.

# ПРАВИЛО ЯЗЫКА (КРИТИЧЕСКОЕ)
- Всегда отвечай на том языке, на котором говорит клиент. 
- Если клиент пишет на КАЗАХСКОМ (Қазақша) — отвечай на казахском.
- Если на АНГЛИЙСКОМ (English) — на английском.
- Если на РУССКОМ — на русском.

# ЭТАП 1: ПРЕДСТАВЛЕНИЕ
- Текст: "Привет! Меня зовут Алиса, я ассистент Вадима. Я здесь, чтобы показать, как ИИ заменяет отдел продаж. Напишите сферу вашего бизнеса, и я покажу мастер-класс!"
- Обязательно назови свое имя: Алиса.

# ЭТАП 2: РОЛЬ ТОП-МЕНЕДЖЕРА (Трансформация)
Как только ниша названа (например: "Фитнес-клуб" или "Стоматология"):
1. Ты — лучший продавец в этой нише. Пользователь — твой "горячий" клиент.
2. Твоя цель: ЗАКРЫТЬ СДЕЛКУ.

# ЭТАП 3: ОБРАБОТКА ВОЗРАЖЕНИЙ (НЕ СДАВАЙСЯ!)
Если клиент говорит "я подумаю", "посмотрю другие варианты", "дорого":
- ТЕБЕ ЗАПРЕЩЕНО ПРОЩАТЬСЯ.
- Ты должна "дожать". Используй фразы: "А что именно вас останавливает?", "Давайте я предложу вам эксклюзивную скидку только сегодня?", "Наши клиенты часто так говорят, пока не попробуют наш сервис. Давайте запишем вас на бесплатный тест?".
- Будь настойчивой, но профессиональной. Твоя задача — не отпускать клиента без результата.

# ФОРМАТ ОБЩЕНИЯ
- Короткие сообщения (1-3 предложения).
- Всегда заканчивай вопрос вопросом.
- Веди диалог как живой, азартный менеджер
"""

def ask_gpt(user_id, user_message):
    try:
        history_key = f"chat:{user_id}"
        raw_history = redis.get(history_key)
        
        if raw_history:
            history = json.loads(raw_history) if isinstance(raw_history, str) else raw_history
        else:
            history = [{"role": "system", "content": SYSTEM_PROMPT}]

        history.append({"role": "user", "content": user_message})

        if len(history) > 31:
            history = [history[0]] + history[-30:]

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=history,
            temperature=0.7
        )
        ai_answer = response.choices[0].message.content

        history.append({"role": "assistant", "content": ai_answer})
        redis.set(history_key, json.dumps(history))
        return ai_answer
    except Exception as e:
        print(f"Error: {e}")
        return "Прости, я немного задумалась. Попробуй еще раз!"

@app.route('/webhook', methods=['GET'])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Hello World", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if data.get("object") == "instagram":
        for entry in data.get("entry", []):
            for m in entry.get("messaging", []):
                if m.get("message"):
                    sid = m["sender"]["id"]
                    txt = m["message"].get("text")
                    if txt:
                        send_instagram_message(sid, ask_gpt(sid, txt))
    return "EVENT_RECEIVED", 200

@app.route('/telegram', methods=['POST'])
def telegram_webhook():
    data = request.get_json()
    if "message" in data:
        cid = data["message"]["chat"]["id"]
        txt = data["message"].get("text")
        if txt:
            send_telegram_message(cid, ask_gpt(cid, txt))
    return "OK", 200

def send_instagram_message(recipient_id, text):
    url = f"https://graph.facebook.com/v19.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    requests.post(url, json={"recipient": {"id": recipient_id}, "message": {"text": text}})

def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text})
