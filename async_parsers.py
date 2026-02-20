import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import quote, urljoin
from config import ITEMS_PER_PAGE, logger
import time

async def fetch_html(session, url, semaphore, timeout=10):
    """Асинхронно получает HTML страницы"""
    async with semaphore:
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            async with session.get(url, headers=headers, timeout=timeout, ssl=False) as response:
                if response.status == 200:
                    return await response.text()
                elif response.status == 403:
                    logger.warning(f"🚫 403 Forbidden: {url}")
                elif response.status == 404:
                    logger.warning(f"🔍 404 Not Found: {url}")
                else:
                    logger.warning(f"🌐 HTTP {response.status} для {url}")
        except asyncio.TimeoutError:
            logger.warning(f"⏰ Таймаут для {url}")
        except aiohttp.ClientProxyConnectionError:
            logger.warning(f"🔌 Ошибка прокси для {url}")
        except aiohttp.ClientConnectorError:
            logger.warning(f"🔌 Ошибка подключения для {url}")
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки {url}: {e}")
        return None

def make_full_url(base, href):
    """Превращает относительный href в абсолютный URL"""
    if not href:
        return ''
    if href.startswith('http'):
        return href
    return urljoin(base, href)

# ==================== MERCARI JP ====================
async def parse_mercari_async(session, keyword, semaphore):
    """Асинхронный парсер Mercari JP"""
    items = []
    url = f"https://jp.mercari.com/search?keyword={quote(keyword)}&order=desc&sort=created_time"
    
    html = await fetch_html(session, url, semaphore)
    if not html:
        return items
    
    try:
        soup = BeautifulSoup(html, 'lxml')
        cards = soup.select('[data-testid="item-cell"]')[:ITEMS_PER_PAGE]
        
        for card in cards:
            try:
                title_elem = card.select_one('[data-testid="thumbnail-title"]')
                price_elem = card.select_one('[data-testid="price"]')
                link_elem = card.select_one('a')
                img_elem = card.select_one('img')
                
                if not link_elem:
                    continue
                
                title = title_elem.text.strip() if title_elem else 'No title'
                price = price_elem.text.strip() if price_elem else 'Цена не указана'
                
                img_url = None
                if img_elem:
                    img_url = img_elem.get('src')
                    if img_url and img_url.startswith('//'):
                        img_url = 'https:' + img_url
                
                href = link_elem.get('href')
                full_url = make_full_url('https://jp.mercari.com', href)
                
                items.append({
                    'title': title[:100],
                    'price': price[:50],
                    'url': full_url,
                    'img_url': img_url,
                    'source': 'Mercari JP'
                })
            except Exception as e:
                logger.debug(f"Ошибка парсинга карточки Mercari: {e}")
                continue
    except Exception as e:
        logger.error(f"Ошибка парсинга Mercari для {keyword}: {e}")
    
    return items

# ==================== RAKUTEN RAKUMA ====================
async def parse_rakuma_async(session, keyword, semaphore):
    """Асинхронный парсер Rakuten Rakuma"""
    items = []
    url = f"https://fril.jp/s?query={quote(keyword)}&order=desc&sort=created_at"
    
    html = await fetch_html(session, url, semaphore)
    if not html:
        return items
    
    try:
        soup = BeautifulSoup(html, 'lxml')
        cards = soup.select('.item')[:ITEMS_PER_PAGE]
        
        for card in cards:
            try:
                title_elem = card.select_one('.item-box__title a')
                price_elem = card.select_one('.item-box__price')
                link_elem = card.select_one('a')
                img_elem = card.select_one('img')
                
                if not title_elem or not link_elem:
                    continue
                
                title = title_elem.text.strip()
                price = price_elem.text.strip() if price_elem else 'Цена не указана'
                
                img_url = None
                if img_elem:
                    img_url = img_elem.get('src')
                    if img_url and img_url.startswith('//'):
                        img_url = 'https:' + img_url
                
                href = link_elem.get('href')
                full_url = make_full_url('https://fril.jp', href)
                
                items.append({
                    'title': title[:100],
                    'price': price[:50],
                    'url': full_url,
                    'img_url': img_url,
                    'source': 'Rakuten Rakuma'
                })
            except Exception as e:
                logger.debug(f"Ошибка парсинга Rakuma: {e}")
                continue
    except Exception as e:
        logger.error(f"Ошибка парсинга Rakuma для {keyword}: {e}")
    
    return items

# ==================== YAHOO FLEA ====================
async def parse_yahoo_flea_async(session, keyword, semaphore):
    """Асинхронный парсер Yahoo Flea"""
    items = []
    url = f"https://paypayfleamarket.yahoo.co.jp/search/{quote(keyword)}?order=desc&sort=create_time"
    
    html = await fetch_html(session, url, semaphore)
    if not html:
        return items
    
    try:
        soup = BeautifulSoup(html, 'lxml')
        cards = soup.select('.Product')[:ITEMS_PER_PAGE]
        
        for card in cards:
            try:
                title_elem = card.select_one('.Product__titleLink')
                price_elem = card.select_one('.Product__price')
                link_elem = card.select_one('a')
                img_elem = card.select_one('img')
                
                if not title_elem:
                    continue
                
                title = title_elem.text.strip()
                price = price_elem.text.strip() if price_elem else 'Цена не указана'
                
                img_url = None
                if img_elem:
                    img_url = img_elem.get('src')
                    if img_url and img_url.startswith('//'):
                        img_url = 'https:' + img_url
                
                href = link_elem.get('href') if link_elem else ''
                full_url = make_full_url('https://paypayfleamarket.yahoo.co.jp', href)
                
                items.append({
                    'title': title[:100],
                    'price': price[:50],
                    'url': full_url,
                    'img_url': img_url,
                    'source': 'Yahoo Flea'
                })
            except Exception as e:
                logger.debug(f"Ошибка парсинга Yahoo Flea: {e}")
                continue
    except Exception as e:
        logger.error(f"Ошибка парсинга Yahoo Flea для {keyword}: {e}")
    
    return items

# ==================== YAHOO AUCTION ====================
async def parse_yahoo_auction_async(session, keyword, semaphore):
    """Асинхронный парсер Yahoo Auction"""
    items = []
    url = f"https://auctions.yahoo.co.jp/search/search?p={quote(keyword)}&aq=-1&type=all&auccat=&tab_ex=commerce&order=desc"
    
    html = await fetch_html(session, url, semaphore)
    if not html:
        return items
    
    try:
        soup = BeautifulSoup(html, 'lxml')
        cards = soup.select('.Product')[:ITEMS_PER_PAGE]
        
        for card in cards:
            try:
                title_elem = card.select_one('.Product__titleLink')
                price_elem = card.select_one('.Product__price')
                link_elem = card.select_one('a')
                img_elem = card.select_one('img')
                
                if not title_elem:
                    continue
                
                title = title_elem.text.strip()
                price = price_elem.text.strip() if price_elem else 'Цена не указана'
                
                img_url = None
                if img_elem:
                    img_url = img_elem.get('src')
                    if img_url and img_url.startswith('//'):
                        img_url = 'https:' + img_url
                
                href = link_elem.get('href') if link_elem else ''
                full_url = make_full_url('https://auctions.yahoo.co.jp', href)
                
                items.append({
                    'title': title[:100],
                    'price': price[:50],
                    'url': full_url,
                    'img_url': img_url,
                    'source': 'Yahoo Auction'
                })
            except Exception as e:
                logger.debug(f"Ошибка парсинга Yahoo Auction: {e}")
                continue
    except Exception as e:
        logger.error(f"Ошибка парсинга Yahoo Auction для {keyword}: {e}")
    
    return items

# ==================== YAHOO SHOPPING ====================
async def parse_yahoo_shopping_async(session, keyword, semaphore):
    """Асинхронный парсер Yahoo Shopping"""
    items = []
    url = f"https://shopping.yahoo.co.jp/search?p={quote(keyword)}&used=1&order=desc&sort=create_time"
    
    html = await fetch_html(session, url, semaphore)
    if not html:
        return items
    
    try:
        soup = BeautifulSoup(html, 'lxml')
        cards = soup.select('.Loop__item')[:ITEMS_PER_PAGE]
        
        for card in cards:
            try:
                title_elem = card.select_one('.Loop__itemTitle a')
                price_elem = card.select_one('.Loop__itemPrice')
                link_elem = card.select_one('a')
                img_elem = card.select_one('img')
                
                if not title_elem:
                    continue
                
                title = title_elem.text.strip()
                price = price_elem.text.strip() if price_elem else 'Цена не указана'
                
                img_url = None
                if img_elem:
                    img_url = img_elem.get('src')
                    if img_url and img_url.startswith('//'):
                        img_url = 'https:' + img_url
                
                href = link_elem.get('href') if link_elem else ''
                full_url = make_full_url('https://shopping.yahoo.co.jp', href)
                
                items.append({
                    'title': title[:100],
                    'price': price[:50],
                    'url': full_url,
                    'img_url': img_url,
                    'source': 'Yahoo Shopping'
                })
            except Exception as e:
                logger.debug(f"Ошибка парсинга Yahoo Shopping: {e}")
                continue
    except Exception as e:
        logger.error(f"Ошибка парсинга Yahoo Shopping для {keyword}: {e}")
    
    return items

# ==================== RAKUTEN MALL ====================
async def parse_rakuten_mall_async(session, keyword, semaphore):
    """Асинхронный парсер Rakuten Mall"""
    items = []
    url = f"https://search.rakuten.co.jp/search/mall/{quote(keyword)}/?used=1"
    
    html = await fetch_html(session, url, semaphore)
    if not html:
        # Пробуем альтернативный URL
        alt_url = f"https://search.rakuten.co.jp/search/mall/?v=2&p={quote(keyword)}&used=1"
        html = await fetch_html(session, alt_url, semaphore)
        if not html:
            return items
    
    try:
        soup = BeautifulSoup(html, 'lxml')
        cards = soup.select('.searchresultitem')[:ITEMS_PER_PAGE]
        
        for card in cards:
            try:
                title_elem = card.select_one('.title a')
                price_elem = card.select_one('.important')
                link_elem = card.select_one('a')
                img_elem = card.select_one('img')
                
                if not title_elem:
                    continue
                
                title = title_elem.text.strip()
                price = price_elem.text.strip() if price_elem else 'Цена не указана'
                
                img_url = None
                if img_elem:
                    img_url = img_elem.get('src')
                    if img_url and img_url.startswith('//'):
                        img_url = 'https:' + img_url
                
                href = link_elem.get('href') if link_elem else ''
                full_url = make_full_url('https://search.rakuten.co.jp', href)
                
                items.append({
                    'title': title[:100],
                    'price': price[:50],
                    'url': full_url,
                    'img_url': img_url,
                    'source': 'Rakuten Mall'
                })
            except Exception as e:
                logger.debug(f"Ошибка парсинга Rakuten Mall: {e}")
                continue
    except Exception as e:
        logger.error(f"Ошибка парсинга Rakuten Mall для {keyword}: {e}")
    
    return items

# ==================== EBAY ====================
async def parse_ebay_async(session, keyword, semaphore):
    """Асинхронный парсер eBay"""
    items = []
    url = f"https://www.ebay.com/sch/i.html?_nkw={quote(keyword)}&_sacat=11450&LH_ItemCondition=4&_sop=10"
    
    html = await fetch_html(session, url, semaphore)
    if not html:
        return items
    
    try:
        soup = BeautifulSoup(html, 'lxml')
        cards = soup.select('li.s-item')[:ITEMS_PER_PAGE]
        
        for card in cards:
            try:
                title_elem = card.select_one('.s-item__title')
                if not title_elem or 'Shop on' in title_elem.text:
                    continue
                
                price_elem = card.select_one('.s-item__price')
                link_elem = card.select_one('a.s-item__link')
                img_elem = card.select_one('.s-item__image-img')
                
                if not link_elem:
                    continue
                
                title = title_elem.text.strip()
                price = price_elem.text.strip() if price_elem else 'Цена не указана'
                
                img_url = None
                if img_elem:
                    img_url = img_elem.get('src')
                    if img_url and img_url.startswith('//'):
                        img_url = 'https:' + img_url
                
                href = link_elem.get('href').split('?')[0]
                
                items.append({
                    'title': title[:100],
                    'price': price[:50],
                    'url': href,
                    'img_url': img_url,
                    'source': 'eBay'
                })
            except Exception as e:
                logger.debug(f"Ошибка парсинга eBay: {e}")
                continue
    except Exception as e:
        logger.error(f"Ошибка парсинга eBay для {keyword}: {e}")
    
    return items

# ==================== 2ND STREET JP ====================
async def parse_2ndstreet_async(session, keyword, semaphore):
    """Асинхронный парсер 2nd Street JP"""
    items = []
    url = f"https://www.2ndstreet.jp/search?keyword={quote(keyword)}"
    
    html = await fetch_html(session, url, semaphore)
    if not html:
        return items
    
    try:
        soup = BeautifulSoup(html, 'lxml')
        cards = soup.select('.itemList .item')[:ITEMS_PER_PAGE]
        
        for card in cards:
            try:
                title_elem = card.select_one('.itemName')
                price_elem = card.select_one('.price')
                link_elem = card.select_one('a')
                img_elem = card.select_one('img')
                
                if not link_elem:
                    continue
                
                title = title_elem.text.strip() if title_elem else 'No title'
                price = price_elem.text.strip() if price_elem else 'Цена не указана'
                
                img_url = None
                if img_elem:
                    img_url = img_elem.get('src')
                    if img_url and img_url.startswith('//'):
                        img_url = 'https:' + img_url
                
                href = link_elem.get('href')
                full_url = make_full_url('https://www.2ndstreet.jp', href)
                
                items.append({
                    'title': title[:100],
                    'price': price[:50],
                    'url': full_url,
                    'img_url': img_url,
                    'source': '2nd Street JP'
                })
            except Exception as e:
                logger.debug(f"Ошибка парсинга 2nd Street: {e}")
                continue
    except Exception as e:
        logger.error(f"Ошибка парсинга 2nd Street для {keyword}: {e}")
    
    return items

# ==================== СЛОВАРЬ ПАРСЕРОВ ====================
ASYNC_PARSERS = {
    'Mercari JP': parse_mercari_async,
    'Rakuten Rakuma': parse_rakuma_async,
    'Yahoo Flea': parse_yahoo_flea_async,
    'Yahoo Auction': parse_yahoo_auction_async,
    'Yahoo Shopping': parse_yahoo_shopping_async,
    'Rakuten Mall': parse_rakuten_mall_async,
    'eBay': parse_ebay_async,
    '2nd Street JP': parse_2ndstreet_async,
}

# ==================== ОСНОВНАЯ ФУНКЦИЯ ПОИСКА ====================
async def search_all_async(keywords, platforms, max_concurrent=20):
    """
    Асинхронный поиск по всем платформам
    
    Args:
        keywords: список ключевых слов для поиска
        platforms: список платформ для поиска
        max_concurrent: максимальное количество одновременных запросов
    
    Returns:
        список найденных товаров
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    connector = aiohttp.TCPConnector(limit=100, limit_per_host=10, ttl_dns_cache=300, ssl=False)
    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = []
        for platform in platforms:
            if platform in ASYNC_PARSERS:
                parser = ASYNC_PARSERS[platform]
                for keyword in keywords:
                    tasks.append(parser(session, keyword, semaphore))
        
        logger.info(f"🚀 Запущено {len(tasks)} асинхронных задач")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Объединяем все результаты
        all_items = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Ошибка в асинхронной задаче: {result}")
            elif isinstance(result, list):
                all_items.extend(result)
        
        logger.info(f"✅ Асинхронный поиск завершен, найдено {len(all_items)} товаров")
        return all_items

# ==================== ФУНКЦИЯ ДЛЯ ЗАПУСКА ИЗ СИНХРОННОГО КОДА ====================
def run_async_search(keywords, platforms, max_concurrent=20):
    """
    Запускает асинхронный поиск из синхронного кода
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        items = loop.run_until_complete(search_all_async(keywords, platforms, max_concurrent))
        return items
    finally:
        loop.close()