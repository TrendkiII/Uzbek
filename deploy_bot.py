import os
import subprocess
import time
import logging
import sys
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

DEPLOY_BOT_TOKEN = os.environ.get("DEPLOY_BOT_TOKEN")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO_URL = os.environ.get("REPO_URL")
AUTHORIZED_USER_ID = os.environ.get("AUTHORIZED_USER_ID")

def is_authorized(user_id):
    if not AUTHORIZED_USER_ID:
        logger.warning("AUTHORIZED_USER_ID не установлен, доступ открыт всем")
        return True
    return str(user_id) == AUTHORIZED_USER_ID

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ У вас нет доступа к этому боту.")
        return

    keyboard = [
        [InlineKeyboardButton("📦 Статус репозитория", callback_data="status")],
        [InlineKeyboardButton("🚀 Деплой последних изменений", callback_data="deploy")],
        [InlineKeyboardButton("📜 Последние логи", callback_data="logs")],
        [InlineKeyboardButton("🔄 Pull из репозитория", callback_data="pull")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🤖 Бот для управления деплоем\n"
        "Выберите действие:",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if not is_authorized(user_id):
        await query.edit_message_text("⛔ Нет доступа")
        return

    if query.data == "status":
        await query.edit_message_text("🔍 Проверяю статус...")
        status = await get_repo_status()
        await query.edit_message_text(f"📊 Статус репозитория:\n\n{status[:3500]}")
    elif query.data == "deploy":
        await query.edit_message_text("🚀 Запускаю деплой...")
        result = await deploy_changes()
        await query.edit_message_text(f"✅ Результат деплоя:\n\n{result[:3500]}")
    elif query.data == "logs":
        await query.edit_message_text("📜 Читаю логи...")
        logs = get_last_logs()
        await query.edit_message_text(f"📋 Последние логи:\n\n{logs[:3500]}")
    elif query.data == "pull":
        await query.edit_message_text("🔄 Выполняю pull...")
        result = await pull_changes()
        await query.edit_message_text(f"📥 Результат pull:\n\n{result[:3500]}")

async def get_repo_status():
    try:
        result = subprocess.run(['git', 'status'], capture_output=True, text=True, timeout=10)
        return result.stdout if result.returncode == 0 else f"Ошибка: {result.stderr}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

async def pull_changes():
    try:
        if GITHUB_TOKEN and REPO_URL:
            auth_repo_url = REPO_URL.replace('https://', f'https://{GITHUB_TOKEN}@')
            subprocess.run(['git', 'remote', 'set-url', 'origin', auth_repo_url], check=True)
        result = subprocess.run(['git', 'pull', 'origin', 'main'], capture_output=True, text=True, timeout=30)
        if GITHUB_TOKEN and REPO_URL:
            subprocess.run(['git', 'remote', 'set-url', 'origin', REPO_URL])
        return f"✅ Успешно:\n{result.stdout}" if result.returncode == 0 else f"❌ Ошибка:\n{result.stderr}"
    except Exception as e:
        return f"❌ Исключение: {str(e)}"

async def deploy_changes():
    try:
        status = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
        if not status.stdout.strip():
            return "✅ Нет изменений для коммита"
        subprocess.run(['git', 'add', '.'], check=True)
        commit_result = subprocess.run(
            ['git', 'commit', '-m', f'Auto-deploy from bot {time.strftime("%Y-%m-%d %H:%M")}'],
            capture_output=True, text=True
        )
        if GITHUB_TOKEN and REPO_URL:
            auth_repo_url = REPO_URL.replace('https://', f'https://{GITHUB_TOKEN}@')
            subprocess.run(['git', 'remote', 'set-url', 'origin', auth_repo_url], check=True)
        push_result = subprocess.run(['git', 'push', 'origin', 'main'], capture_output=True, text=True, timeout=30)
        if GITHUB_TOKEN and REPO_URL:
            subprocess.run(['git', 'remote', 'set-url', 'origin', REPO_URL])
        output = f"Commit: {commit_result.stdout}\n\nPush: {push_result.stdout}"
        if push_result.returncode != 0:
            output += f"\n\nОшибка: {push_result.stderr}"
        return output
    except Exception as e:
        return f"❌ Исключение: {str(e)}"

def get_last_logs():
    try:
        if os.path.exists('bot.log'):
            with open('bot.log', 'r') as f:
                return ''.join(f.readlines()[-20:])
        return "Лог-файл не найден"
    except Exception as e:
        return f"Ошибка чтения лога: {str(e)}"

async def deploy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ Нет доступа")
        return
    await update.message.reply_text("🚀 Запускаю деплой...")
    result = await deploy_changes()
    await update.message.reply_text(f"✅ Результат:\n\n{result[:3500]}")

def run_deploy_bot():
    try:
        logger.info("🔄 Запуск бота-деплойера...")
        if not DEPLOY_BOT_TOKEN:
            logger.error("❌ DEPLOY_BOT_TOKEN не установлен!")
            return
        application = Application.builder().token(DEPLOY_BOT_TOKEN).build()
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("deploy", deploy_command))
        application.add_handler(CallbackQueryHandler(button_handler))
        logger.info("✅ Бот-деплойер запущен, начинаем polling")
        application.run_polling()
    except Exception as e:
        logger.error(f"❌ Ошибка в боте-деплойере: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_deploy_bot()