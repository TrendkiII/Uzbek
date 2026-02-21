import hashlib
import time
import random
import requests
from urllib.parse import urljoin

def get_next_user_agent():
    agents = [
        'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15',
        'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36',
    ]
    return random.choice(agents)

def generate_item_id(item):
    unique = f"{item['source']}_{item['url']}_{item['title']}"
    return hashlib.md5(unique.encode()).hexdigest()

def make_full_url(base, href):
    if not href:
        return ''
    return urljoin(base, href)