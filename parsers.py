import requests
from bs4 import BeautifulSoup
from urllib.parse import quote, urljoin
import random
import time
import logging
from config import REQUEST_TIMEOUT, MAX_RETRIES, RETRY_DELAY, ITEMS_PER_PAGE, PROXY
from brands import ALL_PLATFORMS
import hashlib
from fake_useragent import UserAgent

# ================= User-Agent =================
ua = UserAgent()
USER_AGENTS = [ua.random for _ in range(20)]
UA_INDEX = 0

def get_next_user_agent():
    global UA_INDEX
    ua = USER_AGENTS[UA_INDEX % len(USER_AGENTS)]
    UA_INDEX += 1
    return ua

# ================= Logging ====================
logger = logging.getLogger(__name__)

# ==================== HTTP запросы ====================
def make_request(url, headers=None, timeout=REQUEST_TIMEOUT, retries=MAX_RETRIES):
    if headers is None:
        headers = {'User-Agent': get_next_user_agent()}
    proxies = {'http': PROXY, 'https': PROXY} if PROXY else None
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout, proxies=proxies)
            r.raise_for_status()
            return r
        except requests.exceptions.Timeout:
            logger.warning(f"Таймаут {attempt+1}/{retries} для {url}")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                logger.warning(f"403 Forbidden: {url} – меняем User-Agent")
                headers = {'User-Agent': get_next_user_agent()}
            else:
                logger.warning(f"HTTP ошибка {attempt+1}/{retries} для {url}: {e}")
        except Exception as e:
            logger.warning(f"Ошибка {attempt+1}/{retries} для {url}: {e}")
        if attempt < retries - 1:
            time.sleep(RETRY_DELAY * (attempt + 1))
    return None

# ==================== Helpers ====================
def safe_select(element, selectors):
    for sel in selectors:
        elem = element.select_one(sel)
        if elem:
            return elem
    return None

def generate_item_id(item):
    unique = f"{item['source']}_{item['url']}_{item['title']}"
    return hashlib.md5(unique.encode('utf-8')).hexdigest()

# ==================== Парсеры ====================

# --- Mercari JP ---
def parse_mercari_jp(keyword):
    items = []
    url = f"https://jp.mercari.com/search?keyword={quote(keyword)}"
    resp = make_request(url)
    if not resp:
        return items
    soup = BeautifulSoup(resp.text, 'lxml')
    cards = soup.select('[data-testid="item-cell"]')[:ITEMS_PER_PAGE]
    for card in cards:
        try:
            title = safe_select(card, ['[data-testid="thumbnail-title"]'])
            price = safe_select(card, ['[data-testid="price"]'])
            link = card.select_one('a')
            img = card.select_one('img')
            if not link:
                continue
            img_url = img.get('src') if img else None
            if img_url and img_url.startswith('//'):
                img_url = 'https:' + img_url
            href = link.get('href')
            full_url = urljoin('https://jp.mercari.com', href) if href else ''
            items.append({
                'title': title.text.strip()[:100] if title else 'No title',
                'price': price.text.strip()[:50] if price else 'Цена не указана',
                'url': full_url,
                'img_url': img_url,
                'source': 'Mercari JP'
            })
        except Exception:
            continue
    return items

# --- eBay ---
def parse_ebay(keyword):
    items = []
    url = f"https://www.ebay.com/sch/i.html?_nkw={quote(keyword)}&_sacat=11450&LH_ItemCondition=4"
    resp = make_request(url)
    if not resp:
        return items
    soup = BeautifulSoup(resp.text, 'lxml')
    cards = soup.select('li.s-item')[:ITEMS_PER_PAGE]
    for card in cards:
        try:
            title = safe_select(card, ['.s-item__title', '.s-item__title span'])
            if not title or 'Shop on' in title.text:
                continue
            price = safe_select(card, ['.s-item__price', '.s-item__price span'])
            link = card.select_one('a.s-item__link')
            img = card.select_one('.s-item__image-img')
            if not link:
                continue
            img_url = img.get('src') if img else None
            if img_url and img_url.startswith('//'):
                img_url = 'https:' + img_url
            href = link.get('href').split('?')[0]
            items.append({
                'title': title.text.strip()[:100],
                'price': price.text.strip()[:50] if price else 'Цена не указана',
                'url': href,
                'img_url': img_url,
                'source': 'eBay'
            })
        except Exception:
            continue
    return items

# --- 2nd Street JP ---
def parse_2ndstreet_jp(keyword):
    items = []
    url = f"https://www.2ndstreet.jp/search?keyword={quote(keyword)}"
    resp = make_request(url)
    if not resp:
        return items
    soup = BeautifulSoup(resp.text, 'lxml')
    cards = soup.select('.itemList .item')[:ITEMS_PER_PAGE]
    for card in cards:
        try:
            title = card.select_one('.itemName')
            price = card.select_one('.price')
            link = card.select_one('a')
            img = card.select_one('img')
            if not link:
                continue
            img_url = img.get('src') if img else None
            if img_url and img_url.startswith('//'):
                img_url = 'https:' + img_url
            href = link.get('href')
            full_url = urljoin('https://www.2ndstreet.jp', href) if href else ''
            items.append({
                'title': title.text.strip()[:100] if title else 'No title',
                'price': price.text.strip()[:50] if price else 'Цена не указана',
                'url': full_url,
                'img_url': img_url,
                'source': '2nd Street JP'
            })
        except Exception:
            continue
    return items

# --- Rakuten Rakuma ---
def parse_rakuma(keyword):
    items = []
    url = f"https://fril.jp/s?query={quote(keyword)}"
    resp = make_request(url)
    if not resp:
        return items
    soup = BeautifulSoup(resp.text, 'lxml')
    cards = soup.select('.item')[:ITEMS_PER_PAGE]
    for card in cards:
        try:
            title = card.select_one('.item-box__title a')
            price = card.select_one('.item-box__price')
            link = card.select_one('a')
            img = card.select_one('img')
            if not title or not link:
                continue
            img_url = img.get('src') if img else None
            if img_url and img_url.startswith('//'):
                img_url = 'https:' + img_url
            href = link.get('href')
            full_url = urljoin('https://fril.jp', href) if href else ''
            items.append({
                'title': title.text.strip()[:100],
                'price': price.text.strip()[:50] if price else 'Цена не указана',
                'url': full_url,
                'img_url': img_url,
                'source': 'Rakuten Rakuma'
            })
        except Exception:
            continue
    return items

# --- Yahoo Flea ---
def parse_yahoo_flea(keyword):
    items = []
    url = f"https://paypayfleamarket.yahoo.co.jp/search/{quote(keyword)}"
    resp = make_request(url)
    if not resp:
        return items
    soup = BeautifulSoup(resp.text, 'lxml')
    cards = soup.select('.Product')[:ITEMS_PER_PAGE]
    for card in cards:
        try:
            title = card.select_one('.Product__titleLink')
            price = card.select_one('.Product__price')
            link = card.select_one('a')
            img = card.select_one('img')
            if not title:
                continue
            img_url = img.get('src') if img else None
            if img_url and img_url.startswith('//'):
                img_url = 'https:' + img_url
            href = link.get('href') if link else ''
            full_url = urljoin('https://paypayfleamarket.yahoo.co.jp', href) if href else ''
            items.append({
                'title': title.text.strip()[:100],
                'price': price.text.strip()[:50] if price else 'Цена не указана',
                'url': full_url,
                'img_url': img_url,
                'source': 'Yahoo Flea'
            })
        except Exception:
            continue
    return items

# --- Yahoo Auction ---
def parse_yahoo_auction(keyword):
    items = []
    url = f"https://auctions.yahoo.co.jp/search/search?p={quote(keyword)}&aq=-1&type=all"
    resp = make_request(url)
    if not resp:
        return items
    soup = BeautifulSoup(resp.text, 'lxml')
    cards = soup.select('.Product')[:ITEMS_PER_PAGE]
    for card in cards:
        try:
            title = card.select_one('.Product__titleLink')
            price = card.select_one('.Product__price')
            link = card.select_one('a')
            img = card.select_one('img')
            if not title:
                continue
            img_url = img.get('src') if img else None
            if img_url and img_url.startswith('//'):
                img_url = 'https:' + img_url
            href = link.get('href') if link else ''
            full_url = urljoin('https://auctions.yahoo.co.jp', href) if href else ''
            items.append({
                'title': title.text.strip()[:100],
                'price': price.text.strip()[:50] if price else 'Цена не указана',
                'url': full_url,
                'img_url': img_url,
                'source': 'Yahoo Auction'
            })
        except Exception:
            continue
    return items

# --- Yahoo Shopping ---
def parse_yahoo_shopping(keyword):
    items = []
    url = f"https://shopping.yahoo.co.jp/search?p={quote(keyword)}&used=1"
    resp = make_request(url)
    if not resp:
        return items
    soup = BeautifulSoup(resp.text, 'lxml')
    cards = soup.select('.Loop__item')[:ITEMS_PER_PAGE]
    for card in cards:
        try:
            title = card.select_one('.Loop__itemTitle a')
            price = card.select_one('.Loop__itemPrice')
            link = card.select_one('a')
            img = card.select_one('img')
            if not title:
                continue
            img_url = img.get('src') if img else None
            if img_url and img_url.startswith('//'):
                img_url = 'https:' + img_url
            href = link.get('href') if link else ''
            full_url = urljoin('https://shopping.yahoo.co.jp', href) if href else ''
            items.append({
                'title': title.text.strip()[:100],
                'price': price.text.strip()[:50] if price else 'Цена не указана',
                'url': full_url,
                'img_url': img_url,
                'source': 'Yahoo Shopping'
            })
        except Exception:
            continue
    return items

# --- Rakuten Mall ---
def parse_rakuten_mall(keyword):
    items = []
    url = f"https://search.rakuten.co.jp/search/mall/{quote(keyword)}/?used=1"
    resp = make_request(url)
    if not resp:
        # альтернативный URL
        alt_url = f"https://search.rakuten.co.jp/search/mall/?v=2&p={quote(keyword)}&used=1"
        resp = make_request(alt_url)
        if not resp:
            return items
    soup = BeautifulSoup(resp.text, 'lxml')
    cards = soup.select('.searchresultitem')[:ITEMS_PER_PAGE]
    for card in cards:
        try:
            title = card.select_one('.title a')
            price = card.select_one('.important')
            link = card.select_one('a')
            img = card.select_one('img')
            if not title:
                continue
            img_url = img.get('src') if img else None
            if img_url and img_url.startswith('//'):
                img_url = 'https:' + img_url
            href = link.get('href') if link else ''
            full_url = urljoin('https://search.rakuten.co.jp', href) if href else ''
            items.append({
                'title': title.text.strip()[:100],
                'price': price.text.strip()[:50] if price else 'Цена не указана',
                'url': full_url,
                'img_url': img_url,
                'source': 'Rakuten Mall'
            })
        except Exception:
            continue
    return items

# ===== Словарь всех парсеров =====
PARSERS = {
    'Mercari JP': parse_mercari_jp,
    'Rakuten Rakuma': parse_rakuma,
    'Yahoo Flea': parse_yahoo_flea,
    'Yahoo Auction': parse_yahoo_auction,
    'Yahoo Shopping': parse_yahoo_shopping,
    'Rakuten Mall': parse_rakuten_mall,
    'eBay': parse_ebay,
    '2nd Street JP': parse_2ndstreet_jp
}