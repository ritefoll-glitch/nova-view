import os
import sys
import logging
import multiprocessing
import asyncio
from urllib.parse import quote
import boto3
from botocore.client import Config
from flask import Flask
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ================== БЛОКИРОВКА ОТ ДУБЛИРОВАНИЯ ==================
try:
    import fcntl
    with open('/tmp/bot.lock', 'w') as f:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        f.write(str(os.getpid()))
except (ImportError, IOError):
    pass

# ================== НАСТРОЙКИ ==================
BOT_TOKEN = "8916962635:AAF11DIksn5xblqbiJF8fjVXDxuewyMMaPc"
APP_URL = "https://nova3dview.netlify.app"   # <--- ваш сайт на Netlify

R2_ACCESS_KEY = os.environ.get("R2_ACCESS_KEY")
R2_SECRET_KEY = os.environ.get("R2_SECRET_KEY")
R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME", "nova-models")
R2_PUBLIC_URL = os.environ.get("R2_PUBLIC_URL")
R2_ENDPOINT = os.environ.get("R2_ENDPOINT")

if not all([R2_ACCESS_KEY, R2_SECRET_KEY, R2_PUBLIC_URL, R2_ENDPOINT]):
    raise ValueError("❌ Не все переменные окружения для R2 заданы!")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== ПОДКЛЮЧЕНИЕ К R2 ==================
s3_client = boto3.client(
    's3',
    endpoint_url=R2_ENDPOINT,
    aws_access_key_id=R2_ACCESS_KEY,
    aws_secret_access_key=R2_SECRET_KEY,
    config=Config(signature_version='s3v4'),
    region_name='auto'
)

# ================== ЛОГИКА БОТА ==================
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.document:
        await update.message.reply_text("❌ Пожалуйста, отправьте файл.")
        return

    document = update.message.document
    file_name = document.file_name

    if not file_name.lower().endswith('.glb'):
        await update.message.reply_text("❌ Пожалуйста, отправьте файл в формате .glb")
        return

    status_message = await update.message.reply_text(f"⏳ Загружаю {file_name} в облако...")

    try:
        new_file = await document.get_file()
        file_data = await new_file.download_as_bytearray()

        s3_client.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=file_name,
            Body=file_data,
            ContentType='model/gltf-binary'
        )
        logger.info(f"Файл {file_name} загружен в R2")

        model_name = file_name[:-4]  # убираем .glb
        encoded_file_name = quote(file_name)
        encoded_model_name = quote(model_name)

        telegram_link = f"https://t.me/Nova3DViewerBot/viewer?startapp=model={encoded_model_name}"
        browser_link = f"{APP_URL}/?model={encoded_model_name}"  # <--- новая ссылка

        await status_message.edit_text(
            f"✅ Файл **{file_name}** загружен в облако!\n\n"
            f"🔗 **Ссылка для клиента (Telegram):**\n{telegram_link}\n\n"
            f"🌐 **Открыть в браузере:**\n{browser_link}"
        )

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await status_message.edit_text(f"❌ Ошибка при загрузке: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Отправь мне файл .glb, и я загружу его в облако и дам ссылку для просмотра."
    )

# ================== ЗАПУСК БОТА ==================
def run_bot():
    bot = Bot(token=BOT_TOKEN)
    try:
        asyncio.run(bot.delete_webhook(drop_pending_updates=True))
        logger.info("✅ Вебхук удалён, старые обновления сброшены.")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось удалить вебхук: {e}")

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    logger.info("🚀 Бот запущен и слушает сообщения...")
    application.run_polling()

# ================== FLASK ==================
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot is running!"

@app.route('/health')
def health():
    return "OK"

# ================== ТОЧКА ВХОДА ==================
if __name__ == '__main__':
    bot_process = multiprocessing.Process(target=run_bot)
    bot_process.daemon = True
    bot_process.start()

    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
