import asyncio
from playwright.async_api import async_playwright, Browser
from config import logger

_browser: Browser = None
_playwright = None
_page_semaphore = asyncio.Semaphore(5)  # максимум 5 одновременных страниц

async def init_browser():
    """Инициализирует глобальный браузер Playwright"""
    global _browser, _playwright
    try:
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        logger.info("✅ Playwright browser initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize Playwright browser: {e}")
        _browser = None
        _playwright = None

async def get_browser() -> Browser:
    """Возвращает глобальный браузер, инициализируя при необходимости"""
    global _browser
    if _browser is None:
        await init_browser()
    if _browser is None:
        raise RuntimeError("Failed to initialize Playwright browser")
    return _browser

async def close_browser():
    """Закрывает глобальный браузер и Playwright"""
    global _browser, _playwright
    if _browser:
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.stop()
        _playwright = None
    logger.info("🛑 Playwright browser closed")

async def fetch_html_playwright(url, expected_selector=None, timeout=30000):
    """
    Получает HTML через Playwright, используя глобальный браузер.
    Для каждого запроса создаётся новая страница, которая закрывается после использования.
    """
    browser = await get_browser()
    async with _page_semaphore:  # ограничиваем параллельные страницы
        page = None
        try:
            page = await browser.new_page()
            logger.info(f"🌐 Playwright page loading {url[:100]}...")
            await page.goto(url, timeout=timeout)
            if expected_selector:
                await page.wait_for_selector(expected_selector, timeout=10000)
            html = await page.content()
            return html
        except Exception as e:
            logger.warning(f"⚠️ Playwright error for {url[:100]}: {e}")
            return None
        finally:
            if page:
                await page.close()# 