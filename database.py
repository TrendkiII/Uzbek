import sqlite3
import time
from threading import Lock
from config import logger

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
            
            # Попытка добавить новые колонки в старую БД
            try:
                c.execute("ALTER TABLE items ADD COLUMN last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            except sqlite3.OperationalError:
                pass # Колонка уже существует, всё в порядке

            try:
                c.execute("ALTER TABLE items ADD COLUMN brand_main TEXT")
            except sqlite3.OperationalError:
                pass 
            
            c.execute('''CREATE INDEX IF NOT EXISTS idx_source_time ON items(source, found_at)''')
            c.execute('''CREATE INDEX IF NOT EXISTS idx_brand ON items(brand_main)''')
            c.execute('''CREATE INDEX IF NOT EXISTS idx_active ON items(is_active)''')
            c.execute('''CREATE INDEX IF NOT EXISTS idx_brand_active ON items(brand_main, is_active)''')
            
            conn.commit()
            logger.info(f"✅ База данных SQLite инициализирована: {DB_FILE}")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации БД: {e}")
        finally:
            if conn:
                conn.close()

# ==================== Добавление товара с брендом (УЛУЧШЕНО) ====================
def add_item_with_brand(item, brand_main):
    """
    Добавляет товар в базу с указанием основного бренда.
    Если товар уже существует:
        - обновляет last_seen, last_checked, price, title
        - устанавливает is_active = 1 (даже если ранее был помечен как проданный)
    Возвращает True если товар новый, False если уже был.
    """
    with db_lock:
        conn = None
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            
            # Проверяем, существует ли уже товар
            c.execute("SELECT is_active FROM items WHERE id = ?", (item['id'],))
            existing = c.fetchone()
            
            if existing:
                # Товар уже есть – обновляем информацию и активируем
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
                # Новый товар
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

# ==================== Получение товаров по основному бренду (УЛУЧШЕНО) ====================
def get_items_by_brand_main(brand_main, limit=50, include_sold=False):
    """
    Возвращает товары по основному бренду.
    Если include_sold=True – все товары (включая проданные), иначе только активные.
    Сортировка: сначала по last_seen DESC (самые свежие), затем по found_at DESC.
    """
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

# ==================== Получение статистики по брендам (УЛУЧШЕНО) ====================
def get_brands_stats():
    """
    Возвращает статистику по каждому бренду:
    сколько всего найдено, сколько активных.
    Использует составной индекс (brand_main, is_active) для скорости.
    """
    with db_lock:
        conn = None
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            
            c.execute('''SELECT brand_main, 
                                COUNT(*) as total,
                                SUM(is_active) as active
                         FROM items 
                         WHERE brand_main IS NOT NULL
                         GROUP BY brand_main
                         ORDER BY active DESC, total DESC''')
            
            rows = c.fetchall()
            return [{'brand': row[0], 'total': row[1], 'active': row[2]} for row in rows]
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики по брендам: {e}")
            return []
        finally:
            if conn:
                conn.close()

# ==================== Проверка и обновление статуса товара ====================
def check_item_status(item_id, is_active):
    """
    Обновляет статус товара (продан/активен) и время последней проверки.
    Возвращает True если статус изменился.
    """
    with db_lock:
        conn = None
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('''UPDATE items 
                        SET is_active = ?, last_checked = CURRENT_TIMESTAMP
                        WHERE id = ?''',
                     (1 if is_active else 0, item_id))
            conn.commit()
            return c.rowcount > 0
        except Exception as e:
            logger.error(f"❌ Ошибка обновления статуса {item_id}: {e}")
            return False
        finally:
            if conn:
                conn.close()

# ==================== Получение всех брендов из базы ====================
def get_all_brands_from_db():
    """Возвращает список всех брендов, по которым есть товары"""
    with db_lock:
        conn = None
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('''SELECT DISTINCT brand_main FROM items 
                        WHERE brand_main IS NOT NULL 
                        ORDER BY brand_main''')
            return [row[0] for row in c.fetchall()]
        except Exception as e:
            logger.error(f"❌ Ошибка получения списка брендов: {e}")
            return []
        finally:
            if conn:
                conn.close()

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

# ==================== Автоматическая проверка проданных товаров ====================
def check_sold_items(platform, items):
    """
    Проверяет список товаров и помечает как проданные те,
    которые были в базе, но исчезли из поиска.
    """
    with db_lock:
        conn = None
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            
            # Получаем все активные товары с этой платформы
            c.execute('''SELECT id, url FROM items 
                        WHERE source = ? AND is_active = 1''', (platform,))
            active_items = {row[0]: row[1] for row in c.fetchall()}
            
            # Собираем ID найденных товаров
            found_ids = {item['id'] for item in items if 'id' in item}
            
            # Ищем, какие товары были активны, но не найдены сейчас
            sold_ids = []
            for item_id in active_items:
                if item_id not in found_ids:
                    sold_ids.append(item_id)
            
            # Помечаем их как проданные
            if sold_ids:
                placeholders = ','.join(['?'] * len(sold_ids))
                c.execute(f'''UPDATE items 
                            SET is_active = 0, last_checked = CURRENT_TIMESTAMP
                            WHERE id IN ({placeholders})''', sold_ids)
                conn.commit()
                logger.info(f"💰 Отмечено как проданные: {len(sold_ids)} товаров")
            
            return len(sold_ids)
        except Exception as e:
            logger.error(f"❌ Ошибка проверки проданных товаров: {e}")
            return 0
        finally:
            if conn:
                conn.close()

# ==================== Удаление старых товаров ====================
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

# ==================== Получение статистики по базе ====================
def get_stats():
    """
    Возвращает общую статистику по базе данных
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
            
            # Количество активных
            c.execute("SELECT COUNT(*) FROM items WHERE is_active = 1")
            active = c.fetchone()[0]
            
            return {
                'total': total,
                'active': active,
                'by_source': by_source,
                'oldest': oldest,
                'newest': newest
            }
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return {'total': 0, 'active': 0, 'by_source': {}, 'oldest': None, 'newest': None}
        finally:
            if conn:
                conn.close()