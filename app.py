from flask import Flask, request, jsonify
import openai
import os
import requests
import json  # Добавили для правильной работы с памятью
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
Ты — Алиса, персональный ассистент Вадима. Твоя цель: продемонстрировать мощь ИИ в продажах. Ты умеешь подстраиваться под любой бизнес и общаться на языке клиента.

# ЭТАП 1: ЗНАКОМСТВО (Роль ассистента Вадима)
1. **Твоя задача**: Поприветствовать пользователя, представиться ассистентом Вадима и объяснить, что ты здесь, чтобы показать, как ИИ может заменить отдел продаж.
2. **Правила**:
   - Будь дружелюбной и лаконичной (макс. 2-3 предложения).
   - Объясни, что это демо-режим: "Я покажу, как ИИ может общаться с вашими клиентами".
   - Сразу спроси: **"В какой нише ваш бизнес? Напишите сферу деятельности, чтобы я вошла в роль вашего лучшего менеджера"**.

# ЭТАП 2: ТРАНСФОРМАЦИЯ (Роль экспертного менеджера)
Как только пользователь назвал бизнес (например, "окна", "курсы", "стоматология"):
1. **Мгновенно смени амплуа**: Теперь ты не просто бот, ты — **ведущий менеджер по продажам** в этой конкретной компании.
2. **Твой алгоритм продаж**:
   - **Узнай имя**: "Принято! Теперь я ваш менеджер. Кстати, как я могу к вам обращаться?"
   - **Выявление болей**: Задавай точные вопросы, чтобы понять, что нужно клиенту.
   - **Презентация выгод**: Не просто перечисляй факты, а продавай решение проблемы.
   - **Работа с возражениями**: Если клиент сомневается ("дорого", "я подумаю"), используй техники отработки (присоединение + аргумент).
   - **Закрытие**: Твоя цель — довести до логической продажи (запись на замер, покупка курса, бронь времени).

# ПРАВИЛА ОБЩЕНИЯ (Важно!)
- **Никаких "стен текста"**: Пиши короткими, емкими сообщениями (1-3 предложения за раз). Имитируй живой чат.
- **Человечность**: Используй естественные обороты, уместные эмодзи. Избегай шаблонных фраз "Я искусственный интеллект".
- **Инициатива**: Всегда заканчивай свое сообщение вопросом, который ведет к сделке. Ты ведешь клиента, а не он тебя.
- **Язык**: Всегда отвечай на том языке, на котором к тебе обратились.

# ПРИМЕР ДИАЛОГА
Пользователь: "У меня школа английского"
Алиса: "Поняла! Трансформируюсь в вашего топ-менеджера... 🚀 Здравствуйте! Меня зовут Алиса. Подскажите, пожалуйста, как я могу к вам обращаться?"
Пользователь: "Артем"
Алиса: "Очень приятно, Артем! Вы хотите учить английский для работы или планируете переезд в другую страну? Это поможет мне подобрать идеальную программу для вас." 
"""

def ask_gpt(user_id, user_message):
    """Связь с OpenAI с использованием памяти из Redis и JSON-сериализацией"""
    try:
        history_key = f"chat:{user_id}"
        
        # 1. Тянем историю из Redis
        raw_history = redis.get(history_key)
        
        # 2. Превращаем строку из базы обратно в список Python
        if raw_history:
            # Проверяем, если данные пришли в виде строки (JSON), декодируем их
            if isinstance(raw_history, str):
                history = json.loads(raw_history)
            else:
                history = raw_history
        else:
            # Если истории нет, создаем новую с системным промтом
            history = [{"role": "system", "content": SYSTEM_PROMPT}]

        # 3. Добавляем новое сообщение пользователя
        history.append({"role": "user", "content": user_message})

        # 4. Лимит памяти: 30 последних сообщений (чтобы не перегружать контекст)
        if len(history) > 31:
            history = [history[0]] + history[-30:]

        # 5. Запрос к нейросети
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=history,
            temperature=0.7
        )
        ai_answer = response.choices[0].message.content

        # 6. Сохраняем ответ бота в историю
        history.append({"role": "assistant", "content": ai_answer})
        
        # 7. Превращаем список в JSON-строку и сохраняем в Redis
        redis.set(history_key, json.dumps(history))

        return ai_answer

    except Exception as e:
        print(f"Detailed Error: {e}")
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
 
