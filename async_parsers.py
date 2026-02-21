import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import quote
from config import ITEMS_PER_PAGE, logger
from utils import (
    generate_item_id, make_full_url, get_next_user_agent,
    get_next_proxy_async, mark_proxy_bad_str
)
from playwright_manager import fetch_html_playwright

try:
    import brotli
except ImportError:
    logger.warning("Brotli not installed, some sites may fail. Run: pip install brotli")

# Глобальный семафор для ограничения общего числа параллельных запросов (HTTP + Playwright)
GLOBAL_SEMAPHORE = asyncio.Semaphore(10)

# Отдельный семафор для Playwright (чтобы не перегружать браузер)
PLAYWRIGHT_SEMAPHORE = asyncio.Semaphore(2)

async def fetch_html(session, url):
    """
    Выполняет HTTP-запрос через aiohttp с прокси и повторными попытками.
    Использует глобальный семафор.
    """
    async with GLOBAL_SEMAPHORE:
        headers = {
            'User-Agent': get_next_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        for attempt in range(3):
            proxy = await get_next_proxy_async()
            try:
                async with session.get(url, headers=headers, proxy=proxy, timeout=15, ssl=False) as response:
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
            await asyncio.sleep(2 ** attempt)
        return None

async def fetch_with_fallback(session, url, expected_selector=None, use_playwright=True):
    """
    Пытается сначала загрузить страницу через HTTP. Если не удаётся или нет селектора,
    использует Playwright (с отдельным семафором).
    """
    html = await fetch_html(session, url)
    if html:
        if expected_selector:
            soup = BeautifulSoup(html, 'lxml')
            if soup.select_one(expected_selector):
                return html
            else:
                logger.warning(f"⚠️ Быстрый запрос успешен, но селектор '{expected_selector}' не найден. Пробую Playwright.")
        else:
            return html

    if use_playwright:
        async with PLAYWRIGHT_SEMAPHORE:
            async with GLOBAL_SEMAPHORE:
                logger.info(f"🔄 Fallback to Playwright for {url[:100]}...")
                html = await fetch_html_playwright(url, expected_selector=expected_selector)
                return html
    return None

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

# ==================== Парсеры для каждой площадки ====================

async def parse_mercari_async(session, keyword):
    items = []
    url = f"https://jp.mercari.com/search?keyword={quote(keyword)}&order=desc&sort=created_time"
    html = await fetch_with_fallback(session, url, expected_selector='[data-testid="item-cell"]')
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

async def parse_rakuma_async(session, keyword):
    items = []
    url = f"https://fril.jp/s?query={quote(keyword)}&order=desc&sort=created_at"
    html = await fetch_with_fallback(session, url, expected_selector='.item')
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

async def parse_yahoo_flea_async(session, keyword):
    items = []
    url = f"https://paypayfleamarket.yahoo.co.jp/search/{quote(keyword)}?order=desc&sort=create_time"
    html = await fetch_with_fallback(session, url, expected_selector='.Product')
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

async def parse_yahoo_auction_async(session, keyword):
    items = []
    url = f"https://auctions.yahoo.co.jp/search/search?p={quote(keyword)}&aq=-1&type=all&auccat=&tab_ex=commerce&order=desc"
    html = await fetch_with_fallback(session, url, expected_selector='.Product')
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

async def parse_yahoo_shopping_async(session, keyword):
    items = []
    url = f"https://shopping.yahoo.co.jp/search?p={quote(keyword)}&used=1&order=desc&sort=create_time"
    html = await fetch_with_fallback(session, url, expected_selector='.Loop__item')
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

async def parse_rakuten_mall_async(session, keyword):
    items = []
    encoded = quote(keyword, safe='')
    url = f"https://search.rakuten.co.jp/search/mall/{encoded}/?used=1"
    html = await fetch_with_fallback(session, url, expected_selector='.searchresultitem')
    if not html:
        alt_url = f"https://search.rakuten.co.jp/search/mall/?v=2&p={encoded}&used=1"
        html = await fetch_with_fallback(session, alt_url, expected_selector='.searchresultitem')
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

async def parse_ebay_async(session, keyword):
    items = []
    url = f"https://www.ebay.com/sch/i.html?_nkw={quote(keyword)}&_sacat=11450&LH_ItemCondition=4&_sop=10"
    html = await fetch_with_fallback(session, url, expected_selector='li.s-item')
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

async def parse_2ndstreet_async(session, keyword):
    items = []
    url = f"https://www.2ndstreet.jp/search?keyword={quote(keyword)}"
    html = await fetch_with_fallback(session, url, expected_selector='.itemList .item')
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

# ==================== Словарь парсеров ====================
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

# ==================== Функция с очередью и воркерами ====================
async def worker(queue, session, results):
    while True:
        task = await queue.get()
        if task is None:
            break
        platform, keyword = task
        parser = ASYNC_PARSERS.get(platform)
        if parser:
            try:
                items = await parser(session, keyword)
                results.extend(items)
            except Exception as e:
                logger.error(f"Ошибка при обработке {platform}/{keyword}: {e}")
        queue.task_done()

async def search_all_async(keywords, platforms, max_workers=5):
    queue = asyncio.Queue()
    results = []

    for platform in platforms:
        if platform not in ASYNC_PARSERS:
            continue
        for keyword in keywords:
            await queue.put((platform, keyword))

    connector = aiohttp.TCPConnector(limit=100, limit_per_host=5, ttl_dns_cache=300, ssl=False)
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        workers = [asyncio.create_task(worker(queue, session, results)) for _ in range(max_workers)]
        await queue.join()
        for _ in workers:
            await queue.put(None)
        await asyncio.gather(*workers)

    logger.info(f"✅ Асинхронный поиск завершен, найдено {len(results)} товаров")
    return results

# ==================== Функция для запуска из синхронного кода ====================
def run_async_search(keywords, platforms, max_workers=5):
    from async_loop import run_coro
    future = run_coro(search_all_async(keywords, platforms, max_workers))
    return future.result()