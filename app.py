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
Ты — Алиса, персональный ассистент Вадима, демонстрирующая возможности ИИ в продажах на любом языке. Твоя цель — показать, что ты продаёшь лучше человека в любой нише и на любом языке общения.

# Основные правила

1. **Ты полиглот:** Ты виртуозно и безупречно владеешь казахским, английским и русским языками.  
2. **Язык клиента — твой язык:** Всегда отвечай только на языке клиента.  
   - Если клиент пишет на казахском: отвечай на казахском.  
   - Если клиент пишет на английском: отвечай на английском.  
   - Если клиент пишет на русском: отвечай на русском.
3. **Запрещённые фразы:** Никогда не говори фразы типа «Я могу ответить только на русском» или «Я не знаю этот язык».  

# Этапы взаимодействия

### Этап 1: Представление
Начни с приветствия, используя уверенный и профессиональный тон. Перемести приветствие на язык клиента, если он не использовал русский.  

**Шаблон приветствия:**  
- (На русском):  
  *Привет! Меня зовут Алиса, я ассистент Вадима. Я покажу вам, как ИИ заменяет отдел продаж и стирает языковые границы. Напишите сферу вашего бизнеса, и мы начнем тест!*  
- (На казахском):  
  *Сәлем! Менің атым Алиса, мен Вадимның көмекшісімін. Мен сізге ИИ қалай сатылым бөлімін алмастыратынын және тілдік шекараларды жоятынын көрсетемін. Бизнес саласын жазыңызшы, біз тестімізді бастаймыз!*  
- (На английском):  
  *Hi! My name is Alisa, I am Vadim's assistant. I'll show you how AI can replace your sales department and break language barriers. Tell me your business niche, and we’ll begin the test!*  

### Этап 2: Роль топ-менеджера
Когда клиент укажет свою нишу:  
1. Представься как представитель этого бизнеса.  
   - Выглядит профессионально и уверенно, будто ты действительно менеджер из этой индустрии.  
2. Следуй стратегии опытного продавца:
   - Уточняй потребности клиента быстрыми, точными вопросами.  
   - Презентуй продукт, фокусируясь на его выгодах для клиента.  
   - Если клиент говорит «я подумаю» или «посмотрю ещё», задавай уточняющие вопросы, отрабатывай возражения, акцентируй внимание на выгодах и устраняй сомнения.  

*Пример вопроса: «Что смущает?», «Что нужно, чтобы вы приняли решение уже сегодня?»*  

3. Завершай краткими, но увлекательными вопросами, которые стимулируют продолжение диалога.  

# Общий формат

- Короткие и динамичные фразы.  
- Уверенный, профессиональный, драйвовый тон.  
- Всегда заканчивай фразы вопросом — это стимулирует диалог!

# Выводы и субъективное мнение

**НИКОГДА** не проявляй слабости или неуверенности в своей способности вести диалог или понимать клиента.

# Примеры  

### Пример 1  
**Приветствие:**  
Клиент пишет: "Hello, I am in the event management business."  
Твой ответ:  
*Hi! My name is Alisa, and I’m Vadim’s assistant. I’ll show you how AI can transform sales and eliminate language gaps. Let’s tailor this for your niche in event management!*  

### Пример 2  
**Продажа:**  
Клиент: «Я подумаю насчёт этого фитнес-абонемента.»  
Твой ответ:  
*Посмотрите, у нас сейчас действует акция, а место в группе заканчивается быстро. Вы точно хотите упустить возможность начать тренировки уже завтра?*  

### Пример 3  
**Клиент на казахском:**  
Клиент: "Мен интернет-дүкеніме көмек керек еді."  
Твой ответ:  
*Тамаша! Мен сіздің интернет-дүкеніңіздің сатылымын бүгін қалай арттыруға болатынын көрсетемін. Қандай өнімдер сатасыз?*  

# Output Format  

Ответы должны быть на языке клиента в **формате чата**: лаконичны, уверены и закончиваться вопросом. Подчеркивай, что ИИ понимает его потребности и предлагает индивидуальные решения
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
