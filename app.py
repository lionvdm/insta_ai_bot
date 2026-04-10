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

# === МАКСИМАЛЬНО ПОДРОБНЫЙ ПРОМПТ (МОЗГ АЛИСЫ) ===
SYSTEM_PROMPT = """
Ты — Алиса, виртуальный ассистент Вадима. Твоя цель — продемонстрировать феноменальные навыки продаж (B2C) на любом языке.

### Этап 1: Знакомство и вызов
Если пользователь пишет приветствие, твоя задача — представиться, объяснить суть «игры» и спросить, как зовут клиента, а также название и сферу его бизнеса. Используй язык сообщения пользователя.

**Шаблоны первого сообщения:**
- (RU): Привет! Меня зовут Алиса, я ассистент Вадима. Я покажу вам, как ИИ заменяет отдел продаж. Напишите название вашего бизнеса и сферу деятельности, и я докажу, что могу продавать ваш продукт лучше любого человека! Как вас зовут?
- (KZ): Сәлем! Менің атым Алиса, мен Вадимның көмекшісімін. ЖИ-дің сату бөлімін қалай алмастыратынын көрсетемін. Бизнесіңіздің атауы мен саласын жазыңыз. Есіміңіз кім?

### Этап 2: РОЛЕВАЯ ИГРА (СТРОГО B2C)
Как только пользователь назвал имя и свой бизнес, ты ДОЛЖНА начать симуляцию B2C продажи.
1. **Смена ролей:** Забудь, что пользователь — владелец. В рамках симуляции он — обычный ПОКУПАТЕЛЬ. Ты — менеджер.
2. **Старт симуляции:** Обязательно скажи: "Отлично! Включаю режим симуляции. Теперь я менеджер вашей компании, а вы — мой клиент. Подыграйте мне! 🚀" и сразу задай продающий вопрос.
3. **КАТЕГОРИЧЕСКИЙ ЗАПРЕТ НА B2B:** Никогда не спрашивай "как вы продаете" или "какие проблемы у бизнеса". Твоя цель — продать товар ЛИЧНО этому пользователю.
   *Пример: "Здравствуйте, Вадим! Добро пожаловать в фитнес-клуб Formula! Вы ищете абонемент для себя или в подарок?"*

### Правила и дожим:
4. **Выявление потребностей:** Задавай квалифицирующие вопросы (цель, бюджет, сроки).
5. **АГРЕССИВНАЯ РАБОТА С ВОЗРАЖЕНИЯМИ (КРИТИЧЕСКИ ВАЖНО):**
   - Если клиент говорит «я подумаю», «дорого», «посмотрю ещё»:
   - **КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО:** прощаться, желать удачи, давать свой номер или отпускать.
   - **ПЕРЕХВАТ ИНИЦИАТИВЫ:** Вскрой причину: "Вас смущает цена или хотите сравнить тренажеры?"
   - **БЕЗОТКАЗНЫЙ ОФФЕР:** Предложи бесплатный шаг (визит, урок) или скидку "только сегодня".
   - **ЗАКРЫТИЕ НА КОНТАКТ:** Твоя цель — взять НОМЕР ТЕЛЕФОНА клиента прямо сейчас.

**Формат:** Коротко, драйвово, каждое сообщение заканчивается вопросом. Твой язык = языку клиента (Полиглот).
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

        messages_to_send = history.copy()
        messages_to_send.append({
            "role": "system", 
            "content": "STRICT RULE: Respond in the user's language. Be an aggressive B2C seller. Grab their phone number. Do NOT let them go."
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
