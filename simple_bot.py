"""
simple_bot.py - Telegram бот для парсинга с поддержкой Claude Computer Use
"""

import os
import asyncio
import logging
import sys
from datetime import datetime
from typing import Dict, List, Optional

# Telegram бот
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Твои модули
from config import Config, logger
from database import Database, init_db
from brands import get_all_brands, get_brand_categories
from simple_parsers import parse_mercari, search_all, run_parser
from utils import format_number

# Claude Computer Use
try:
    from claude_controller import ClaudeComputerUse, ComputerUseTask
    CLAUDE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"⚠️ Claude модуль не загружен: {e}")
    CLAUDE_AVAILABLE = False

# ============================================
# КОНФИГУРАЦИЯ
# ============================================

# Загружаем конфиг
config = Config()

# Проверяем токен!
if not config.BOT_TOKEN:
    logger.critical("❌ КРИТИЧЕСКАЯ ОШИБКА: Токен бота не найден!")
    logger.critical("Проверь переменные окружения: BOT_TOKEN или TELEGRAM_BOT_TOKEN")
    sys.exit(1)

logger.info(f"✅ Токен бота: {config.BOT_TOKEN[:10]}...")

# ============================================
# ИНИЦИАЛИЗАЦИЯ
# ============================================

# Создаем бота и диспетчер
bot = Bot(token=config.BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ============================================
# ПРИНУДИТЕЛЬНОЕ УДАЛЕНИЕ ВЕБХУКА - ЭТО РЕШИТ ПРОБЛЕМУ!
# ============================================

async def force_delete_webhook():
    """Принудительно удаляет вебхук"""
    try:
        logger.info("🔍 Проверка наличия вебхука...")
        webhook_info = await bot.get_webhook_info()
        
        if webhook_info.url:
            logger.warning(f"⚠️ НАЙДЕН АКТИВНЫЙ ВЕБХУК: {webhook_info.url}")
            logger.warning("🔄 Принудительно удаляю вебхук...")
            
            result = await bot.delete_webhook(drop_pending_updates=True)
            if result:
                logger.info("✅ Вебхук успешно удален!")
            else:
                logger.error("❌ Не удалось удалить вебхук")
        else:
            logger.info("✅ Вебхуков нет, можно использовать polling")
            
        # Проверяем еще раз для уверенности
        webhook_info = await bot.get_webhook_info()
        if not webhook_info.url:
            logger.info("✅ Подтверждено: вебхуков нет")
        else:
            logger.error(f"❌ Вебхук все еще есть: {webhook_info.url}")
            
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке/удалении вебхука: {e}")

# ЗАПУСКАЕМ УДАЛЕНИЕ ВЕБХУКА (синхронно)
try:
    loop = asyncio.get_event_loop()
    loop.run_until_complete(force_delete_webhook())
except RuntimeError:
    # Если цикл событий уже запущен
    asyncio.create_task(force_delete_webhook())

# ============================================
# ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ И CLAUDE
# ============================================

# Инициализация базы данных
db = Database()

# Инициализация Claude (если доступно)
claude_cu = None
if config.CLAUDE_ENABLED and CLAUDE_AVAILABLE:
    try:
        claude_cu = ClaudeComputerUse(api_url=config.CLAUDE_API_URL)
        logger.info("✅ Claude Computer Use инициализирован")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации Claude: {e}")

# ============================================
# СОСТОЯНИЯ FSM
# ============================================

class ParserStates(StatesGroup):
    """Состояния для многошаговых диалогов"""
    waiting_for_platform = State()
    waiting_for_brand = State()
    waiting_for_search_query = State()
    waiting_for_price_min = State()
    waiting_for_price_max = State()
    waiting_for_claude_task = State()

# ============================================
# КЛАВИАТУРЫ
# ============================================

def get_main_keyboard():
    """Главное меню"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔍 Быстрый поиск", callback_data="quick_search")
    builder.button(text="🤖 Claude Computer Use", callback_data="claude_menu")
    builder.button(text="📊 Статистика", callback_data="stats")
    builder.button(text="⚙️ Настройки", callback_data="settings")
    builder.button(text="📋 Мои задачи", callback_data="my_tasks")
    builder.adjust(2)
    return builder.as_markup()

def get_platforms_keyboard():
    """Клавиатура с площадками"""
    builder = InlineKeyboardBuilder()
    
    for platform_id, platform_info in config.PLATFORMS.items():
        emoji = "🤖" if platform_info.get("use_claude") else "⚡"
        builder.button(
            text=f"{emoji} {platform_info['name']}",
            callback_data=f"platform_{platform_id}"
        )
    
    builder.button(text="◀️ Назад", callback_data="back_to_main")
    builder.adjust(2)
    return builder.as_markup()

def get_brands_keyboard():
    """Клавиатура с брендами"""
    brands = get_all_brands()
    builder = InlineKeyboardBuilder()
    
    for brand in brands[:20]:
        builder.button(text=brand, callback_data=f"brand_{brand}")
    
    builder.button(text="◀️ Назад", callback_data="back_to_platforms")
    builder.adjust(3)
    return builder.as_markup()

def get_claude_menu_keyboard():
    """Меню Claude"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🖱️ Запустить парсинг", callback_data="claude_start")
    builder.button(text="📋 Активные задачи", callback_data="claude_tasks")
    builder.button(text="◀️ Назад", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

# ============================================
# ОБРАБОТЧИКИ КОМАНД
# ============================================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    username = message.from_user.username or "Unknown"
    
    # Сохраняем пользователя
    await db.add_user(user_id, username)
    
    welcome_text = (
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "Я бот для парсинга площадок с б/у товарами.\n"
    )
    
    if claude_cu:
        welcome_text += "🤖 **Claude Computer Use активен!**\n\n"
    else:
        welcome_text += "⚠️ Claude отключен, работает только базовый парсинг.\n\n"
    
    welcome_text += "Выбери действие в меню:"
    
    await message.answer(
        welcome_text,
        reply_markup=get_main_keyboard()
    )

@dp.message(Command("help"))
async def cmd_help(message: Message):
    """Команда /help"""
    help_text = (
        "🔍 **Команды:**\n\n"
        "/start - Запустить бота\n"
        "/help - Эта справка\n"
        "/search <запрос> - Быстрый поиск\n"
        "/claude <запрос> - Поиск с Claude\n"
        "/stats - Статистика\n"
    )
    await message.answer(help_text)

@dp.message(Command("search"))
async def cmd_search(message: Message, state: FSMContext):
    """Быстрый поиск"""
    query = message.text.replace("/search", "").strip()
    
    if not query:
        await message.answer("Введи запрос после /search")
        return
    
    await state.update_data(search_query=query)
    await state.set_state(ParserStates.waiting_for_platform)
    
    await message.answer(
        f"🔍 Ищем: **{query}**\n\nВыбери площадку:",
        reply_markup=get_platforms_keyboard()
    )

@dp.message(Command("claude"))
async def cmd_claude(message: Message, state: FSMContext):
    """Запуск Claude"""
    if not claude_cu:
        await message.answer("❌ Claude Computer Use не доступен")
        return
    
    query = message.text.replace("/claude", "").strip()
    
    if not query:
        await message.answer("Введи запрос после /claude")
        return
    
    status_msg = await message.answer("🤖 Запускаю Claude...")
    
    try:
        task = ComputerUseTask(
            query=query,
            user_id=message.from_user.id,
            platforms=config.PLATFORMS
        )
        
        asyncio.create_task(run_claude_task(message.chat.id, task, status_msg.message_id))
        
    except Exception as e:
        logger.error(f"Ошибка Claude: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")

# ============================================
# CALLBACK ОБРАБОТЧИКИ
# ============================================

@dp.callback_query(lambda c: c.data == "quick_search")
async def callback_quick_search(callback: CallbackQuery, state: FSMContext):
    """Быстрый поиск"""
    await callback.answer()
    await state.set_state(ParserStates.waiting_for_search_query)
    await callback.message.edit_text(
        "Введи поисковый запрос:",
        reply_markup=InlineKeyboardBuilder().button(text="◀️ Назад", callback_data="back_to_main").as_markup()
    )

@dp.callback_query(lambda c: c.data == "claude_menu")
async def callback_claude_menu(callback: CallbackQuery):
    """Меню Claude"""
    await callback.answer()
    
    if not claude_cu:
        await callback.message.edit_text(
            "❌ Claude не доступен",
            reply_markup=InlineKeyboardBuilder().button(text="◀️ Назад", callback_data="back_to_main").as_markup()
        )
        return
    
    await callback.message.edit_text(
        "🤖 **Claude Computer Use**\n\nВыбери действие:",
        reply_markup=get_claude_menu_keyboard()
    )

@dp.callback_query(lambda c: c.data == "claude_start")
async def callback_claude_start(callback: CallbackQuery, state: FSMContext):
    """Запуск задачи Claude"""
    await callback.answer()
    await state.set_state(ParserStates.waiting_for_claude_task)
    await callback.message.edit_text(
        "🔍 Опиши задачу для Claude:",
        reply_markup=InlineKeyboardBuilder().button(text="◀️ Назад", callback_data="claude_menu").as_markup()
    )

@dp.callback_query(lambda c: c.data == "back_to_main")
async def callback_back_to_main(callback: CallbackQuery):
    """Назад в главное меню"""
    await callback.answer()
    await callback.message.edit_text(
        "Главное меню:",
        reply_markup=get_main_keyboard()
    )

@dp.callback_query(lambda c: c.data.startswith("platform_"))
async def callback_platform_selected(callback: CallbackQuery, state: FSMContext):
    """Выбор платформы"""
    platform_id = callback.data.replace("platform_", "")
    platform_info = config.PLATFORMS.get(platform_id)
    
    if not platform_info:
        await callback.answer("Платформа не найдена")
        return
    
    await state.update_data(platform=platform_id)
    
    data = await state.get_data()
    search_query = data.get("search_query")
    
    if search_query:
        await callback.answer()
        
        status_msg = await callback.message.edit_text(
            f"🔍 Ищу **{search_query}** на **{platform_info['name']}**..."
        )
        
        # Запускаем парсинг
        asyncio.create_task(run_parser_task(
            callback.message.chat.id,
            platform_id,
            search_query,
            status_msg.message_id
        ))
    else:
        await state.set_state(ParserStates.waiting_for_brand)
        await callback.message.edit_text(
            f"Выбрана платформа: **{platform_info['name']}**\n\nВыбери бренд:",
            reply_markup=get_brands_keyboard()
        )

@dp.callback_query(lambda c: c.data.startswith("brand_"))
async def callback_brand_selected(callback: CallbackQuery, state: FSMContext):
    """Выбор бренда"""
    brand = callback.data.replace("brand_", "")
    await state.update_data(brand=brand)
    
    await state.set_state(ParserStates.waiting_for_price_min)
    await callback.message.edit_text(
        f"Выбран бренд: **{brand}**\n\nВведи минимальную цену (0 если не важно):"
    )

# ============================================
# ОБРАБОТЧИКИ СООБЩЕНИЙ
# ============================================

@dp.message(ParserStates.waiting_for_search_query)
async def process_search_query(message: Message, state: FSMContext):
    """Обработка поискового запроса"""
    query = message.text.strip()
    
    if len(query) < 2:
        await message.answer("Слишком короткий запрос")
        return
    
    await state.update_data(search_query=query)
    await state.set_state(ParserStates.waiting_for_platform)
    
    await message.answer(
        f"🔍 Ищем: **{query}**\n\nВыбери площадку:",
        reply_markup=get_platforms_keyboard()
    )

@dp.message(ParserStates.waiting_for_claude_task)
async def process_claude_task(message: Message, state: FSMContext):
    """Обработка задачи Claude"""
    task_description = message.text.strip()
    
    if len(task_description) < 5:
        await message.answer("Слишком короткое описание")
        return
    
    status_msg = await message.answer("🤖 Передаю задачу Claude...")
    
    task = ComputerUseTask(
        query=task_description,
        user_id=message.from_user.id,
        platforms=config.PLATFORMS
    )
    
    asyncio.create_task(run_claude_task(message.chat.id, task, status_msg.message_id))
    await state.clear()

@dp.message(ParserStates.waiting_for_price_min)
async def process_price_min(message: Message, state: FSMContext):
    """Минимальная цена"""
    try:
        price_min = int(message.text.strip())
        await state.update_data(price_min=price_min)
        await state.set_state(ParserStates.waiting_for_price_max)
        await message.answer("Введи максимальную цену:")
    except ValueError:
        await message.answer("Введи число")

@dp.message(ParserStates.waiting_for_price_max)
async def process_price_max(message: Message, state: FSMContext):
    """Максимальная цена и запуск"""
    try:
        price_max = int(message.text.strip())
        await state.update_data(price_max=price_max)
        
        data = await state.get_data()
        platform = data.get("platform")
        brand = data.get("brand")
        search_query = data.get("search_query", brand)
        
        platform_info = config.PLATFORMS.get(platform, {})
        
        status_msg = await message.answer(
            f"🔍 Ищу **{search_query}** на **{platform_info.get('name', platform)}**..."
        )
        
        asyncio.create_task(run_parser_task(
            message.chat.id,
            platform,
            search_query,
            status_msg.message_id,
            data.get("price_min", 0),
            price_max
        ))
        
        await state.clear()
        
    except ValueError:
        await message.answer("Введи число")

# ============================================
# АСИНХРОННЫЕ ЗАДАЧИ
# ============================================

async def run_parser_task(chat_id: int, platform: str, query: str, status_msg_id: int, price_min: int = 0, price_max: int = 1000000):
    """Запуск парсера"""
    try:
        # Обновляем статус
        await bot.edit_message_text(
            f"🔍 Парсинг... Найдено: 0",
            chat_id=chat_id,
            message_id=status_msg_id
        )
        
        # Запускаем парсер
        results = await run_parser(platform, query, price_min, price_max, 20)
        
        # Сохраняем результаты
        saved = await db.save_items(results, platform, query)
        
        # Отчет
        report = (
            f"✅ **Парсинг завершен!**\n\n"
            f"📊 Найдено: {len(results)}\n"
            f"💾 Сохранено: {saved}\n\n"
        )
        
        if results:
            report += "**Товары:**\n"
            for i, item in enumerate(results[:3], 1):
                title = item.get('title', '?')
                price = item.get('price', '?')
                report += f"{i}. {title[:50]}... - {price}\n"
        
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="🔄 Новый поиск", callback_data="quick_search")
        
        await bot.edit_message_text(
            report,
            chat_id=chat_id,
            message_id=status_msg_id,
            reply_markup=keyboard.as_markup()
        )
        
    except Exception as e:
        logger.error(f"Ошибка парсинга: {e}")
        await bot.edit_message_text(
            f"❌ Ошибка: {str(e)[:100]}",
            chat_id=chat_id,
            message_id=status_msg_id
        )

async def run_claude_task(chat_id: int, task: 'ComputerUseTask', status_msg_id: int):
    """Запуск Claude задачи"""
    if not claude_cu:
        await bot.edit_message_text(
            "❌ Claude не доступен",
            chat_id=chat_id,
            message_id=status_msg_id
        )
        return
    
    try:
        await bot.edit_message_text(
            "🤖 Claude работает...",
            chat_id=chat_id,
            message_id=status_msg_id
        )
        
        result = await claude_cu.run_task(task)
        
        if result.success:
            saved = await db.save_items(result.items, "claude", task.query)
            
            report = (
                f"✅ **Claude завершил!**\n\n"
                f"📊 Найдено: {len(result.items)}\n"
                f"💾 Сохранено: {saved}\n"
                f"⏱ Время: {result.duration:.1f}с\n\n"
            )
            
            if result.items:
                report += "**Товары:**\n"
                for i, item in enumerate(result.items[:3], 1):
                    title = item.get('title', '?')
                    report += f"{i}. {title[:50]}...\n"
            
            keyboard = InlineKeyboardBuilder()
            keyboard.button(text="🔄 Новая задача", callback_data="claude_start")
            
            await bot.edit_message_text(
                report,
                chat_id=chat_id,
                message_id=status_msg_id,
                reply_markup=keyboard.as_markup()
            )
        else:
            await bot.edit_message_text(
                f"❌ Ошибка Claude: {result.error}",
                chat_id=chat_id,
                message_id=status_msg_id
            )
            
    except Exception as e:
        logger.error(f"Ошибка Claude задачи: {e}")
        await bot.edit_message_text(
            f"❌ Критическая ошибка: {str(e)[:100]}",
            chat_id=chat_id,
            message_id=status_msg_id
        )

# ============================================
# ЗАПУСК
# ============================================

async def main():
    """Главная функция"""
    logger.info("🚀 Запуск simple_bot.py")
    logger.info(f"✅ Токен: {config.BOT_TOKEN[:10]}...")
    logger.info(f"🤖 Claude: {'доступен' if claude_cu else 'отключен'}")
    
    # Финальная проверка вебхука перед запуском
    try:
        webhook_info = await bot.get_webhook_info()
        if webhook_info.url:
            logger.warning(f"⚠️ ВЕБХУК ВСЕ ЕЩЕ ЕСТЬ: {webhook_info.url}")
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("✅ Вебхук удален перед стартом")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка при финальной проверке: {e}")
    
    # Запускаем polling
    await dp.start_polling(bot, drop_pending_updates=True)

if __name__ == "__main__":
    asyncio.run(main())