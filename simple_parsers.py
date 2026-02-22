import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
import time
from config import ITEMS_PER_PAGE
from utils import generate_item_id, make_full_url, get_next_user_agent, logger  # ДОБАВИЛ logger

def parse_mercari(keyword):
    """Синхронный парсер Mercari"""
    items = []
    url = f"https://jp.mercari.com/search?keyword={quote(keyword)}"
    headers = {'User-Agent': get_next_user_agent()}
    
    try:
        logger.info(f"Парсинг Mercari: {keyword}")
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            logger.warning(f"Mercari вернул {r.status_code}")
            return items
            
        soup = BeautifulSoup(r.text, 'lxml')
        cards = soup.select('[data-testid="item-cell"]')[:ITEMS_PER_PAGE]
        
        for card in cards:
            try:
                title_elem = card.select_one('[data-testid="thumbnail-title"]')
                price_elem = card.select_one('[data-testid="price"]')
                link_elem = card.select_one('a')
                
                if not title_elem or not link_elem:
                    continue
                
                title = title_elem.text.strip()
                price = price_elem.text.strip() if price_elem else '0'
                href = link_elem.get('href')
                full_url = make_full_url('https://jp.mercari.com', href)
                
                items.append({
                    'id': generate_item_id({'source': 'Mercari JP', 'url': full_url, 'title': title}),
                    'title': title[:100],
                    'price': price[:50],
                    'url': full_url,
                    'source': 'Mercari JP',
                    'img_url': '',  # Добавил пустое поле
                })
            except Exception as e:
                logger.debug(f"Ошибка парсинга карточки: {e}")
                
    except Exception as e:
        logger.error(f"Ошибка запроса Mercari: {e}")
    
    logger.info(f"Найдено {len(items)} товаров на Mercari")
    return items

def search_all(keywords):
    """Запускает поиск по всем ключам"""
    all_items = []
    for keyword in keywords:
        logger.info(f"Ищем '{keyword}'...")
        items = parse_mercari(keyword)
        all_items.extend(items)
        time.sleep(2)  # задержка между запросами
    return all_items

# ============== ДОБАВЛЯЕМ ФУНКЦИЮ ДЛЯ СОВМЕСТИМОСТИ ==============
async def run_parser(platform, query, price_min=0, price_max=1000000, max_items=50):
    """
    Асинхронная функция для запуска парсера (совместимость с simple_bot.py)
    """
    import asyncio
    
    logger.info(f"🔍 Запуск парсера для {platform}, запрос: {query}")
    
    # Пока поддерживаем только Mercari
    if platform in ["mercari", "Mercari JP", "mercari jp"]:
        # Запускаем синхронный парсер в отдельном потоке
        loop = asyncio.get_event_loop()
        items = await loop.run_in_executor(None, parse_mercari, query)
        return items[:max_items]
    else:
        # Для других платформ возвращаем пустой список
        logger.warning(f"⚠️ Платформа {platform} пока не поддерживается")
        return []