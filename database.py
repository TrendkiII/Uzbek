import json
from threading import Lock
from config import FOUND_ITEMS_FILE

lock = Lock()

def init_db():
    """Создает файл базы, если его нет"""
    try:
        with open(FOUND_ITEMS_FILE, "r", encoding="utf-8") as f:
            json.load(f)
    except:
        with open(FOUND_ITEMS_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)

def add_item(item):
    """Добавляет товар, возвращает True если новый"""
    with lock:
        try:
            with open(FOUND_ITEMS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except:
            data = {}
        if item['id'] in data:
            return False
        data[item['id']] = item
        with open(FOUND_ITEMS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True

def get_items_by_brand(brand):
    with lock:
        try:
            with open(FOUND_ITEMS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except:
            return []
    return [v for v in data.values() if brand.lower() in v['title'].lower()]