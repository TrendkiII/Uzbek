import sqlite3
import time
from threading import Lock
from config import logger

# ==================== Конфигурация ====================
DB_FILE = "items.db"
db_lock = Lock()

# ==================== Инициализация базы данных ====================
def init_db():
    """Создаёт таблицу items, если её нет"""
    with db_lock:
        conn = None
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            
            # Создаём таблицу для товаров
            c.execute('''CREATE TABLE IF NOT EXISTS items
                        (id TEXT PRIMARY KEY,
                         title TEXT,
                         price TEXT,
                         url TEXT,
                         img_url TEXT,
                         source TEXT,
                         found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            
            # Создаём индекс для быстрого поиска по источнику и времени
            c.execute('''CREATE INDEX IF NOT EXISTS idx_source_time 
                         ON items(source, found_at)''')
            
            # Создаём индекс для поиска по бренду (по заголовку)
            c.execute('''CREATE INDEX IF NOT EXISTS idx_title 
                         ON items(title)''')
            
            conn.commit()
            logger.info(f"✅ База данных SQLite инициализирована: {DB_FILE}")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации БД: {e}")
        finally:
            if conn:
                conn.close()

# ==================== Добавление товара ====================
def add_item(item):
    """
    Добавляет товар в базу, если его там ещё нет.
    Возвращает True если товар новый, False если уже был.
    """
    with db_lock:
        conn = None
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            
            c.execute('''INSERT OR IGNORE INTO items 
                        (id, title, price, url, img_url, source)
                        VALUES (?, ?, ?, ?, ?, ?)''',
                     (item['id'], 
                      item['title'][:500],  # ограничиваем длину
                      item['price'][:100],
                      item['url'][:1000],
                      item.get('img_url', '')[:500],
                      item['source']))
            
            conn.commit()
            return c.rowcount > 0  # если вставилась хотя бы одна строка
        except Exception as e:
            logger.error(f"❌ Ошибка добавления товара {item.get('id')}: {e}")
            return False
        finally:
            if conn:
                conn.close()

# ==================== Массовое добавление (для оптимизации) ====================
def add_items_bulk(items):
    """
    Добавляет несколько товаров за раз (быстрее, чем по одному)
    Возвращает количество новых товаров
    """
    if not items:
        return 0
    
    with db_lock:
        conn = None
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            
            new_count = 0
            for item in items:
                c.execute('''INSERT OR IGNORE INTO items 
                            (id, title, price, url, img_url, source)
                            VALUES (?, ?, ?, ?, ?, ?)''',
                         (item['id'], 
                          item['title'][:500],
                          item['price'][:100],
                          item['url'][:1000],
                          item.get('img_url', '')[:500],
                          item['source']))
                if c.rowcount > 0:
                    new_count += 1
            
            conn.commit()
            return new_count
        except Exception as e:
            logger.error(f"❌ Ошибка массового добавления: {e}")
            return 0
        finally:
            if conn:
                conn.close()

# ==================== Получение всех товаров ====================
def load_all_items(limit=None, offset=None):
    """
    Загружает все товары из базы
    Можно указать limit и offset для пагинации
    """
    with db_lock:
        conn = None
        try:
            conn = sqlite3.connect(DB_FILE)
            conn.row_factory = sqlite3.Row  # чтобы возвращать как словари
            c = conn.cursor()
            
            query = "SELECT * FROM items ORDER BY found_at DESC"
            params = []
            
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            if offset:
                query += " OFFSET ?"
                params.append(offset)
            
            c.execute(query, params)
            rows = c.fetchall()
            
            # Преобразуем в список словарей
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки всех товаров: {e}")
            return []
        finally:
            if conn:
                conn.close()

# ==================== Получение товаров по бренду ====================
def get_items_by_brand(brand, limit=100):
    """
    Возвращает товары, в названии которых встречается бренд
    """
    with db_lock:
        conn = None
        try:
            conn = sqlite3.connect(DB_FILE)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            
            # Используем LIKE для поиска по части названия (регистронезависимо)
            c.execute('''SELECT * FROM items 
                        WHERE title LIKE ? COLLATE NOCASE
                        ORDER BY found_at DESC
                        LIMIT ?''',
                     (f'%{brand}%', limit))
            
            rows = c.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"❌ Ошибка поиска по бренду {brand}: {e}")
            return []
        finally:
            if conn:
                conn.close()

# ==================== Получение последних товаров ====================
def get_recent_items(limit=50):
    """
    Возвращает последние добавленные товары
    """
    return load_all_items(limit=limit)

# ==================== Проверка существования товара ====================
def item_exists(item_id):
    """
    Проверяет, есть ли уже товар с таким ID
    """
    with db_lock:
        conn = None
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT 1 FROM items WHERE id = ?", (item_id,))
            return c.fetchone() is not None
        except Exception as e:
            logger.error(f"❌ Ошибка проверки существования {item_id}: {e}")
            return False
        finally:
            if conn:
                conn.close()

# ==================== Удаление старых товаров (для экономии места) ====================
def delete_old_items(days=30):
    """
    Удаляет товары старше указанного количества дней
    """
    with db_lock:
        conn = None
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('''DELETE FROM items 
                        WHERE found_at < datetime('now', ?)''',
                     (f'-{days} days',))
            conn.commit()
            deleted = c.rowcount
            logger.info(f"🗑 Удалено {deleted} старых товаров (старше {days} дней)")
            return deleted
        except Exception as e:
            logger.error(f"❌ Ошибка удаления старых товаров: {e}")
            return 0
        finally:
            if conn:
                conn.close()

# ==================== Получение статистики ====================
def get_stats():
    """
    Возвращает статистику по базе данных
    """
    with db_lock:
        conn = None
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            
            # Общее количество
            c.execute("SELECT COUNT(*) FROM items")
            total = c.fetchone()[0]
            
            # Количество по источникам
            c.execute('''SELECT source, COUNT(*) FROM items 
                        GROUP BY source ORDER BY COUNT(*) DESC''')
            by_source = dict(c.fetchall())
            
            # Самый старый и самый новый товар
            c.execute("SELECT MIN(found_at), MAX(found_at) FROM items")
            oldest, newest = c.fetchone()
            
            return {
                'total': total,
                'by_source': by_source,
                'oldest': oldest,
                'newest': newest
            }
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return {'total': 0, 'by_source': {}, 'oldest': None, 'newest': None}
        finally:
            if conn:
                conn.close()