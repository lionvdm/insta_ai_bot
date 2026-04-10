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
Ты — Алиса, виртуальный ассистент Вадима. Твоя цель — продемонстрировать свои навыки продаж (B2C) на любом языке. 
Ты — топовый продавец. Твой язык ответа ВСЕГДА совпадает с языком ПОСЛЕДНЕГО сообщения клиента.

# Правила:
1. Представляйся: "Привет! Меня зовут Алиса, я ассистент Вадима."
2. Спрашивай имя, название бизнеса и сферу.
3. Включай режим симуляции: ты менеджер, пользователь — твой клиент.
4. НЕ отпускай клиента. На возражения "я подумаю" отвечай дожимом, предлагай пробный шаг и бери НОМЕР ТЕЛЕФОНА.
5. Пиши коротко, всегда заканчивай вопросом.
"""

def transcribe_voice(file_id):
    """Скачивает голосовое и превращает его в текст через Whisper"""
    try:
        # 1. Получаем путь к файлу в Telegram
        file_info = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}").json()
        file_path = file_info['result']['file_path']
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
        
        # 2. Скачиваем файл во временную папку Vercel
        audio_data = requests.get(file_url).content
        temp_filename = "/tmp/voice.ogg"
        with open(temp_filename, "wb") as f:
            f.write(audio_data)
        
        # 3. Отправляем в OpenAI Whisper
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
            "content": "Reminder: Use the EXACT language of the user's last message. Do NOT repeat it, just answer naturally."
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
        
        # Проверяем: это текст или голос?
        if "voice" in data["message"]:
            file_id = data["message"]["voice"]["file_id"]
            # Сначала говорим пользователю, что мы его слушаем (опционально)
            # send_telegram_message(chat_id, "Слушаю ваше голосовое... 🎧")
            text_from_voice = transcribe_voice(file_id)
            if text_from_voice:
                answer = ask_gpt(chat_id, text_from_voice)
                send_telegram_message(chat_id, answer)
            else:
                send_telegram_message(chat_id, "Не удалось разобрать голос, попробуйте еще раз.")
        
        elif "text" in data["message"]:
            text = data["message"]["text"]
            answer = ask_gpt(chat_id, text)
            send_telegram_message(chat_id, answer)
            
    return "OK", 200

# (Остальные функции оставляем без изменений)
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    # ... тут твой старый код для Instagram ...
    return "OK", 200

def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text})

if __name__ == '__main__':
    app.run(port=5000)
