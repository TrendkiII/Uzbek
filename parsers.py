import logging
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from config import ITEMS_PER_PAGE
from utils import make_request, safe_select, generate_item_id, encode_keyword, make_full_url

logger = logging.getLogger(__name__)

# ==================== Парсеры ====================

def parse_mercari_jp(keyword):
    items = []
    url = f"https://jp.mercari.com/search?keyword={encode_keyword(keyword)}"
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
            full_url = make_full_url('https://jp.mercari.com', href)
            items.append({
                'title': title.text.strip()[:100] if title else 'No title',
                'price': price.text.strip()[:50] if price else 'Цена не указана',
                'url': full_url,
                'img_url': img_url,
                'source': 'Mercari JP'
            })
        except Exception as e:
            logger.debug(f"Ошибка парсинга карточки Mercari: {e}")
            continue
    return items

def parse_ebay(keyword):
    items = []
    url = f"https://www.ebay.com/sch/i.html?_nkw={encode_keyword(keyword)}&_sacat=11450&LH_ItemCondition=4"
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
        except Exception as e:
            logger.debug(f"Ошибка парсинга карточки eBay: {e}")
            continue
    return items

def parse_2ndstreet_jp(keyword):
    items = []
    url = f"https://www.2ndstreet.jp/search?keyword={encode_keyword(keyword)}"
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
            full_url = make_full_url('https://www.2ndstreet.jp', href)
            items.append({
                'title': title.text.strip()[:100] if title else 'No title',
                'price': price.text.strip()[:50] if price else 'Цена не указана',
                'url': full_url,
                'img_url': img_url,
                'source': '2nd Street JP'
            })
        except Exception as e:
            logger.debug(f"Ошибка парсинга 2ndStreet: {e}")
            continue
    return items

def parse_rakuma(keyword):
    items = []
    url = f"https://fril.jp/s?query={encode_keyword(keyword)}"
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
            full_url = make_full_url('https://fril.jp', href)
            items.append({
                'title': title.text.strip()[:100],
                'price': price.text.strip()[:50] if price else 'Цена не указана',
                'url': full_url,
                'img_url': img_url,
                'source': 'Rakuten Rakuma'
            })
        except Exception as e:
            logger.debug(f"Ошибка парсинга Rakuma: {e}")
            continue
    return items

def parse_yahoo_flea(keyword):
    items = []
    url = f"https://paypayfleamarket.yahoo.co.jp/search/{encode_keyword(keyword)}"
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
            full_url = make_full_url('https://paypayfleamarket.yahoo.co.jp', href)
            items.append({
                'title': title.text.strip()[:100],
                'price': price.text.strip()[:50] if price else 'Цена не указана',
                'url': full_url,
                'img_url': img_url,
                'source': 'Yahoo Flea'
            })
        except Exception as e:
            logger.debug(f"Ошибка парсинга Yahoo Flea: {e}")
            continue
    return items

def parse_yahoo_auction(keyword):
    items = []
    url = f"https://auctions.yahoo.co.jp/search/search?p={encode_keyword(keyword)}&aq=-1&type=all"
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
            full_url = make_full_url('https://auctions.yahoo.co.jp', href)
            items.append({
                'title': title.text.strip()[:100],
                'price': price.text.strip()[:50] if price else 'Цена не указана',
                'url': full_url,
                'img_url': img_url,
                'source': 'Yahoo Auction'
            })
        except Exception as e:
            logger.debug(f"Ошибка парсинга Yahoo Auction: {e}")
            continue
    return items

def parse_yahoo_shopping(keyword):
    items = []
    url = f"https://shopping.yahoo.co.jp/search?p={encode_keyword(keyword)}&used=1"
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
            full_url = make_full_url('https://shopping.yahoo.co.jp', href)
            items.append({
                'title': title.text.strip()[:100],
                'price': price.text.strip()[:50] if price else 'Цена не указана',
                'url': full_url,
                'img_url': img_url,
                'source': 'Yahoo Shopping'
            })
        except Exception as e:
            logger.debug(f"Ошибка парсинга Yahoo Shopping: {e}")
            continue
    return items

def parse_rakuten_mall(keyword):
    items = []
    url = f"https://search.rakuten.co.jp/search/mall/{encode_keyword(keyword)}/?used=1"
    resp = make_request(url)
    if not resp:
        # альтернативный URL
        alt_url = f"https://search.rakuten.co.jp/search/mall/?v=2&p={encode_keyword(keyword)}&used=1"
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
            full_url = make_full_url('https://search.rakuten.co.jp', href)
            items.append({
                'title': title.text.strip()[:100],
                'price': price.text.strip()[:50] if price else 'Цена не указана',
                'url': full_url,
                'img_url': img_url,
                'source': 'Rakuten Mall'
            })
        except Exception as e:
            logger.debug(f"Ошибка парсинга Rakuten Mall: {e}")
            continue
    return items

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