import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
from parsers import PARSERS
from brands import ALL_BRANDS
import threading
import time

API_TOKEN = "ВАШ_ТОКЕН_БОТА_ЗДЕСЬ"

# ================= Logging =================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================= Telegram =================
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# ================= Глобальные состояния =================
STATE = {
    'active': False,
    'selected_brands': [],
    'selected_platforms': list(PARSERS.keys()),
    'last_items': []
}

# ==================== Меню ====================
def build_main_menu():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("Выбрать бренды", callback_data="menu_brands"),
        InlineKeyboardButton("Выбрать площадки", callback_data="menu_platforms"),
        InlineKeyboardButton("Старт поиска", callback_data="menu_start"),
        InlineKeyboardButton("Пауза поиска", callback_data="menu_pause")
    )
    return keyboard

def build_brands_menu():
    keyboard = InlineKeyboardMarkup(row_width=2)
    for brand in ALL_BRANDS:
        selected = "✅" if brand in STATE['selected_brands'] else ""
        keyboard.insert(InlineKeyboardButton(f"{selected} {brand}", callback_data=f"brand_{brand}"))
    keyboard.add(InlineKeyboardButton("Назад", callback_data="menu_back"))
    return keyboard

def build_platforms_menu():
    keyboard = InlineKeyboardMarkup(row_width=2)
    for platform in PARSERS.keys():
        selected = "✅" if platform in STATE['selected_platforms'] else ""
        keyboard.insert(InlineKeyboardButton(f"{selected} {platform}", callback_data=f"platform_{platform}"))
    keyboard.add(InlineKeyboardButton("Назад", callback_data="menu_back"))
    return keyboard

# ================== Обработчики =================
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    await message.answer("Меню бота:", reply_markup=build_main_menu())

@dp.callback_query_handler(lambda c: c.data)
async def menu_callback(callback_query: types.CallbackQuery):
    data = callback_query.data

    # ===== Назад в главное меню =====
    if data == "menu_back":
        await bot.edit_message_text("Меню бота:", callback_query.from_user.id, callback_query.message.message_id,
                                    reply_markup=build_main_menu())
        return

    # ===== Выбор брендов =====
    if data == "menu_brands":
        await bot.edit_message_text("Выберите бренды:", callback_query.from_user.id,
                                    callback_query.message.message_id,
                                    reply_markup=build_brands_menu())
        return

    # ===== Выбор платформ =====
    if data == "menu_platforms":
        await bot.edit_message_text("Выберите площадки:", callback_query.from_user.id,
                                    callback_query.message.message_id,
                                    reply_markup=build_platforms_menu())
        return

    # ===== Старт поиска =====
    if data == "menu_start":
        if not STATE['selected_brands']:
            await bot.answer_callback_query(callback_query.id, "Выберите хотя бы один бренд!")
            return
        STATE['active'] = True
        threading.Thread(target=background_search, daemon=True).start()
        await bot.answer_callback_query(callback_query.id, "Поиск запущен!")
        return

    # ===== Пауза поиска =====
    if data == "menu_pause":
        STATE['active'] = False
        await bot.answer_callback_query(callback_query.id, "Поиск приостановлен!")
        return

    # ===== Выбор конкретного бренда =====
    if data.startswith("brand_"):
        brand = data[6:]
        if brand in STATE['selected_brands']:
            STATE['selected_brands'].remove(brand)
        else:
            STATE['selected_brands'].append(brand)
        await bot.edit_message_text("Выберите бренды:", callback_query.from_user.id,
                                    callback_query.message.message_id,
                                    reply_markup=build_brands_menu())
        return

    # ===== Выбор конкретной платформы =====
    if data.startswith("platform_"):
        platform = data[9:]
        if platform in STATE['selected_platforms']:
            STATE['selected_platforms'].remove(platform)
        else:
            STATE['selected_platforms'].append(platform)
        await bot.edit_message_text("Выберите площадки:", callback_query.from_user.id,
                                    callback_query.message.message_id,
                                    reply_markup=build_platforms_menu())
        return

# ================== Фоновый поиск =================
def background_search():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    while STATE['active']:
        for brand in STATE['selected_brands']:
            for platform in STATE['selected_platforms']:
                parser = PARSERS.get(platform)
                if parser:
                    try:
                        items = parser(brand)
                        new_items = [item for item in items if item['url'] not in [i['url'] for i in STATE['last_items']]]
                        for item in new_items:
                            loop.run_until_complete(send_item(item))
                        STATE['last_items'].extend(new_items)
                    except Exception as e:
                        logger.warning(f"Ошибка парсинга {platform} для {brand}: {e}")
        time.sleep(10)  # пауза между проверками

# ================== Отправка найденного товара =================
async def send_item(item):
    text = f"📌 *{item['title']}*\n💰 {item['price']}\n🔗 [Ссылка]({item['url']})\n🛒 Источник: {item['source']}"
    try:
        await bot.send_message(chat_id=bot.id, text=text, parse_mode="Markdown", disable_web_page_preview=False)
    except Exception as e:
        logger.warning(f"Не удалось отправить товар: {e}")

# ================== Запуск бота =================
if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)