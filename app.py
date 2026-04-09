from flask import Flask, request, jsonify
import openai
import os
import requests

app = Flask(__name__)

# --- Настройки из переменных окружения Vercel ---
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN')
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
openai.api_key = os.environ.get('OPENAI_API_KEY')

# --- СЕКЦИЯ INSTAGRAM ---

@app.route('/webhook', methods=['GET'])
def verify():
    """Проверка связи с Meta"""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == VERIFY_TOKEN:
            return challenge, 200
        else:
            return "Forbidden", 403
    return "Hello World", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    """Прием сообщений из Instagram"""
    data = request.get_json()
    if data.get("object") == "instagram":
        for entry in data.get("entry", []):
            for messaging_event in entry.get("messaging", []):
                if messaging_event.get("message"):
                    sender_id = messaging_event["sender"]["id"]
                    message_text = messaging_event["message"].get("text")
                    if message_text:
                        ai_answer = ask_gpt(message_text)
                        send_instagram_message(sender_id, ai_answer)
    return "EVENT_RECEIVED", 200

# --- СЕКЦИЯ TELEGRAM ---

@app.route('/telegram', methods=['POST'])
def telegram_webhook():
    """Прием сообщений из Telegram"""
    data = request.get_json()
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text")
        if text:
            ai_answer = ask_gpt(text)
            send_telegram_message(chat_id, ai_answer)
    return "OK", 200

# --- ОБЩИЙ МОЗГ (OpenAI) ---

def ask_gpt(prompt):
    """Связь с OpenAI (одна для всех платформ)"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"OpenAI Error: {e}")
        return "Прости, я немного задумался. Попробуй еще раз!"

# --- ОТПРАВКА СООБЩЕНИЙ ---

def send_instagram_message(recipient_id, text):
    """Отправка в Instagram"""
    url = f"https://graph.facebook.com/v19.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {"recipient": {"id": recipient_id}, "message": {"text": text}}
    requests.post(url, json=payload)

def send_telegram_message(chat_id, text):
    """Отправка в Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)

if __name__ == '__main__':
    app.run(port=5000)
