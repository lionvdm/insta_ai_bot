from flask import Flask, request, jsonify
import openai
import os
import requests

app = Flask(__name__)

# Считываем настройки из переменных окружения Vercel
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN')
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN')
openai.api_key = os.environ.get('OPENAI_API_KEY')

@app.route('/webhook', methods=['GET'])
def verify():
    """Проверка связи с Meta (Instagram/Facebook)"""
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
    """Прием и обработка сообщений"""
    data = request.get_json()

    if data.get("object") == "instagram":
        for entry in data.get("entry", []):
            for messaging_event in entry.get("messaging", []):
                # Проверяем, что это именно сообщение
                if messaging_event.get("message"):
                    sender_id = messaging_event["sender"]["id"]
                    message_text = messaging_event["message"].get("text")

                    if message_text:
                        # 1. Спрашиваем у нейросети
                        ai_answer = ask_gpt(message_text)
                        # 2. Отправляем ответ пользователю
                        send_message(sender_id, ai_answer)

    return "EVENT_RECEIVED", 200

def ask_gpt(prompt):
    """Связь с OpenAI"""
    try:
        # Используем старый синтаксис для совместимости с простыми версиями библиотек
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"OpenAI Error: {e}")
        return "Прости, я немного задумался. Попробуй еще раз!"

def send_message(recipient_id, text):
    """Отправка ответа в Instagram через Graph API"""
    url = f"https://graph.facebook.com/v19.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text}
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Send Message Error: {e}")

if __name__ == '__main__':
    app.run(port=5000)
