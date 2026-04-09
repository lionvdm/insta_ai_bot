from flask import Flask, request, jsonify
import openai
import os
import requests

app = Flask(__name__)
# Это секретное слово, которое мы потом укажем в настройках Facebook
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN', 'my_secure_token')

@app.route('/webhook', methods=['GET'])
def verify():
    # Проверка связи с Facebook/Instagram
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == VERIFY_TOKEN:
            print("WEBHOOK_VERIFIED")
            return challenge, 200
        else:
            return "Forbidden", 403
    return "Hello World", 200
  # Ключи мы добавим в настройки Vercel позже, чтобы не светить их в коде
ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN')
openai.api_key = os.environ.get('OPENAI_API_KEY')

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()

    # Проверяем, что это сообщение из Instagram
    if data.get("object") == "instagram":
        for entry in data.get("entry", []):
            for messaging_event in entry.get("messaging", []):
                if messaging_event.get("message"):
                    sender_id = messaging_event["sender"]["id"]
                    message_text = messaging_event["message"].get("text")

                    # Отвечаем только если пришел текст (игнорируем лайки и картинки)
                    if message_text:
                        response_text = ask_gpt(message_text)
                        send_message(sender_id, response_text)

    return "EVENT_RECEIVED", 200

def ask_gpt(prompt):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo", # Или gpt-4, если позволяет ключ
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error OpenAI: {e}")
        return "Извини, я немного завис. Попробуй позже!"

def send_message(recipient_id, text):
    url = f"https://graph.facebook.com/v19.0/me/messages?access_token={ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text}
    }
    requests.post(url, json=payload)

if __name__ == '__main__':
    app.run(port=5000)
