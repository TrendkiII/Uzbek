import hashlib
import time
import random
from urllib.parse import urljoin, quote
from bs4 import BeautifulSoup
from config import USER_AGENTS_POOL, get_next_user_agent, PROXY, REQUEST_TIMEOUT, MAX_RETRIES, RETRY_DELAY
import requests
import logging

logger = logging.getLogger(__name__)

# ================== Генерация уникального ID для товара ==================
def generate_item_id(item):
    """
    Формирует уникальный ID на основе source, url и title.
    """
    unique = f"{item['source']}_{item['url']}_{item['title']}"
    return hashlib.md5(unique.encode('utf-8')).hexdigest()

# ================== Безопасный CSS селектор ==================
def safe_select(element, selectors):
    """
    Пробует список селекторов и возвращает первый найденный элемент.
    Если ничего не найдено, возвращает None.
    """
    for sel in selectors:
        elem = element.select_one(sel)
        if elem:
            return elem
    return None

# ================== Безопасные HTTP-запросы ==================
def make_request(url, headers=None, timeout=REQUEST_TIMEOUT, retries=MAX_RETRIES):
    """
    Делает GET-запрос с повторами, ротацией User-Agent и поддержкой прокси.
    Возвращает объект Response или None.
    """
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
                headers['User-Agent'] = get_next_user_agent()
            else:
                logger.warning(f"HTTP ошибка {attempt+1}/{retries} для {url}: {e}")
        except Exception as e:
            logger.warning(f"Ошибка {attempt+1}/{retries} для {url}: {e}")

        if attempt < retries - 1:
            time.sleep(RETRY_DELAY * (attempt + 1))
    return None

# ================== URL вспомогательные ==================
def make_full_url(base, href):
    """
    Превращает относительный href в абсолютный URL.
    """
    if not href:
        return ''
    if href.startswith('http'):
        return href
    return urljoin(base, href)

def encode_keyword(keyword):
    """
    Кодирует ключевое слово для URL (например для японских символов)
    """
    return quote(keyword)