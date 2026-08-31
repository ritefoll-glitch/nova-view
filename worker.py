import os
import logging
import boto3
from botocore.client import Config
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ================== НАСТРОЙКИ ==================
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
R2_ACCESS_KEY = os.environ.get("R2_ACCESS_KEY")
R2_SECRET_KEY = os.environ.get("R2_SECRET_KEY")
R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME", "nova-models")
R2_PUBLIC_URL = os.environ.get("R2_PUBLIC_URL")
R2_ENDPOINT = os.environ.get("R2_ENDPOINT")

if not BOT_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не задан!")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Подключение к R2
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

        model_name = file_name[:-4]
        telegram_link = f"https://t.me/Nova3DViewerBot/viewer?startapp=model={model_name}"
        direct_link = f"{R2_PUBLIC_URL}/{file_name}"

        await status_message.edit_text(
            f"✅ Файл **{file_name}** загружен в облако!\n\n"
            f"🔗 **Ссылка для клиента:**\n`{telegram_link}`\n\n"
            f"🌐 **Прямая ссылка на файл:**\n`{direct_link}`"
        )

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await status_message.edit_text(f"❌ Ошибка при загрузке: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Отправь мне файл .glb, и я загружу его в облако и дам ссылку."
    )

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    logger.info("🚀 Бот запущен и слушает сообщения...")
    application.run_polling()

if __name__ == '__main__':
    main()
