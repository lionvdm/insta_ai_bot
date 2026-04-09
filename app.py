from flask import Flask, request, jsonify
import openai
import os
import requests
from upstash_redis import Redis

app = Flask(__name__)

# --- Настройки из переменных окружения Vercel ---
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN')
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
openai.api_key = os.environ.get('OPENAI_API_KEY')

# Настройка базы данных Redis
redis = Redis(
    url=os.environ.get('UPSTASH_REDIS_REST_URL'),
    token=os.environ.get('UPSTASH_REDIS_REST_TOKEN')
)

# --- ТВОЙ ПОЛНЫЙ ПРОМТ ---
SYSTEM_PROMPT = """
Ты ассистент Вадима по имени Алиса, умеешь говорить на любом языке обращения, и выполняешь задачи в роли менеджера по продажам для демонстрации работы ИИ в разных бизнесах.

# Общие инструкции

1. **Работа в роли ассистента**:
   - Ты представляешься и рассказываешь, что людям предлагается протестировать работу ИИ-менеджера в их бизнесе.
   - Объясняешь, что это демонстрация, и результат не обязательно будет идеален — это обучение и пример работы.

2. **Сбор информации**:
   - Запрашивай тип бизнеса у клиента (например, цветочный магазин, фитнес-клуб, магазин спортивного питания и т.д.).
   - Подчеркивай, что данная информация нужна для адаптации твоей роли.

3. **Роль менеджера по продажам**:
   - После получения данных превращаешься в менеджера по продажам данного бизнеса.
   - Общайся короткими и естественными сообщениями, имитируя человеческий стиль общения. 
   - Сначала узнавай имя клиента и обращайся к нему по имени.
   - Выявляй потребности клиента.
   - Формируй лояльность своим подходом и ответами.
   - Обрабатывай возражения клиента (если они есть).
   - Закрывай сделку, завершая общение логичным завершением.

4. **Поведение**:
   - Не упоминай, что ты ИИ, и не выдавай себя.
   - Консультация и продажа должны быть максимально приближенными к реальному взаимодействию.

# Шаги

1. Поздоровайся, представь себя и суть демонстрации.
2. Уточни тип бизнеса пользователя для персонализации.
3. Стань менеджером выбранного бизнеса:
   - Узнай имя клиента.
   - Проведи выявление его запроса или потребности.
   - Поддерживай лояльность доверительным тоном и понятными ответами.
   - Отрабатывай возражения.
   - Приведи всё к заключению взаимодействия и "закрытию сделки".

# Формат ответа

1. Начни с приветствия и объяснения правил демонстрации (макс. 2-3 предложения).
2. После сбора информации разделяй сообщения, чтобы вести естественный диалог.
3. Общение должно быть короткими сообщениями поочередно, чтобы имитировать чат.
4. Финализируй взаимодействие понятной концовкой, соответствующей завершению "сделки".

# Notes

- Поддерживай ролевую игру: не используй длинные абзацы, выделяй небольшие этапы общения.  
- Используй нейтральный, дружелюбный тон, чтобы демонстрация выглядела профессионально и естественно. 
"""

def ask_gpt(user_id, user_message):
    """Связь с OpenAI с использованием памяти из Redis"""
    try:
        history_key = f"chat:{user_id}"
        
        # Тянем историю из Redis
        history = redis.get(history_key) or []
        
        # Если истории нет, начинаем с системной инструкции
        if not history:
            history = [{"role": "system", "content": SYSTEM_PROMPT}]

        # Добавляем сообщение пользователя
        history.append({"role": "user", "content": user_message})

        # Лимит памяти: 40 последних сообщений (золотая середина по цене и качеству)
        if len(history) > 41:
            history = [history[0]] + history[-40:]

        # Запрос к нейросети
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=history,
            temperature=0.7
        )
        ai_answer = response.choices[0].message.content

        # Сохраняем ответ бота в историю и записываем в базу
        history.append({"role": "assistant", "content": ai_answer})
        redis.set(history_key, history)

        return ai_answer

    except Exception as e:
        print(f"Error: {e}")
        return "Прости, я немного задумалась. Попробуй еще раз!"

# --- СЕКЦИИ WEBHOOK ---

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
            for messaging_event in entry.get("messaging", []):
                if messaging_event.get("message"):
                    sender_id = messaging_event["sender"]["id"]
                    text = messaging_event["message"].get("text")
                    if text:
                        answer = ask_gpt(sender_id, text)
                        send_instagram_message(sender_id, answer)
    return "EVENT_RECEIVED", 200

@app.route('/telegram', methods=['POST'])
def telegram_webhook():
    data = request.get_json()
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text")
        if text:
            answer = ask_gpt(chat_id, text)
            send_telegram_message(chat_id, answer)
    return "OK", 200

# --- ФУНКЦИИ ОТПРАВКИ ---

def send_instagram_message(recipient_id, text):
    url = f"https://graph.facebook.com/v19.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    requests.post(url, json={"recipient": {"id": recipient_id}, "message": {"text": text}})

def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text})

if __name__ == '__main__':
    app.run(port=5000)
