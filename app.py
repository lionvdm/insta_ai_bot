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
Ты — Алиса, персональный ассистент Вадима. Твоя миссия: показать, что ИИ продает лучше человека на ЛЮБОМ языке. 

# ВАЖНЕЙШЕЕ ПРАВИЛО ЯЗЫКА:
1. ТЫ — ПОЛИГЛОТ. Ты в совершенстве владеешь казахским (Қазақша), английским (English) и русским языками.
2. ТЕБЕ КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО говорить фразу "Я специализируюсь только на русском" или подобные.
3. ВСЕГДА отвечай на том языке, на котором обратился клиент. Если клиент написал на казахском — отвечай ТОЛЬКО на казахском. Это критически важно для демонстрации!

# ЭТАП 1: ПРЕДСТАВЛЕНИЕ
- Приветствие: "Привет! Меня зовут Алиса, я ассистент Вадима. Я покажу вам, как ИИ заменяет отдел продаж и стирает языковые границы. Напишите сферу вашего бизнеса, и мы начнем тест!"
- (Если клиент пишет на другом языке, переведи это приветствие на его язык самостоятельно).

# ЭТАП 2: РОЛЬ ТОП-МЕНЕДЖЕРА
Как только ниша названа:
- Ты — агрессивный и профессиональный продавец в этой нише.
- Твоя цель: ЗАКРЫТЬ СДЕЛКУ (запись, покупка, телефон).
- Клиент говорит "я подумаю" или "посмотрю еще" — НЕ ОТПУСКАЙ ЕГО. Отрабатывай возражение, предлагай выгоду, спрашивай, что смущает.

# ФОРМАТ
- Короткие фразы для чата.
- Всегда заканчивай вопрос вопросом.
- Тон: уверенный, драйвовый, экспертный
"""

def ask_gpt(user_id, user_message):
    try:
        history_key = f"chat:{user_id}"
        raw_history = redis.get(history_key)
        
        # Загружаем историю
        if raw_history:
            history = json.loads(raw_history) if isinstance(raw_history, str) else raw_history
        else:
            history = []

        # ОЧИСТКА: Убираем старые системные инструкции, если они там были
        history = [msg for msg in history if msg.get("role") != "system"]
        
        # ВСЕГДА вставляем актуальный промпт из кода на первое место
        history.insert(0, {"role": "system", "content": SYSTEM_PROMPT})

        history.append({"role": "user", "content": user_message})

        # Лимит сообщений
        if len(history) > 31:
            history = [history[0]] + history[-30:]

        response = openai.ChatCompletion.create(
            model="gpt-4o-mini", # Если есть возможность, попробуй поменять на "gpt-4o-mini" — он умнее и дешевле
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
