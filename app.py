import os
import logging
import multiprocessing
import asyncio
import time
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
BOT_TOKEN = "8957265857:AAG2ZXZ-AWvMrjGmUZFfr-SP-cjcQKVLra4"  # твой токен
APP_SHORT_NAME = "viewer4"   # имя приложения в BotFather
APP_URL = "https://nova3dview.netlify.app"   # твой сайт

# R2 (из переменных окружения Render)
R2_ACCESS_KEY = os.environ.get("R2_ACCESS_KEY")
R2_SECRET_KEY = os.environ.get("R2_SECRET_KEY")
R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME", "nova-models")
R2_PUBLIC_URL = os.environ.get("R2_PUBLIC_URL")
R2_ENDPOINT = os.environ.get("R2_ENDPOINT")

if not all([R2_ACCESS_KEY, R2_SECRET_KEY, R2_PUBLIC_URL, R2_ENDPOINT]):
    raise ValueError("❌ Не все переменные для R2 заданы!")

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
        await update.message.reply_text("❌ Отправьте файл.")
        return

    doc = update.message.document
    file_name = doc.file_name

    if not file_name.lower().endswith('.glb'):
        await update.message.reply_text("❌ Только .glb файлы.")
        return

    status_msg = await update.message.reply_text(f"⏳ Загружаю {file_name}...")

    try:
        new_file = await doc.get_file()
        file_data = await new_file.download_as_bytearray()

        s3_client.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=file_name,
            Body=file_data,
            ContentType='model/gltf-binary'
        )
        logger.info(f"Файл {file_name} загружен в R2")

        model_name = file_name[:-4]  # убираем .glb
        encoded = quote(model_name)
        cache = int(time.time())

        tg_link = f"https://t.me/Nova3DViewerProBot/{APP_SHORT_NAME}?startapp=model={encoded}&v={cache}"
        browser_link = f"{APP_URL}/?model={encoded}&v={cache}"

        await status_msg.edit_text(
            f"✅ Файл **{file_name}** загружен!\n\n"
            f"🔗 **Telegram:**\n{tg_link}\n\n"
            f"🌐 **Браузер:**\n{browser_link}"
        )

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Отправь .glb файл, получу ссылки."
    )

# ================== ЗАПУСК БОТА ==================
def run_bot():
    bot = Bot(token=BOT_TOKEN)
    try:
        asyncio.run(bot.delete_webhook(drop_pending_updates=True))
        logger.info("✅ Вебхук удалён.")
    except Exception as e:
        logger.warning(f"⚠️ {e}")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    logger.info("🚀 Бот запущен.")
    app.run_polling()

# ================== FLASK ==================
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "✅ Bot is running!"

@flask_app.route('/health')
def health():
    return "OK"

# ================== ТОЧКА ВХОДА ==================
if __name__ == '__main__':
    proc = multiprocessing.Process(target=run_bot)
    proc.daemon = True
    proc.start()
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host='0.0.0.0', port=port)
