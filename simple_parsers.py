import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
import time  # ЭТА СТРОКА
from config import ITEMS_PER_PAGE, logger
from utils import generate_item_id, make_full_url, get_next_user_agent

def parse_mercari(keyword):
    """Синхронный парсер Mercari"""
    items = []
    url = f"https://jp.mercari.com/search?keyword={quote(keyword)}"
    headers = {'User-Agent': get_next_user_agent()}
    
    try:
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
                    'source': 'Mercari JP'
                })
            except Exception as e:
                logger.debug(f"Ошибка парсинга карточки: {e}")
                
    except Exception as e:
        logger.error(f"Ошибка запроса Mercari: {e}")
    
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