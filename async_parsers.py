import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import quote
from config import ITEMS_PER_PAGE, logger
import time

from utils import (
    generate_item_id, make_full_url, get_next_user_agent,
    get_next_proxy_async, mark_proxy_bad_str
)

async def fetch_html(session, url, semaphore, timeout=15, retries=3):
    """
    Асинхронно получает HTML страницы с поддержкой прокси и повторными попытками.
    """
    async with semaphore:
        headers = {
            'User-Agent': get_next_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        for attempt in range(retries):
            proxy = await get_next_proxy_async()  # получаем свежий прокси на каждую попытку
            try:
                async with session.get(url, headers=headers, proxy=proxy, timeout=timeout, ssl=False) as response:
                    if response.status == 200:
                        return await response.text()
                    elif response.status in [403, 404]:
                        logger.warning(f"🚫 {response.status} для {url[:100]}...")
                        return None
                    else:
                        logger.warning(f"🌐 HTTP {response.status} для {url[:100]}...")
            except asyncio.TimeoutError:
                logger.warning(f"⏰ Таймаут (попытка {attempt+1}) для {url[:100]}...")
            except aiohttp.ClientProxyConnectionError as e:
                logger.warning(f"🔌 Ошибка прокси {proxy} (попытка {attempt+1}): {e}")
                if proxy:
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, mark_proxy_bad_str, proxy)
            except aiohttp.ClientConnectorError as e:
                logger.warning(f"🔌 Ошибка подключения (попытка {attempt+1}): {e}")
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки {url[:100]}: {e}")
            
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)  # экспоненциальная задержка
        return None

# ==================== Вспомогательная функция для извлечения данных из карточки ====================
def extract_item_from_card(card, source, base_url, title_sel, price_sel, link_sel='a', img_sel='img'):
    try:
        title_elem = card.select_one(title_sel)
        price_elem = card.select_one(price_sel)
        link_elem = card.select_one(link_sel)
        img_elem = card.select_one(img_sel) if img_sel else None

        if not title_elem or not link_elem:
            return None

        title = title_elem.text.strip()
        price = price_elem.text.strip() if price_elem else 'Цена не указана'

        img_url = None
        if img_elem:
            img_url = img_elem.get('src')
            if img_url and img_url.startswith('//'):
                img_url = 'https:' + img_url

        href = link_elem.get('href')
        full_url = make_full_url(base_url, href)

        return {
            'title': title[:100],
            'price': price[:50],
            'url': full_url,
            'img_url': img_url,
            'source': source
        }
    except Exception as e:
        logger.debug(f"Ошибка парсинга карточки {source}: {e}")
        return None

# ==================== MERCARI JP ====================
async def parse_mercari_async(session, keyword, semaphore):
    items = []
    url = f"https://jp.mercari.com/search?keyword={quote(keyword)}&order=desc&sort=created_time"
    html = await fetch_html(session, url, semaphore)
    if not html:
        return items
    try:
        soup = BeautifulSoup(html, 'lxml')
        cards = soup.select('[data-testid="item-cell"]')[:ITEMS_PER_PAGE]
        for card in cards:
            item_data = extract_item_from_card(
                card,
                source='Mercari JP',
                base_url='https://jp.mercari.com',
                title_sel='[data-testid="thumbnail-title"]',
                price_sel='[data-testid="price"]',
                link_sel='a',
                img_sel='img'
            )
            if item_data:
                item_data['id'] = generate_item_id(item_data)
                items.append(item_data)
    except Exception as e:
        logger.error(f"Ошибка парсинга Mercari для {keyword}: {e}")
    return items

# ==================== RAKUTEN RAKUMA ====================
async def parse_rakuma_async(session, keyword, semaphore):
    items = []
    url = f"https://fril.jp/s?query={quote(keyword)}&order=desc&sort=created_at"
    html = await fetch_html(session, url, semaphore)
    if not html:
        return items
    try:
        soup = BeautifulSoup(html, 'lxml')
        cards = soup.select('.item')[:ITEMS_PER_PAGE]
        for card in cards:
            item_data = extract_item_from_card(
                card,
                source='Rakuten Rakuma',
                base_url='https://fril.jp',
                title_sel='.item-box__title a',
                price_sel='.item-box__price',
                link_sel='a',
                img_sel='img'
            )
            if item_data:
                item_data['id'] = generate_item_id(item_data)
                items.append(item_data)
    except Exception as e:
        logger.error(f"Ошибка парсинга Rakuma для {keyword}: {e}")
    return items

# ==================== YAHOO FLEA ====================
async def parse_yahoo_flea_async(session, keyword, semaphore):
    items = []
    url = f"https://paypayfleamarket.yahoo.co.jp/search/{quote(keyword)}?order=desc&sort=create_time"
    html = await fetch_html(session, url, semaphore)
    if not html:
        return items
    try:
        soup = BeautifulSoup(html, 'lxml')
        cards = soup.select('.Product')[:ITEMS_PER_PAGE]
        for card in cards:
            item_data = extract_item_from_card(
                card,
                source='Yahoo Flea',
                base_url='https://paypayfleamarket.yahoo.co.jp',
                title_sel='.Product__titleLink',
                price_sel='.Product__price',
                link_sel='a',
                img_sel='img'
            )
            if item_data:
                item_data['id'] = generate_item_id(item_data)
                items.append(item_data)
    except Exception as e:
        logger.error(f"Ошибка парсинга Yahoo Flea для {keyword}: {e}")
    return items

# ==================== YAHOO AUCTION ====================
async def parse_yahoo_auction_async(session, keyword, semaphore):
    items = []
    url = f"https://auctions.yahoo.co.jp/search/search?p={quote(keyword)}&aq=-1&type=all&auccat=&tab_ex=commerce&order=desc"
    html = await fetch_html(session, url, semaphore)
    if not html:
        return items
    try:
        soup = BeautifulSoup(html, 'lxml')
        cards = soup.select('.Product')[:ITEMS_PER_PAGE]
        for card in cards:
            item_data = extract_item_from_card(
                card,
                source='Yahoo Auction',
                base_url='https://auctions.yahoo.co.jp',
                title_sel='.Product__titleLink',
                price_sel='.Product__price',
                link_sel='a',
                img_sel='img'
            )
            if item_data:
                item_data['id'] = generate_item_id(item_data)
                items.append(item_data)
    except Exception as e:
        logger.error(f"Ошибка парсинга Yahoo Auction для {keyword}: {e}")
    return items

# ==================== YAHOO SHOPPING ====================
async def parse_yahoo_shopping_async(session, keyword, semaphore):
    items = []
    url = f"https://shopping.yahoo.co.jp/search?p={quote(keyword)}&used=1&order=desc&sort=create_time"
    html = await fetch_html(session, url, semaphore)
    if not html:
        return items
    try:
        soup = BeautifulSoup(html, 'lxml')
        cards = soup.select('.Loop__item')[:ITEMS_PER_PAGE]
        for card in cards:
            item_data = extract_item_from_card(
                card,
                source='Yahoo Shopping',
                base_url='https://shopping.yahoo.co.jp',
                title_sel='.Loop__itemTitle a',
                price_sel='.Loop__itemPrice',
                link_sel='a',
                img_sel='img'
            )
            if item_data:
                item_data['id'] = generate_item_id(item_data)
                items.append(item_data)
    except Exception as e:
        logger.error(f"Ошибка парсинга Yahoo Shopping для {keyword}: {e}")
    return items

# ==================== RAKUTEN MALL ====================
async def parse_rakuten_mall_async(session, keyword, semaphore):
    items = []
    url = f"https://search.rakuten.co.jp/search/mall/{quote(keyword)}/?used=1"
    html = await fetch_html(session, url, semaphore)
    if not html:
        alt_url = f"https://search.rakuten.co.jp/search/mall/?v=2&p={quote(keyword)}&used=1"
        html = await fetch_html(session, alt_url, semaphore)
        if not html:
            return items
    try:
        soup = BeautifulSoup(html, 'lxml')
        cards = soup.select('.searchresultitem')[:ITEMS_PER_PAGE]
        for card in cards:
            item_data = extract_item_from_card(
                card,
                source='Rakuten Mall',
                base_url='https://search.rakuten.co.jp',
                title_sel='.title a',
                price_sel='.important',
                link_sel='a',
                img_sel='img'
            )
            if item_data:
                item_data['id'] = generate_item_id(item_data)
                items.append(item_data)
    except Exception as e:
        logger.error(f"Ошибка парсинга Rakuten Mall для {keyword}: {e}")
    return items

# ==================== EBAY ====================
async def parse_ebay_async(session, keyword, semaphore):
    items = []
    url = f"https://www.ebay.com/sch/i.html?_nkw={quote(keyword)}&_sacat=11450&LH_ItemCondition=4&_sop=10"
    html = await fetch_html(session, url, semaphore)
    if not html:
        return items
    try:
        soup = BeautifulSoup(html, 'lxml')
        cards = soup.select('li.s-item')[:ITEMS_PER_PAGE]
        for card in cards:
            title_elem = card.select_one('.s-item__title')
            if not title_elem or 'Shop on' in title_elem.text:
                continue
            item_data = extract_item_from_card(
                card,
                source='eBay',
                base_url='https://www.ebay.com',
                title_sel='.s-item__title',
                price_sel='.s-item__price',
                link_sel='a.s-item__link',
                img_sel='.s-item__image-img'
            )
            if item_data:
                item_data['id'] = generate_item_id(item_data)
                items.append(item_data)
    except Exception as e:
        logger.error(f"Ошибка парсинга eBay для {keyword}: {e}")
    return items

# ==================== 2ND STREET JP ====================
async def parse_2ndstreet_async(session, keyword, semaphore):
    items = []
    url = f"https://www.2ndstreet.jp/search?keyword={quote(keyword)}"
    html = await fetch_html(session, url, semaphore)
    if not html:
        return items
    try:
        soup = BeautifulSoup(html, 'lxml')
        cards = soup.select('.itemList .item')[:ITEMS_PER_PAGE]
        for card in cards:
            item_data = extract_item_from_card(
                card,
                source='2nd Street JP',
                base_url='https://www.2ndstreet.jp',
                title_sel='.itemName',
                price_sel='.price',
                link_sel='a',
                img_sel='img'
            )
            if item_data:
                item_data['id'] = generate_item_id(item_data)
                items.append(item_data)
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
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        items = loop.run_until_complete(search_all_async(keywords, platforms, max_concurrent))
        return items
    finally:
        loop.close()