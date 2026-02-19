import json
from threading import Lock
from config import FOUND_ITEMS_FILE, file_lock

def init_db():
    """Создает файл базы, если его нет"""
    with file_lock:
        try:
            with open(FOUND_ITEMS_FILE, "r", encoding="utf-8") as f:
                json.load(f)
        except:
            with open(FOUND_ITEMS_FILE, "w", encoding="utf-8") as f:
                json.dump({}, f)

def load_all_items():
    """Загружает все элементы из базы"""
    with file_lock:
        try:
            with open(FOUND_ITEMS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}

def save_all_items(data):
    """Сохраняет все элементы в базу"""
    with file_lock:
        with open(FOUND_ITEMS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

def add_item(item):
    """
    Добавляет товар в базу, если его там ещё нет.
    Возвращает True если товар новый.
    """
    data = load_all_items()
    if item['id'] in data:
        return False
    data[item['id']] = item
    save_all_items(data)
    return True

def get_items_by_brand(brand):
    data = load_all_items()
    return [v for v in data.values() if brand.lower() in v['title'].lower()]