"""
claude_controller.py - Клиент для Claude Computer Use
"""

import asyncio
import aiohttp
import json
import uuid
import time
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict

@dataclass
class ComputerUseTask:
    """Задача для Computer Use"""
    query: str
    user_id: int
    platform: Optional[str] = None
    platforms: Optional[Dict] = None
    max_items: int = 50
    price_min: int = 0
    price_max: int = 1000000
    id: str = None
    
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:8]

@dataclass
class ComputerUseResult:
    """Результат выполнения задачи"""
    success: bool
    items: List[Dict]
    error: str = None
    duration: float = 0
    tokens: int = 0
    screenshots: List[str] = None
    task_id: str = None

class ClaudeComputerUse:
    """Клиент для Claude Computer Use"""
    
    def __init__(self, api_url: str = "http://localhost:3032"):
        self.api_url = api_url
        self.session = None
        print(f"✅ Claude Computer Use инициализирован (API: {api_url})")
    
    async def _get_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def run_task(self, task: ComputerUseTask) -> ComputerUseResult:
        """Запуск задачи"""
        start_time = time.time()
        
        try:
            prompt = self._build_prompt(task)
            
            messages = [
                {
                    "role": "system",
                    "content": "Ты — помощник для парсинга сайтов. Твоя задача — заходить на сайты, искать товары и возвращать структурированные данные в JSON."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
            
            session = await self._get_session()
            
            async with session.post(
                f"{self.api_url}/v1/chat/completions",
                json={
                    "model": "claude3.5",
                    "messages": messages,
                    "stream": False
                },
                timeout=120
            ) as response:
                
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"API вернул {response.status}: {error_text}")
                
                data = await response.json()
                
                # Парсим ответ
                content = data.get('content', '')
                if not content and 'choices' in data:
                    content = data['choices'][0].get('message', {}).get('content', '')
                
                items = self._parse_response(content)
                
                duration = time.time() - start_time
                
                return ComputerUseResult(
                    success=True,
                    items=items,
                    duration=duration,
                    tokens=0,
                    screenshots=[],
                    task_id=task.id
                )
            
        except Exception as e:
            print(f"❌ Ошибка Computer Use: {e}")
            return ComputerUseResult(
                success=False,
                items=[],
                error=str(e),
                task_id=task.id
            )
        finally:
            if self.session:
                await self.session.close()
                self.session = None
    
    def _build_prompt(self, task: ComputerUseTask) -> str:
        platform_info = ""
        if task.platform and task.platforms and task.platform in task.platforms:
            platform = task.platforms.get(task.platform, {})
            platform_info = f"Сайт: {platform.get('url')} ({platform.get('name')})"
        
        prompt = f"""
ЗАДАЧА: {task.query}

{platform_info}

ИНСТРУКЦИИ:
1. Открой сайт в браузере
2. Найди товары по запросу
3. Для каждого товара собери:
   - Название
   - Цену
   - Ссылку
   - Фото (ссылку)
   - Локацию продавца
   - Состояние (новый/б/у)
4. Если появится капча или запрос на подтверждение:
   - Напиши "НУЖНА ПОМОЩЬ: [описание]"
5. Собери минимум {task.max_items} товаров
6. Верни результат строго в формате JSON-массива:
   [{{"title": "...", "price": "...", "url": "...", "image": "...", "location": "...", "condition": "..."}}]
"""
        return prompt
    
    def _parse_response(self, content: str) -> List[Dict]:
        items = []
        try:
            import re
            json_match = re.search(r'\[\s*\{.*\}\s*\]', content, re.DOTALL)
            
            if json_match:
                data = json.loads(json_match.group(0))
                if isinstance(data, list):
                    items = data
            else:
                try:
                    data = json.loads(content)
                    if isinstance(data, list):
                        items = data
                    elif isinstance(data, dict) and 'items' in data:
                        items = data['items']
                except:
                    items = self._extract_items_from_text(content)
        except Exception as e:
            print(f"Ошибка парсинга ответа: {e}")
        return items
    
    def _extract_items_from_text(self, text: str) -> List[Dict]:
        items = []
        import re
        price_pattern = r'(\d+[\.,]?\d*)\s*(?:₽|\$|€|zł|грн|руб|usd|eur|pln|uah)'
        
        lines = text.split('\n')
        current_item = {}
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            price_match = re.search(price_pattern, line, re.IGNORECASE)
            
            if price_match and len(line) > 10:
                if current_item:
                    items.append(current_item)
                
                current_item = {
                    'title': line[:100],
                    'price': price_match.group(1),
                    'currency': self._detect_currency(line)
                }
            elif current_item and 'description' not in current_item:
                current_item['description'] = line[:200]
        
        if current_item:
            items.append(current_item)
        
        return items
    
    def _detect_currency(self, text: str) -> str:
        currency_map = {
            '₽': 'RUB', 'руб': 'RUB', 'rubble': 'RUB',
            '$': 'USD', 'usd': 'USD',
            '€': 'EUR', 'eur': 'EUR',
            'zł': 'PLN', 'pln': 'PLN', 'zloty': 'PLN',
            'грн': 'UAH', 'uah': 'UAH', 'гривна': 'UAH',
            '£': 'GBP', 'gbp': 'GBP'
        }
        
        text_lower = text.lower()
        for symbol, code in currency_map.items():
            if symbol in text or (len(symbol) > 1 and symbol in text_lower):
                return code
        
        return 'USD'