"""
database.py - Работа с SQLite базой данных для хранения товаров и статистики
"""

import sqlite3
import time
import logging
from threading import Lock
from datetime import datetime, timedelta

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ==================== Конфигурация ====================
DB_FILE = "items.db"
db_lock = Lock()

# ==================== Инициализация базы данных ====================
def init_db():
    """Создаёт таблицу items и обновляет старые таблицы"""
    with db_lock:
        conn = None
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            
            # Основная таблица товаров
            c.execute('''CREATE TABLE IF NOT EXISTS items
                        (id TEXT PRIMARY KEY,
                         title TEXT,
                         price TEXT,
                         url TEXT,
                         img_url TEXT,
                         source TEXT,
                         brand_main TEXT,
                         found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                         last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                         last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                         is_active INTEGER DEFAULT 1)''')
            
            # Таблица пользователей
            c.execute('''CREATE TABLE IF NOT EXISTS users
                        (user_id INTEGER PRIMARY KEY,
                         username TEXT,
                         first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                         last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            
            # Таблица задач Claude
            c.execute('''CREATE TABLE IF NOT EXISTS claude_tasks
                        (task_id TEXT PRIMARY KEY,
                         user_id INTEGER,
                         query TEXT,
                         status TEXT,
                         created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                         completed_at TIMESTAMP,
                         items_found INTEGER DEFAULT 0,
                         error TEXT)''')
            
            # Индексы для ускорения
            c.execute('''CREATE INDEX IF NOT EXISTS idx_source_time ON items(source, found_at)''')
            c.execute('''CREATE INDEX IF NOT EXISTS idx_brand ON items(brand_main)''')
            c.execute('''CREATE INDEX IF NOT EXISTS idx_active ON items(is_active)''')
            
            conn.commit()
            logger.info(f"✅ База данных SQLite инициализирована: {DB_FILE}")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации БД: {e}")
        finally:
            if conn:
                conn.close()

# ==================== КЛАСС DATABASE ====================
class Database:
    """Класс-обертка для работы с БД"""
    
    def __init__(self, db_file=DB_FILE):
        self.db_file = db_file
    
    async def add_user(self, user_id, username):
        """Добавление или обновление пользователя"""
        with db_lock:
            conn = None
            try:
                conn = sqlite3.connect(self.db_file)
                c = conn.cursor()
                c.execute('''INSERT INTO users (user_id, username, last_active)
                            VALUES (?, ?, CURRENT_TIMESTAMP)
                            ON CONFLICT(user_id) DO UPDATE SET
                                username = excluded.username,
                                last_active = CURRENT_TIMESTAMP''',
                         (user_id, username))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Ошибка добавления пользователя {user_id}: {e}")
                return False
            finally:
                if conn:
                    conn.close()
    
    async def save_items(self, items, platform, query):
        """Сохранение товаров"""
        from database import add_item_with_brand
        count = 0
        for item in items:
            brand = item.get('brand', 'Unknown')
            if add_item_with_brand(item, brand):
                count += 1
        return count
    
    async def get_user_tasks(self, user_id, task_type=None):
        """Получение задач пользователя"""
        with db_lock:
            conn = None
            try:
                conn = sqlite3.connect(self.db_file)
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                c.execute('''SELECT * FROM claude_tasks 
                            WHERE user_id = ? 
                            ORDER BY created_at DESC 
                            LIMIT 10''', (user_id,))
                rows = c.fetchall()
                return [dict(row) for row in rows]
            except Exception as e:
                logger.error(f"Ошибка получения задач {user_id}: {e}")
                return []
            finally:
                if conn:
                    conn.close()
    
    async def get_task(self, task_id):
        """Получение задачи по ID"""
        with db_lock:
            conn = None
            try:
                conn = sqlite3.connect(self.db_file)
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                c.execute('''SELECT * FROM claude_tasks WHERE task_id = ?''', (task_id,))
                row = c.fetchone()
                return dict(row) if row else None
            except Exception as e:
                logger.error(f"Ошибка получения задачи {task_id}: {e}")
                return None
            finally:
                if conn:
                    conn.close()
    
    async def save_claude_results(self, items, user_id):
        """Сохранение результатов Claude"""
        return len(items)

# ==================== Работа с товарами ====================
def add_item_with_brand(item, brand_main):
    """
    Добавляет товар в базу с указанием основного бренда.
    """
    with db_lock:
        conn = None
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            
            c.execute("SELECT is_active FROM items WHERE id = ?", (item['id'],))
            existing = c.fetchone()
            
            if existing:
                c.execute('''UPDATE items 
                            SET last_checked = CURRENT_TIMESTAMP,
                                last_seen = CURRENT_TIMESTAMP,
                                is_active = 1,
                                price = ?,
                                title = ?
                            WHERE id = ?''',
                         (item['price'][:100], item['title'][:500], item['id']))
                conn.commit()
                return False
            else:
                c.execute('''INSERT INTO items 
                            (id, title, price, url, img_url, source, brand_main, 
                             found_at, last_checked, last_seen, is_active)
                            VALUES (?, ?, ?, ?, ?, ?, ?, 
                                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)''',
                         (item['id'], 
                          item['title'][:500],
                          item['price'][:100],
                          item['url'][:1000],
                          item.get('img_url', '')[:500],
                          item['source'],
                          brand_main))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"❌ Ошибка добавления товара {item.get('id')}: {e}")
            return False
        finally:
            if conn:
                conn.close()

def get_items_by_brand_main(brand_main, limit=50, include_sold=False):
    """Получение товаров по бренду"""
    with db_lock:
        conn = None
        try:
            conn = sqlite3.connect(DB_FILE)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            
            if include_sold:
                c.execute('''SELECT * FROM items 
                            WHERE brand_main = ?
                            ORDER BY last_seen DESC, found_at DESC
                            LIMIT ?''',
                         (brand_main, limit))
            else:
                c.execute('''SELECT * FROM items 
                            WHERE brand_main = ? AND is_active = 1
                            ORDER BY last_seen DESC, found_at DESC
                            LIMIT ?''',
                         (brand_main, limit))
            
            rows = c.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"❌ Ошибка получения товаров по бренду {brand_main}: {e}")
            return []
        finally:
            if conn:
                conn.close()

def get_stats():
    """Общая статистика"""
    with db_lock:
        conn = None
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            
            c.execute("SELECT COUNT(*) FROM items")
            total = c.fetchone()[0]
            
            c.execute("SELECT COUNT(*) FROM items WHERE is_active = 1")
            active = c.fetchone()[0]
            
            c.execute("SELECT COUNT(*) FROM users")
            users = c.fetchone()[0]
            
            return {
                'total': total,
                'active': active,
                'users': users
            }
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return {'total': 0, 'active': 0, 'users': 0}
        finally:
            if conn:
                conn.close()
                # В конце database.py добавить:

__all__ = ['init_db', 'Database', 'add_item_with_brand', 'get_items_by_brand_main', 'get_stats']