"""
simple_parsers.py - Парсеры для маркетплейсов
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
import time
import random
import asyncio
from config import ITEMS_PER_PAGE, logger
from utils import generate_item_id, make_full_url, get_next_user_agent

def parse_mercari(keyword):
    """Синхронный парсер Mercari с отладкой"""
    items = []
    url = f"https://jp.mercari.com/search?keyword={quote(keyword)}"
    
    # Ротация User-Agent
    user_agents = [
        'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (Linux; Android 13; SM-S901B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Mobile Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
    ]
    headers = {
        'User-Agent': random.choice(user_agents),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Cache-Control': 'max-age=0'
    }
    
    logger.info(f"🔍 Парсинг Mercari: {keyword}")
    logger.info(f"📋 URL: {url}")
    
    try:
        # Добавляем случайную задержку
        time.sleep(random.uniform(1, 3))
        
        session = requests.Session()
        r = session.get(url, headers=headers, timeout=15)
        
        logger.info(f"📊 Статус код: {r.status_code}")
        logger.info(f"📏 Длина ответа: {len(r.text)} символов")
        
        if r.status_code != 200:
            logger.warning(f"Mercari вернул {r.status_code}")
            return items
            
        soup = BeautifulSoup(r.text, 'lxml')
        
        # Пробуем разные селекторы
        selectors = [
            '[data-testid="item-cell"]',
            '.merItemCell',
            '.sc-1v2q8tf-0',
            '.items-box',
            'article',
            '.item'
        ]
        
        cards = []
        for selector in selectors:
            cards = soup.select(selector)
            if cards:
                logger.info(f"✅ Найдено карточек по селектору '{selector}': {len(cards)}")
                break
        
        if not cards:
            # Если карточки не найдены, ищем ссылки на товары
            links = soup.find_all('a', href=True)
            product_links = [l for l in links if '/item/' in l['href'] or '/m' in l['href']]
            logger.info(f"🔗 Найдено ссылок на товары: {len(product_links)}")
            
            # Пробуем извлечь товары из ссылок
            for link in product_links[:ITEMS_PER_PAGE]:
                try:
                    href = link.get('href')
                    full_url = make_full_url('https://jp.mercari.com', href)
                    
                    # Ищем название
                    title_elem = link.find(['h3', 'div', 'span'], class_=True)
                    title = title_elem.text.strip() if title_elem else 'Без названия'
                    
                    # Ищем цену
                    price_elem = link.find(text=lambda t: t and ('¥' in t or '円' in t))
                    price = price_elem.strip() if price_elem else 'Цена не указана'
                    
                    # Ищем фото
                    img_elem = link.select_one('img')
                    img_url = img_elem.get('src') if img_elem else ''
                    
                    items.append({
                        'id': generate_item_id({'source': 'Mercari JP', 'url': full_url, 'title': title}),
                        'title': title[:200],
                        'price': price[:100],
                        'url': full_url,
                        'source': 'Mercari JP',
                        'img_url': img_url,
                    })
                except Exception as e:
                    logger.debug(f"Ошибка парсинга ссылки: {e}")
            
            logger.info(f"📦 Извлечено товаров из ссылок: {len(items)}")
            return items
        
        # Парсим карточки
        for card in cards[:ITEMS_PER_PAGE]:
            try:
                # Пробуем разные селекторы для названия
                title_elem = (
                    card.select_one('[data-testid="thumbnail-title"]') or
                    card.select_one('h3') or
                    card.select_one('img[alt]') or
                    card.select_one('.item-name')
                )
                
                # Пробуем разные селекторы для цены
                price_elem = (
                    card.select_one('[data-testid="price"]') or
                    card.select_one('.price') or
                    card.select_one('[class*="price"]') or
                    card.find(text=lambda t: t and ('¥' in t or '円' in t))
                )
                
                # Пробуем найти ссылку
                link_elem = card.select_one('a') or card.find('a', href=True)
                
                if not link_elem:
                    continue
                
                title = title_elem.text.strip() if title_elem else 'Без названия'
                if hasattr(title_elem, 'get') and title_elem.get('alt'):
                    title = title_elem.get('alt')
                
                price = price_elem.text.strip() if price_elem else 'Цена не указана'
                if isinstance(price_elem, str):
                    price = price_elem
                
                href = link_elem.get('href')
                full_url = make_full_url('https://jp.mercari.com', href)
                
                # Ищем фото
                img_elem = card.select_one('img') or link_elem.select_one('img')
                img_url = img_elem.get('src') if img_elem else ''
                
                items.append({
                    'id': generate_item_id({'source': 'Mercari JP', 'url': full_url, 'title': title}),
                    'title': title[:200],
                    'price': price[:100],
                    'url': full_url,
                    'source': 'Mercari JP',
                    'img_url': img_url,
                })
                
                logger.debug(f"✅ Товар: {title[:30]}... - {price}")
                
            except Exception as e:
                logger.debug(f"Ошибка парсинга карточки: {e}")
                
    except requests.exceptions.Timeout:
        logger.error("⏰ Таймаут запроса Mercari")
    except requests.exceptions.ConnectionError:
        logger.error("🔌 Ошибка соединения с Mercari")
    except Exception as e:
        logger.error(f"❌ Ошибка запроса Mercari: {e}")
    
    logger.info(f"📦 Найдено {len(items)} товаров на Mercari")
    return items

def search_all(keywords):
    """Запускает поиск по всем ключам"""
    all_items = []
    for keyword in keywords:
        logger.info(f"🔍 Ищем '{keyword}'...")
        items = parse_mercari(keyword)
        all_items.extend(items)
        time.sleep(random.uniform(2, 5))  # случайная задержка
    return all_items

async def run_parser(platform, query, price_min=0, price_max=1000000, max_items=50):
    """
    Асинхронная функция для запуска парсера
    """
    logger.info(f"🚀 Запуск парсера для {platform}, запрос: {query}")
    
    # Для Mercari
    if platform in ["mercari", "Mercari JP", "mercari jp", "mercari"]:
        # Запускаем синхронный парсер в отдельном потоке
        loop = asyncio.get_event_loop()
        items = await loop.run_in_executor(None, parse_mercari, query)
        return items[:max_items]
    
    elif platform in ["all", "multiple", "все"]:
        # Поиск по всем ключам
        loop = asyncio.get_event_loop()
        items = await loop.run_in_executor(None, search_all, [query])
        return items[:max_items]
    
    else:
        # Для других платформ
        logger.warning(f"⚠️ Платформа {platform} пока не поддерживается, используем Mercari")
        loop = asyncio.get_event_loop()
        items = await loop.run_in_executor(None, parse_mercari, query)
        return items[:max_items]