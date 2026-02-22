import hashlib
import time
import random
import requests
import logging
from urllib.parse import urljoin

# ============== ДОБАВЛЯЕМ ЛОГГЕР ==============
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def get_next_user_agent():
    agents = [
        'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (Linux; Android 13; SM-S901B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Mobile Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
    ]
    return random.choice(agents)

def generate_item_id(item):
    unique = f"{item.get('source', 'unknown')}_{item.get('url', '')}_{item.get('title', '')}"
    return hashlib.md5(unique.encode()).hexdigest()

def make_full_url(base, href):
    if not href:
        return ''
    if href.startswith('http'):
        return href
    return urljoin(base, href)

# ============== ДОБАВЛЯЕМ ФУНКЦИЮ ДЛЯ ФОРМАТИРОВАНИЯ ЧИСЕЛ ==============
def format_number(num):
    """Форматирует число с разделителями тысяч"""
    try:
        return f"{int(num):,}".replace(",", " ")
    except:
        return str(num)