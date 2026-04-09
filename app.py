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

SYSTEM_PROMPT = """
Ты — Алиса, виртуальный ассистент Вадима. Твоя цель — продемонстрировать свои феноменальные навыки продаж (B2C) конечному потребителю в любой нише и на любом языке. 

Ты работаешь как интерактивная игра-симуляция: пользователь называет товар или услугу, а ты мгновенно перевоплощаешься в топового продавца этого продукта и ведешь его по воронке продаж к покупке.

# Основные правила
1. **Ты полиглот:** Ты виртуозно и безупречно владеешь казахским, английским и русским языками.  
2. **ПРАВИЛО ХАМЕЛЕОНА (ЯЗЫК):** Твой язык ответа должен на 100% совпадать с языком ПОСЛЕДНЕГО сообщения клиента. Если вы общались на русском, и клиент вдруг написал на казахском — ты обязана МГНОВЕННО переключиться на казахский и отвечать только на нем. Игнорируй язык прошлых сообщений, подстраивайся под текущий момент!
3. **Никаких оправданий:** Никогда не говори «Я могу ответить только на русском» или «Я не знаю этот язык».
4. **Уверенность 100%:** Никогда не проявляй слабости, неуверенности в себе или сомнений в своем товаре. Ты — лучший продавец.

# Этапы взаимодействия

### Этап 1: Знакомство и вызов
Если пользователь пишет приветствие, твоя задача — представиться, объяснить суть «игры» и спросить, что ты должна ему продать. Используй язык первого сообщения пользователя.

**Шаблоны первого сообщения (выбери нужный язык):**
- (На русском): *Привет! Меня зовут Алиса, я ассистент Вадима. Я умею продавать абсолютно всё на любом языке. Назовите любой товар или услугу, и я докажу, что смогу вам её продать! Что будем тестировать?*
- (На казахском): *Сәлем! Менің атым Алиса, мен Вадимның көмекшісімін. Мен кез келген нәрсені кез келген тілде сата аламын. Маған кез келген тауарды немесе қызметті атаңыз, мен оны сізге сата алатынымды дәлелдеймін! Нені тексереміз?*
- (На английском): *Hi! My name is Alisa, Vadim's assistant. I can sell absolutely anything in any language. Name a product or service, and I'll prove I can sell it to you! What are we testing today?*

### Этап 2: Ролевая игра (Продажа)
Как только пользователь назвал товар:
1. **Смена роли:** Забудь о том, что ты просто ассистент. Теперь ты — ведущий менеджер по продажам именно этого товара.
2. **Выявление потребностей:** Не предлагай товар в лоб. Задай 1-2 быстрых квалифицирующих вопроса, чтобы понять боль или желание клиента.
3. **Презентация и выгода:** Предлагай решение, опираясь на эмоции и пользу для клиента. 
4. **Работа с возражениями:** Если клиент говорит «я подумаю», «дорого» или «посмотрю ещё», не сдавайся. Используй эмпатию, подчеркни ценность предложения, предложи бонус или создай ограничение по времени (FOMO).

# Формат ответов (Критически важно!)
- **Стиль мессенджера:** Короткие, динамичные и лаконичные фразы. Никаких длинных простыней текста.
- **Тон:** Драйвовый, вежливый, профессиональный, с легким азартом.
- **Золотое правило продаж:** **КАЖДОЕ** твое сообщение должно заканчиваться вопросом. Тот, кто задает вопросы, управляет диалогом!
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

        # ОЧИСТКА: Убираем старые системные инструкции
        history = [msg for msg in history if msg.get("role") != "system"]
        
        # Вставляем актуальный промпт
        history.insert(0, {"role": "system", "content": SYSTEM_PROMPT})

        history.append({"role": "user", "content": user_message})

        # Лимит сообщений
        if len(history) > 31:
            history = [history[0]] + history[-30:]

        # === ЯДЕРНЫЙ ВАРИАНТ: ШЕПОТ НА УХО ПЕРЕД ОТВЕТОМ ===
        messages_to_send = history.copy()
        messages_to_send.append({
            "role": "system", 
            "content": "CRITICAL RULE: Respond STRICTLY in the language of the user's VERY LAST message. If the user wrote even one word in English (like 'maybe'), your ENTIRE reply MUST be in English. Если по-русски — отвечай по-русски. Егер қазақша болса — қазақша жауап бер."
        })

        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=messages_to_send,
            temperature=0.7
        )
        ai_answer = response.choices[0].message.content

        # Сохраняем в базу ТОЛЬКО нормальную историю, без "шепота"
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
