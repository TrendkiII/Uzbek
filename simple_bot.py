"""
simple_bot.py - Telegram бот для управления парсингом с поддержкой Claude Computer Use
"""

import os
import asyncio
import logging
import json
from datetime import datetime
from typing import Dict, List, Optional

# Telegram бот (использую aiogram 3.x как самую популярную асинхронную библиотеку)
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Твои модули
from config import Config
from database import Database
from brands import get_all_brands, get_brand_categories
from simple_parsers import parse_mercari, search_all
from utils import logger
from utils import logger, format_number

# Импорт модуля Computer Use
from claude_controller import ClaudeComputerUse, ComputerUseTask

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================
# КОНФИГУРАЦИЯ
# ============================================

class BotConfig:
    """Конфигурация бота из переменных окружения"""
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(","))) if os.getenv("ADMIN_IDS") else []
    
    # Настройки Computer Use
    CLAUDE_ENABLED = os.getenv("CLAUDE_ENABLED", "false").lower() == "true"
    CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
    CLAUDE_PROJECT_ID = os.getenv("CLAUDE_PROJECT_ID")
    CLAUDE_REGION = os.getenv("CLAUDE_REGION", "us-central1")
    
    # Доступные платформы для парсинга
    PLATFORMS = {
        "olx": {"name": "OLX", "url": "https://www.olx.pl", "use_claude": True},
        "ebay": {"name": "eBay", "url": "https://www.ebay.com", "use_claude": True},
        "vinted": {"name": "Vinted", "url": "https://www.vinted.pl", "use_claude": True},
        "wallapop": {"name": "Wallapop", "url": "https://es.wallapop.com", "use_claude": True},
        "allegro": {"name": "Allegro", "url": "https://allegro.pl", "use_claude": False},
        "facebook": {"name": "Facebook Marketplace", "url": "https://www.facebook.com/marketplace", "use_claude": True},
    }
    
    # Настройки парсинга
    DEFAULT_MAX_ITEMS = 50
    DEFAULT_PRICE_MIN = 0
    DEFAULT_PRICE_MAX = 1000000

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
# ИНИЦИАЛИЗАЦИЯ
# ============================================

config = BotConfig()
bot = Bot(token=config.BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Инициализация базы данных
db = Database()

# Инициализация Claude Computer Use (если включено)
claude_cu = None
if config.CLAUDE_ENABLED:
    try:
        claude_cu = ClaudeComputerUse(
            api_key=config.CLAUDE_API_KEY,
            project_id=config.CLAUDE_PROJECT_ID,
            region=config.CLAUDE_REGION
        )
        logger.info("✅ Claude Computer Use инициализирован")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации Claude: {e}")

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
    builder.adjust(2, 2, 1)
    return builder.as_markup()

def get_platforms_keyboard(use_claude_only: bool = False):
    """Клавиатура с площадками"""
    builder = InlineKeyboardBuilder()
    
    for platform_id, platform_info in config.PLATFORMS.items():
        if use_claude_only and not platform_info.get("use_claude", False):
            continue
            
        emoji = "🤖" if platform_info.get("use_claude") else "⚡"
        builder.button(
            text=f"{emoji} {platform_info['name']}",
            callback_data=f"platform_{platform_id}"
        )
    
    builder.button(text="◀️ Назад", callback_data="back_to_main")
    builder.adjust(2, 2, 1)
    return builder.as_markup()

def get_brands_keyboard():
    """Клавиатура с брендами"""
    brands = get_all_brands()
    builder = InlineKeyboardBuilder()
    
    for brand in brands[:20]:  # Показываем первые 20
        builder.button(text=brand, callback_data=f"brand_{brand}")
    
    builder.button(text="◀️ Назад", callback_data="back_to_platforms")
    builder.adjust(3, 3, 3, 3, 3, 2)
    return builder.as_markup()

def get_claude_menu_keyboard():
    """Меню Claude Computer Use"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🖱️ Запустить парсинг с Claude", callback_data="claude_start")
    builder.button(text="📋 Активные задачи", callback_data="claude_tasks")
    builder.button(text="📊 Статистика Claude", callback_data="claude_stats")
    builder.button(text="⚙️ Настройки Claude", callback_data="claude_settings")
    builder.button(text="◀️ Назад", callback_data="back_to_main")
    builder.adjust(2, 2, 1)
    return builder.as_markup()

def get_task_control_keyboard(task_id: str):
    """Клавиатура управления задачей"""
    builder = InlineKeyboardBuilder()
    builder.button(text="⏸️ Пауза", callback_data=f"task_pause_{task_id}")
    builder.button(text="▶️ Возобновить", callback_data=f"task_resume_{task_id}")
    builder.button(text="⏹️ Остановить", callback_data=f"task_stop_{task_id}")
    builder.button(text="📊 Статус", callback_data=f"task_status_{task_id}")
    builder.button(text="◀️ Назад", callback_data="claude_tasks")
    builder.adjust(2, 2, 1)
    return builder.as_markup()

# ============================================
# ОБРАБОТЧИКИ КОМАНД
# ============================================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    username = message.from_user.username or "Unknown"
    
    # Сохраняем пользователя в БД
    await db.add_user(user_id, username)
    
    # Приветственное сообщение
    welcome_text = (
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "Я бот для парсинга всех б/у площадок мира. "
        "Могу искать товары по брендам на разных платформах.\n\n"
    )
    
    if claude_cu:
        welcome_text += "🤖 **Claude Computer Use АКТИВИРОВАН!**\nМогу обходить антибот-системы и капчи.\n\n"
    
    welcome_text += "Выбери действие в меню ниже:"
    
    await message.answer(
        welcome_text,
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

@dp.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help"""
    help_text = (
        "🔍 **Доступные команды:**\n\n"
        "/start - Запустить бота\n"
        "/help - Эта справка\n"
        "/search <бренд> - Быстрый поиск\n"
        "/claude <запрос> - Поиск с Claude Computer Use\n"
        "/stats - Статистика\n"
        "/tasks - Мои задачи\n\n"
        "**Примеры:**\n"
        "`/search Nike Air Max`\n"
        "`/claude Найди iPhone 13 на OLX Польша`"
    )
    await message.answer(help_text, parse_mode="Markdown")

@dp.message(Command("search"))
async def cmd_search(message: Message, state: FSMContext):
    """Быстрый поиск по запросу"""
    query = message.text.replace("/search", "").strip()
    
    if not query:
        await message.answer(
            "Введи поисковый запрос после команды, например:\n"
            "`/search Nike Air Max`",
            parse_mode="Markdown"
        )
        return
    
    # Сохраняем запрос и переходим к выбору платформы
    await state.update_data(search_query=query)
    await state.set_state(ParserStates.waiting_for_platform)
    
    await message.answer(
        f"🔍 Ищем: **{query}**\n\nВыбери площадку для поиска:",
        reply_markup=get_platforms_keyboard(),
        parse_mode="Markdown"
    )

@dp.message(Command("claude"))
async def cmd_claude(message: Message, state: FSMContext):
    """Запуск поиска с Claude Computer Use"""
    if not claude_cu:
        await message.answer(
            "❌ Claude Computer Use не активирован.\n"
            "Проверь настройки в конфиге."
        )
        return
    
    query = message.text.replace("/claude", "").strip()
    
    if not query:
        await message.answer(
            "Введи запрос после команды, например:\n"
            "`/claude Найди iPhone 13 на OLX Польша, цена до 3000 злотых`"
        )
        return
    
    # Отправляем запрос в Claude
    status_msg = await message.answer("🤖 Запускаю Claude Computer Use... Это может занять некоторое время.")
    
    try:
        # Создаем задачу для Claude
        task = ComputerUseTask(
            query=query,
            user_id=message.from_user.id,
            platforms=config.PLATFORMS
        )
        
        # Запускаем асинхронно
        asyncio.create_task(run_claude_task(message.chat.id, task, status_msg.message_id))
        
    except Exception as e:
        logger.error(f"Ошибка запуска Claude: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")

# ============================================
# ОБРАБОТЧИКИ CALLBACK QUERIES
# ============================================

@dp.callback_query(lambda c: c.data == "quick_search")
async def callback_quick_search(callback: CallbackQuery, state: FSMContext):
    """Быстрый поиск из меню"""
    await callback.answer()
    await state.set_state(ParserStates.waiting_for_search_query)
    await callback.message.edit_text(
        "Введи поисковый запрос (например: Nike Air Max, iPhone 13):",
        reply_markup=InlineKeyboardBuilder().button(text="◀️ Назад", callback_data="back_to_main").as_markup()
    )

@dp.callback_query(lambda c: c.data == "claude_menu")
async def callback_claude_menu(callback: CallbackQuery):
    """Меню Claude Computer Use"""
    await callback.answer()
    
    if not claude_cu:
        await callback.message.edit_text(
            "❌ Claude Computer Use не активирован.\n\n"
            "Чтобы активировать, добавь в переменные окружения:\n"
            "`CLAUDE_ENABLED=true`\n"
            "`CLAUDE_API_KEY=твой_ключ`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardBuilder().button(text="◀️ Назад", callback_data="back_to_main").as_markup()
        )
        return
    
    status_text = (
        "🤖 **Claude Computer Use**\n\n"
        "✅ Модуль активирован\n"
        f"🌍 Регион: {config.CLAUDE_REGION}\n"
        "🖱️ Доступны функции:\n"
        "• Обход капчи\n"
        "• Эмуляция человека\n"
        "• Парсинг сложных сайтов\n"
        "• Работа с JavaScript\n\n"
        "Выбери действие:"
    )
    
    await callback.message.edit_text(
        status_text,
        reply_markup=get_claude_menu_keyboard(),
        parse_mode="Markdown"
    )

@dp.callback_query(lambda c: c.data == "claude_start")
async def callback_claude_start(callback: CallbackQuery, state: FSMContext):
    """Запуск задачи Claude"""
    await callback.answer()
    await state.set_state(ParserStates.waiting_for_claude_task)
    await callback.message.edit_text(
        "🔍 Опиши задачу для Claude подробно.\n\n"
        "**Примеры:**\n"
        "• Найди все Nike Air Force 1 на OLX Польша, цена до 500 злотых, с фото\n"
        "• Спарси iPhone 13 на eBay, только новые, с доставкой в Европу\n"
        "• Найди Nintendo Switch на Vinted, цена от 800 до 1200 злотых\n\n"
        "Чем подробнее опишешь, тем точнее будет результат.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardBuilder().button(text="◀️ Назад", callback_data="claude_menu").as_markup()
    )

@dp.callback_query(lambda c: c.data == "claude_tasks")
async def callback_claude_tasks(callback: CallbackQuery):
    """Список активных задач Claude"""
    await callback.answer()
    
    # Получаем задачи из БД
    tasks = await db.get_user_tasks(callback.from_user.id, task_type="claude")
    
    if not tasks:
        await callback.message.edit_text(
            "📋 У тебя нет активных задач Claude.\n\n"
            "Запусти новую задачу через меню.",
            reply_markup=InlineKeyboardBuilder()
                .button(text="🖱️ Запустить задачу", callback_data="claude_start")
                .button(text="◀️ Назад", callback_data="claude_menu")
                .as_markup()
        )
        return
    
    builder = InlineKeyboardBuilder()
    for task in tasks[:5]:  # Показываем последние 5 задач
        status_emoji = {
            "running": "▶️",
            "paused": "⏸️",
            "completed": "✅",
            "failed": "❌"
        }.get(task["status"], "⏳")
        
        builder.button(
            text=f"{status_emoji} {task['name'][:30]}",
            callback_data=f"task_view_{task['id']}"
        )
    
    builder.button(text="◀️ Назад", callback_data="claude_menu")
    builder.adjust(1, 1, 1, 1, 1)
    
    await callback.message.edit_text(
        "📋 **Твои задачи Claude:**",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

@dp.callback_query(lambda c: c.data.startswith("task_view_"))
async def callback_task_view(callback: CallbackQuery):
    """Просмотр конкретной задачи"""
    task_id = callback.data.replace("task_view_", "")
    
    # Получаем задачу из БД
    task = await db.get_task(task_id)
    
    if not task:
        await callback.answer("Задача не найдена")
        return
    
    # Формируем статус
    status_text = (
        f"📋 **Задача: {task['name']}**\n\n"
        f"🔄 Статус: **{task['status']}**\n"
        f"📊 Прогресс: {task.get('progress', 0)}%\n"
        f"📦 Найдено: {task.get('items_found', 0)} товаров\n"
        f"⏱️ Создана: {task['created_at']}\n"
    )
    
    if task.get('completed_at'):
        status_text += f"✅ Завершена: {task['completed_at']}\n"
    
    if task.get('error'):
        status_text += f"❌ Ошибка: {task['error']}\n"
    
    await callback.message.edit_text(
        status_text,
        reply_markup=get_task_control_keyboard(task_id),
        parse_mode="Markdown"
    )

@dp.callback_query(lambda c: c.data.startswith("platform_"))
async def callback_platform_selected(callback: CallbackQuery, state: FSMContext):
    """Выбор платформы"""
    platform_id = callback.data.replace("platform_", "")
    platform_info = config.PLATFORMS.get(platform_id)
    
    if not platform_info:
        await callback.answer("Платформа не найдена")
        return
    
    # Сохраняем платформу
    await state.update_data(platform=platform_id)
    
    # Получаем данные состояния
    data = await state.get_data()
    search_query = data.get("search_query")
    
    if search_query:
        # Если есть поисковый запрос, запускаем парсинг
        await callback.answer()
        
        status_msg = await callback.message.edit_text(
            f"🔍 Ищу **{search_query}** на **{platform_info['name']}**...\n"
            f"⏳ Это может занять некоторое время.",
            parse_mode="Markdown"
        )
        
        # Запускаем парсинг
        if platform_info.get("use_claude") and claude_cu:
            # Используем Claude для сложных сайтов
            task = ComputerUseTask(
                query=search_query,
                platform=platform_id,
                user_id=callback.from_user.id
            )
            asyncio.create_task(run_claude_task(callback.message.chat.id, task, status_msg.message_id))
        else:
            # Используем обычный парсер
            asyncio.create_task(run_parser_task(
                callback.message.chat.id, 
                platform_id, 
                search_query, 
                status_msg.message_id
            ))
    else:
        # Иначе выбираем бренд
        await state.set_state(ParserStates.waiting_for_brand)
        await callback.message.edit_text(
            f"Выбрана платформа: **{platform_info['name']}**\n\n"
            "Теперь выбери бренд для поиска:",
            reply_markup=get_brands_keyboard(),
            parse_mode="Markdown"
        )

@dp.callback_query(lambda c: c.data.startswith("brand_"))
async def callback_brand_selected(callback: CallbackQuery, state: FSMContext):
    """Выбор бренда"""
    brand = callback.data.replace("brand_", "")
    
    # Сохраняем бренд
    await state.update_data(brand=brand)
    
    # Спрашиваем мин. цену
    await state.set_state(ParserStates.waiting_for_price_min)
    await callback.message.edit_text(
        f"Выбран бренд: **{brand}**\n\n"
        "Введи минимальную цену (или 0, если не важно):",
        parse_mode="Markdown"
    )

# ============================================
# ОБРАБОТЧИКИ СООБЩЕНИЙ (FSM)
# ============================================

@dp.message(ParserStates.waiting_for_search_query)
async def process_search_query(message: Message, state: FSMContext):
    """Обработка поискового запроса"""
    query = message.text.strip()
    
    if len(query) < 2:
        await message.answer("Слишком короткий запрос. Введи минимум 2 символа.")
        return
    
    await state.update_data(search_query=query)
    await state.set_state(ParserStates.waiting_for_platform)
    
    await message.answer(
        f"🔍 Ищем: **{query}**\n\nВыбери площадку для поиска:",
        reply_markup=get_platforms_keyboard(),
        parse_mode="Markdown"
    )

@dp.message(ParserStates.waiting_for_claude_task)
async def process_claude_task(message: Message, state: FSMContext):
    """Обработка задачи для Claude"""
    task_description = message.text.strip()
    
    if len(task_description) < 5:
        await message.answer("Слишком короткое описание. Опиши задачу подробнее.")
        return
    
    status_msg = await message.answer(
        "🤖 Передаю задачу Claude Computer Use...\n"
        "⏳ Это может занять 1-5 минут в зависимости от сложности."
    )
    
    # Создаем задачу
    task = ComputerUseTask(
        query=task_description,
        user_id=message.from_user.id,
        platforms=config.PLATFORMS
    )
    
    # Запускаем асинхронно
    asyncio.create_task(run_claude_task(message.chat.id, task, status_msg.message_id))
    
    await state.clear()

@dp.message(ParserStates.waiting_for_price_min)
async def process_price_min(message: Message, state: FSMContext):
    """Обработка минимальной цены"""
    try:
        price_min = int(message.text.strip())
        await state.update_data(price_min=price_min)
        await state.set_state(ParserStates.waiting_for_price_max)
        
        await message.answer(
            "Введи максимальную цену:"
        )
    except ValueError:
        await message.answer("Пожалуйста, введи число (целое).")

@dp.message(ParserStates.waiting_for_price_max)
async def process_price_max(message: Message, state: FSMContext):
    """Обработка максимальной цены и запуск поиска"""
    try:
        price_max = int(message.text.strip())
        await state.update_data(price_max=price_max)
        
        # Получаем все данные
        data = await state.get_data()
        platform = data.get("platform")
        brand = data.get("brand")
        price_min = data.get("price_min", 0)
        search_query = data.get("search_query", brand)
        
        platform_info = config.PLATFORMS.get(platform, {})
        
        status_msg = await message.answer(
            f"🔍 Ищу **{search_query}** на **{platform_info.get('name', platform)}**\n"
            f"💰 Цена: {price_min} - {price_max}\n"
            f"⏳ Начинаю парсинг...",
            parse_mode="Markdown"
        )
        
        # Запускаем парсинг
        if platform_info.get("use_claude") and claude_cu:
            task = ComputerUseTask(
                query=f"{brand} цена от {price_min} до {price_max}",
                platform=platform,
                user_id=message.from_user.id
            )
            asyncio.create_task(run_claude_task(message.chat.id, task, status_msg.message_id))
        else:
            asyncio.create_task(run_parser_task(
                message.chat.id,
                platform,
                search_query,
                status_msg.message_id,
                price_min,
                price_max
            ))
        
        await state.clear()
        
    except ValueError:
        await message.answer("Пожалуйста, введи число (целое).")

# ============================================
# АСИНХРОННЫЕ ЗАДАЧИ
# ============================================

async def run_parser_task(chat_id: int, platform: str, query: str, status_msg_id: int, price_min: int = 0, price_max: int = 1000000):
    """Запуск обычного парсера в фоне"""
    try:
        # Используем существующие функции вместо run_parser
        from simple_parsers import parse_mercari, search_all
        
        # Для Mercari используем parse_mercari
        if platform == "mercari" or platform == "Mercari JP":
            # Запускаем в отдельном потоке, т.к. parse_mercari синхронный
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(None, parse_mercari, query)
        else:
            # Для нескольких ключей используем search_all
            results = await loop.run_in_executor(None, search_all, [query])
        
        # Ограничиваем количество
        results = results[:config.DEFAULT_MAX_ITEMS]
        
        # Сохраняем в БД
        saved_count = await db.save_items(results, platform, query)
        
        # Формируем отчет
        report = (
            f"✅ **Парсинг завершен!**\n\n"
            f"📊 **Результаты:**\n"
            f"• Платформа: Mercari JP\n"
            f"• Запрос: {query}\n"
            f"• Найдено: {len(results)}\n"
            f"• Сохранено: {saved_count}\n\n"
        )
        
        if results:
            # Показываем первые 3 результата
            report += "**Топ товаров:**\n"
            for i, item in enumerate(results[:3], 1):
                report += f"{i}. {item['title'][:50]}... - {item['price']}\n"
        
        await bot.edit_message_text(
            report,
            chat_id=chat_id,
            message_id=status_msg_id,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardBuilder()
                .button(text="📋 Все результаты", callback_data=f"results_{platform}_{query[:20]}")
                .button(text="🔄 Новый поиск", callback_data="quick_search")
                .as_markup()
        )
        
    except Exception as e:
        logger.error(f"Ошибка парсинга: {e}")
        await bot.edit_message_text(
            f"❌ **Ошибка парсинга:**\n```\n{str(e)}\n```",
            chat_id=chat_id,
            message_id=status_msg_id,
            parse_mode="Markdown"
        )

async def run_claude_task(chat_id: int, task: 'ComputerUseTask', status_msg_id: int):
    """Запуск задачи Claude Computer Use"""
    try:
        # Обновляем статус
        await bot.edit_message_text(
            f"🤖 **Claude Computer Use работает...**\n\n"
            f"📋 Задача: {task.query[:100]}\n"
            f"⏳ Прогресс: 0%",
            chat_id=chat_id,
            message_id=status_msg_id,
            parse_mode="Markdown"
        )
        
        # Запускаем Claude
        result = await claude_cu.run_task(task)
        
        if result.success:
            # Сохраняем результаты
            saved_count = await db.save_claude_results(result.items, task.user_id)
            
            # Формируем отчет
            report = (
                f"✅ **Claude Computer Use завершил задачу!**\n\n"
                f"📊 **Результаты:**\n"
                f"• Найдено товаров: {len(result.items)}\n"
                f"• Сохранено: {saved_count}\n"
                f"• Время работы: {result.duration} сек\n"
                f"• Потрачено токенов: {result.tokens}\n\n"
            )
            
            if result.screenshots:
                report += f"📸 Сделано скриншотов: {len(result.screenshots)}\n\n"
            
            if result.items:
                # Показываем первые 3 результата
                report += "**Найденные товары:**\n"
                for i, item in enumerate(result.items[:3], 1):
                    report += f"{i}. {item.get('title', 'Без названия')[:50]}... - {item.get('price', '?')}\n"
            
            await bot.edit_message_text(
                report,
                chat_id=chat_id,
                message_id=status_msg_id,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardBuilder()
                    .button(text="📋 Все результаты", callback_data=f"claude_results_{task.id}")
                    .button(text="🔄 Новая задача", callback_data="claude_start")
                    .as_markup()
            )
            
        else:
            # Ошибка
            error_text = (
                f"❌ **Claude Computer Use не справился**\n\n"
                f"Причина: {result.error}\n\n"
            )
            
            if "капча" in result.error.lower():
                error_text += "🤖 **Нужна помощь с капчей!**\n"
                error_text += "Нажми кнопку ниже, чтобы помочь Claude."
                
                await bot.edit_message_text(
                    error_text,
                    chat_id=chat_id,
                    message_id=status_msg_id,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardBuilder()
                        .button(text="🔓 Помочь с капчей", callback_data=f"help_captcha_{task.id}")
                        .button(text="🔄 Попробовать снова", callback_data="claude_start")
                        .as_markup()
                )
            else:
                await bot.edit_message_text(
                    error_text,
                    chat_id=chat_id,
                    message_id=status_msg_id,
                    parse_mode="Markdown"
                )
        
    except Exception as e:
        logger.error(f"Ошибка Claude задачи: {e}")
        await bot.edit_message_text(
            f"❌ **Критическая ошибка:**\n```\n{str(e)}\n```",
            chat_id=chat_id,
            message_id=status_msg_id,
            parse_mode="Markdown"
        )

# ============================================
# ЗАПУСК БОТА
# ============================================

async def main():
    """Главная функция запуска"""
    logger.info("🚀 Запуск simple_bot.py с поддержкой Claude Computer Use")
    
    if claude_cu:
        logger.info("✅ Claude Computer Use активирован")
    else:
        logger.warning("⚠️ Claude Computer Use отключен")
    
    # Запускаем polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())