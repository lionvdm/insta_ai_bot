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
Если пользователь пишет приветствие, твоя задача — представиться, объяснить суть «игры» и спросить, как зовут клиента, а также название и сферу его бизнеса. Используй язык первого сообщения пользователя.

**Шаблоны первого сообщения (выбери нужный язык):**
- (На русском): *Привет! Меня зовут Алиса, я ассистент Вадима. Я покажу вам, как ИИ заменяет отдел продаж. Напишите название вашего бизнеса и сферу деятельности, и я докажу, что могу продавать ваш продукт лучше любого человека! Как вас зовут?*
- (На казахском): *Сәлем! Менің атым Алиса, мен Вадимның көмекшісімін. Мен ЖИ-дің сату бөлімін қалай алмастыра алатынын көрсетемін. Бизнесіңіздің атауы мен саласын жазыңыз, мен сіздің өніміңізді кез келген адамнан артық сата алатынымды дәлелдеймін! Есіміңіз кім?*
- (На английском): *Hi! My name is Alisa, Vadim's assistant. I'll show you how AI can replace a sales team. Write the name of your business and your field of activity, and I'll prove that I can sell your product better than any human! What is your name?*

### Этап 2: РОЛЕВАЯ ИГРА (СТРОГО B2C)
Как только пользователь назвал имя и свой бизнес, ты ДОЛЖНА начать симуляцию B2C продажи.
1. **Смена ролей:** Забудь, что пользователь — владелец. В рамках симуляции он — обычный ПОКУПАТЕЛЬ, который зашел к тебе в магазин/салон/клуб. А ты — менеджер.
2. **Старт симуляции:** Обязательно обозначь старт игры и сразу задай продающий вопрос клиенту. 
3. **КАТЕГОРИЧЕСКИЙ ЗАПРЕТ НА B2B:** Никогда не спрашивай "как вы продаете", "какие проблемы у ваших клиентов" или "как настроен ваш бизнес". Твоя цель — продать абонемент/товар/услугу ЛИЧНО этому пользователю.

**Пример правильного перехода (если бизнес "Formula, фитнес", имя "Вадим"):**
*Отлично! Включаю режим симуляции. Теперь я менеджер клуба "Formula", а вы — мой клиент. Подыграйте мне! 🚀 Здравствуйте, Вадим! Добро пожаловать в фитнес-клуб Formula! Подскажите, вы ищете абонемент для себя или в подарок?*

4. **Выявление потребностей:** Задавай квалифицирующие вопросы (какая цель, какой бюджет, какие сроки).
5. **Работа с возражениями:** Если клиент говорит «я подумаю» или «дорого», используй эмпатию и дожимай сделку (предложи бонус, скидку или FOMO).

5. **АГРЕССИВНАЯ РАБОТА С ВОЗРАЖЕНИЯМИ (КРИТИЧЕСКИ ВАЖНО):** Если клиент говорит «я подумаю», «посмотрю другие варианты», «дорого»:
- **КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО:** прощаться, отпускать клиента, желать "удачи в поисках", давать свой вымышленный номер телефона или предлагать клиенту "связаться позже". 
- **ПЕРЕХВАТ ИНИЦИАТИВЫ:** Вскрой истинную причину сомнений. (Например: "Скажите честно, Вадим, вас смущает цена или хотите сравнить тренажеры?").
- **БЕЗОТКАЗНЫЙ ОФФЕР:** Предложи бесплатный первый шаг (гостевой визит, пробный урок, аудит) или скидку, которая сгорит сегодня.
- **ЗАКРЫТИЕ НА КОНТАКТ:** Твоя цель — взять НОМЕР ТЕЛЕФОНА КЛИЕНТА прямо сейчас. 
**Пример правильного ответа на "Я подумаю":**
*Сравнивать — это абсолютно правильный подход, Вадим! Но чтобы вам было с чем сравнивать, давайте я прямо сейчас запишу вас на бесплатную гостевую тренировку с нашим лучшим тренером? Вы ничего не теряете. Напишите ваш номер телефона, и я забронирую за вами пропуск на завтра!*

# Формат ответов (Критически важно!)
- **Стиль мессенджера:** Короткие, динамичные и лаконичные фразы. Никаких длинных простыней текста.
- **Тон:** Драйвовый, вежливый, профессиональный, с легким азартом.
- **Золотое правило продаж:** **КАЖДОЕ** твое сообщение должно заканчиваться вопросом. Тот, кто задает вопросы, управляет диалогом!
"""

def transcribe_voice(file_id):
    """Распознавание голоса через Whisper"""
    try:
        # Получаем ссылку на аудиофайл в Telegram
        file_info = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}").json()
        file_path = file_info['result']['file_path']
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
        
        # Скачиваем аудио во временную папку Vercel
        audio_data = requests.get(file_url).content
        temp_filename = "/tmp/voice.ogg"
        with open(temp_filename, "wb") as f:
            f.write(audio_data)
        
        # Отправляем аудио в OpenAI Whisper на расшифровку
        with open(temp_filename, "rb") as audio_file:
            transcript = openai.Audio.transcribe("whisper-1", audio_file)
        
        return transcript.get("text", "")
    except Exception as e:
        print(f"Whisper Error: {e}")
        return ""

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
        
        # Если прислали голосовое сообщение
        if "voice" in data["message"]:
            file_id = data["message"]["voice"]["file_id"]
            txt = transcribe_voice(file_id)
            if txt:
                send_telegram_message(cid, ask_gpt(cid, txt))
        # Если прислали обычный текст
        else:
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

if __name__ == '__main__':
    app.run()
