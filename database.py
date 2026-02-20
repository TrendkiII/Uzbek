import json
from threading import Lock
from config import FOUND_ITEMS_FILE, file_lock

def init_db():
    with file_lock:
        try:
            with open(FOUND_ITEMS_FILE, "r", encoding="utf-8") as f:
                json.load(f)
        except:
            with open(FOUND_ITEMS_FILE, "w", encoding="utf-8") as f:
                json.dump({}, f)

def load_all_items():
    with file_lock:
        try:
            with open(FOUND_ITEMS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}

def save_all_items(data):
    with file_lock:
        with open(FOUND_ITEMS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

def add_item(item):
    data = load_all_items()
    if item['id'] in data:
        return False
    data[item['id']] = item
    save_all_items(data)
    return True

def get_items_by_brand(brand):
    data = load_all_items()
    return [v for v in data.values() if brand.lower() in v['title'].lower()]