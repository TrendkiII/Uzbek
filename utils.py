import hashlib
import time
import random
import requests
import logging
from urllib.parse import urljoin, quote
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from config import PROXY, REQUEST_TIMEOUT, MAX_RETRIES, RETRY_DELAY

logger = logging.getLogger(__name__)

# ================== Управление User-Agent ==================
ua = UserAgent()
USER_AGENTS = [ua.random for _ in range(20)]
UA_INDEX = 0

def get_next_user_agent():
    global UA_INDEX
    agent = USER_AGENTS[UA_INDEX % len(USER_AGENTS)]
    UA_INDEX += 1
    return agent

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

# ================== Telegram-отправка (базовые функции) ==================
# Эти функции будут переопределены в telegram_bot.py, но здесь они могут использоваться для тестов
def send_telegram_message(text, photo_url=None, keyboard=None, chat_id=None):
    """Заглушка, должна быть заменена в telegram_bot.py"""
    logger.warning("send_telegram_message не реализована")