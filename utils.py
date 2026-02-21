import hashlib
import time
import random
import requests
import logging
import json
from urllib.parse import urljoin, quote
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from threading import Lock
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import (
    PROXY_POOL, USE_PROXY_POOL, proxy_lock, PROXY_FILE,
    REQUEST_TIMEOUT, MAX_RETRIES, RETRY_DELAY,
    USER_AGENTS_COUNT, BROWSER_HEADERS,
    MIN_DELAY_BETWEEN_REQUESTS, MAX_DELAY_BETWEEN_REQUESTS,
    MIN_DELAY_BETWEEN_BRANDS, MAX_DELAY_BETWEEN_BRANDS,
    REQUESTS_BEFORE_PROXY_CHANGE
)

logger = logging.getLogger(__name__)

# ================== User-Agent ==================
ua = UserAgent()
USER_AGENTS = [ua.random for _ in range(USER_AGENTS_COUNT)]
UA_INDEX = 0
ua_lock = Lock()

def get_next_user_agent():
    with ua_lock:
        global UA_INDEX
        agent = USER_AGENTS[UA_INDEX % len(USER_AGENTS)]
        UA_INDEX += 1
        return agent

# ================== Прокси с поддержкой разных протоколов ==================
request_counter = 0
current_proxy_index = 0
bad_proxies = set()

def load_proxies_from_file():
    try:
        with open(PROXY_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_proxies_to_file(proxies):
    with open(PROXY_FILE, 'w') as f:
        json.dump(proxies, f, indent=2)

def init_proxy_pool():
    global PROXY_POOL
    with proxy_lock:
        PROXY_POOL = load_proxies_from_file()
        logger.info(f"📦 Загружено {len(PROXY_POOL)} прокси из файла")

def add_proxy_to_pool(proxy_url):
    with proxy_lock:
        if proxy_url not in PROXY_POOL:
            PROXY_POOL.append(proxy_url)
            save_proxies_to_file(PROXY_POOL)
            logger.info(f"✅ Добавлен прокси: {proxy_url}")
            return True
    return False

def remove_proxy_from_pool(proxy_url):
    with proxy_lock:
        if proxy_url in PROXY_POOL:
            PROXY_POOL.remove(proxy_url)
            save_proxies_to_file(PROXY_POOL)
            logger.info(f"🗑 Удалён прокси: {proxy_url}")
            return True
    return False

def test_proxy(proxy_url):
    """Синхронная проверка одного прокси"""
    proxies = {'http': proxy_url, 'https': proxy_url}
    try:
        start = time.time()
        r = requests.get('http://httpbin.org/ip', proxies=proxies, timeout=10)
        if r.status_code == 200:
            elapsed = time.time() - start
            return proxy_url, True, r.json().get('origin'), round(elapsed, 2)
    except:
        pass
    return proxy_url, False, None, None

async def test_proxy_async(proxy_url):
    """Асинхронная проверка одного прокси (запускает синхронную в executor)"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, test_proxy, proxy_url)

def check_and_update_proxies(proxy_list=None):
    """Проверяет список прокси и обновляет пул (синхронно, многопоточно)"""
    if proxy_list is None:
        with proxy_lock:
            proxy_list = PROXY_POOL.copy()
    
    if not proxy_list:
        return []
    
    working = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(test_proxy, p): p for p in proxy_list}
        for future in as_completed(futures):
            proxy, ok, ip, speed = future.result()
            if ok:
                working.append(proxy)
                logger.info(f"✅ {proxy} работает (IP: {ip}, {speed}с)")
            else:
                logger.warning(f"❌ {proxy} не работает")
    
    if proxy_list is PROXY_POOL or proxy_list == PROXY_POOL:
        with proxy_lock:
            PROXY_POOL[:] = working
            global bad_proxies
            bad_proxies.clear()
            save_proxies_to_file(PROXY_POOL)
    
    return working

def get_next_proxy():
    if not USE_PROXY_POOL or not PROXY_POOL:
        return None
    
    with proxy_lock:
        global request_counter, current_proxy_index
        available_proxies = [p for p in PROXY_POOL if p not in bad_proxies]
        if not available_proxies:
            logger.warning("⚠️ Нет доступных прокси!")
            return None
        if request_counter >= REQUESTS_BEFORE_PROXY_CHANGE:
            current_proxy_index = (current_proxy_index + 1) % len(available_proxies)
            request_counter = 0
            logger.info(f"🔄 Смена прокси на {available_proxies[current_proxy_index]}")
        proxy_url = available_proxies[current_proxy_index]
        request_counter += 1
        return {'http': proxy_url, 'https': proxy_url}

def mark_proxy_bad(proxy_dict):
    if not proxy_dict:
        return
    with proxy_lock:
        for p in PROXY_POOL:
            proxy_url = proxy_dict.get('http', '')
            if proxy_url and proxy_url in p:
                bad_proxies.add(p)
                logger.warning(f"🗑 Прокси {p} помечен как неработающий")
                break

def mark_proxy_bad_str(proxy_str):
    """Помечает прокси как нерабочий по строке (для асинхронного кода)"""
    with proxy_lock:
        if proxy_str in PROXY_POOL:
            bad_proxies.add(proxy_str)
            logger.warning(f"🗑 Прокси {proxy_str} помечен как неработающий (асинхронно)")

def get_proxy_stats():
    with proxy_lock:
        return {
            'total': len(PROXY_POOL),
            'bad': len(bad_proxies),
            'good': len(PROXY_POOL) - len(bad_proxies),
            'current_index': current_proxy_index,
            'requests_this_proxy': request_counter
        }

# ================== Асинхронное получение прокси ==================
async def get_next_proxy_async():
    """Асинхронно возвращает следующий прокси из пула (с блокировкой)"""
    global request_counter, current_proxy_index
    with proxy_lock:
        if not PROXY_POOL:
            return None
        available_proxies = [p for p in PROXY_POOL if p not in bad_proxies]
        if not available_proxies:
            logger.warning("⚠️ Нет доступных прокси для асинхронного запроса!")
            return None
        if request_counter >= REQUESTS_BEFORE_PROXY_CHANGE:
            current_proxy_index = (current_proxy_index + 1) % len(available_proxies)
            request_counter = 0
        proxy_url = available_proxies[current_proxy_index]
        request_counter += 1
        return proxy_url

# ================== Генерация ID ==================
def normalize_url(url):
    if not url:
        return url
    return url.split('?')[0]

def generate_item_id(item):
    source = item.get('source', '')
    url = normalize_url(item.get('url', ''))
    title = item.get('title', '')[:100]
    unique = f"{source}_{url}_{title}"
    return hashlib.md5(unique.encode('utf-8')).hexdigest()

# ================== CSS селектор ==================
def safe_select(element, selectors):
    for sel in selectors:
        elem = element.select_one(sel)
        if elem:
            return elem
    return None

# ================== Задержки ==================
def human_delay(min_sec=MIN_DELAY_BETWEEN_REQUESTS, max_sec=MAX_DELAY_BETWEEN_REQUESTS):
    time.sleep(random.uniform(min_sec, max_sec))

def brand_delay():
    time.sleep(random.uniform(MIN_DELAY_BETWEEN_BRANDS, MAX_DELAY_BETWEEN_BRANDS))

# ================== HTTP запросы с маскировкой ==================
def make_request(url, headers=None, timeout=REQUEST_TIMEOUT, retries=MAX_RETRIES):
    if headers is None:
        headers = BROWSER_HEADERS.copy()
    
    headers['User-Agent'] = get_next_user_agent()
    
    if random.random() > 0.7:
        headers['Referer'] = random.choice([
            'https://www.google.com/',
            'https://www.yahoo.com/',
            'https://www.bing.com/',
        ])

    for attempt in range(retries):
        proxies = get_next_proxy()
        
        if attempt == 0:
            human_delay()
        else:
            time.sleep(RETRY_DELAY * (2 ** attempt))
        
        try:
            logger.debug(f"🌐 Запрос {url[:100]}... через {proxies.get('http') if proxies else 'без прокси'}")
            r = requests.get(
                url, 
                headers=headers, 
                timeout=timeout, 
                proxies=proxies,
                allow_redirects=True
            )
            r.raise_for_status()
            return r
            
        except requests.exceptions.ProxyError as e:
            logger.warning(f"🔌 Ошибка прокси {attempt+1}/{retries}: {e}")
            if proxies:
                mark_proxy_bad(proxies)
            
        except requests.exceptions.Timeout:
            logger.warning(f"⏰ Таймаут {attempt+1}/{retries} для {url[:50]}...")
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                logger.warning(f"🚫 403 Forbidden - меняем User-Agent")
                headers['User-Agent'] = get_next_user_agent()
            elif e.response.status_code == 429:
                logger.warning(f"🛑 429 Too Many Requests - ждём")
                time.sleep(60)
            elif e.response.status_code == 404:
                return None
            else:
                logger.warning(f"🌐 HTTP ошибка {e.response.status_code}")
                
        except requests.exceptions.ConnectionError:
            logger.warning(f"🔌 Ошибка подключения {attempt+1}/{retries}")
            
        except Exception as e:
            logger.warning(f"❌ Ошибка {attempt+1}/{retries}: {e}")
    
    logger.error(f"❌ Все {retries} попыток не удались для {url[:50]}...")
    return None

# ================== URL helpers ==================
def make_full_url(base, href):
    if not href:
        return ''
    if href.startswith('http'):
        return href
    return urljoin(base, href)

def encode_keyword(keyword):
    return quote(keyword)