import asyncio
from playwright.async_api import async_playwright, Browser, Error as PlaywrightError
from config import logger

_browser: Browser = None
_playwright = None
_page_semaphore = asyncio.Semaphore(1)  # ⚡ уменьшено до 1 для экономии памяти
_browser_available = False

async def init_browser():
    """Инициализирует глобальный браузер Playwright"""
    global _browser, _playwright, _browser_available
    try:
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        _browser_available = True
        logger.info("✅ Playwright browser initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize Playwright browser: {e}")
        _browser = None
        _playwright = None
        _browser_available = False

async def get_browser() -> Browser:
    """Возвращает глобальный браузер, если он доступен"""
    if not _browser_available:
        raise RuntimeError("Playwright browser not available")
    return _browser

async def close_browser():
    """Закрывает глобальный браузер и Playwright"""
    global _browser, _playwright, _browser_available
    if _browser:
        try:
            await _browser.close()
        except Exception as e:
            logger.error(f"Error closing browser: {e}")
        _browser = None
    if _playwright:
        try:
            await _playwright.stop()
        except Exception as e:
            logger.error(f"Error stopping playwright: {e}")
        _playwright = None
    _browser_available = False
    logger.info("🛑 Playwright browser closed")

async def fetch_html_playwright(url, expected_selector=None, timeout=60000):  # ⏰ увеличено до 60 сек
    """
    Получает HTML через Playwright, используя глобальный браузер.
    Если браузер недоступен, сразу возвращает None.
    """
    if not _browser_available:
        logger.warning("⚠️ Playwright browser not available, skipping fallback")
        return None
    
    try:
        browser = await get_browser()
    except RuntimeError:
        return None

    async with _page_semaphore:
        page = None
        try:
            page = await browser.new_page()
            logger.info(f"🌐 Playwright page loading {url[:100]}...")
            await page.goto(url, timeout=timeout)
            if expected_selector:
                await page.wait_for_selector(expected_selector, timeout=20000)  # ⏰ увеличено до 20 сек
            html = await page.content()
            return html
        except PlaywrightError as e:
            logger.warning(f"⚠️ Playwright error for {url[:100]}: {e}")
            return None
        except Exception as e:
            logger.warning(f"⚠️ Unexpected Playwright error for {url[:100]}: {e}")
            return None
        finally:
            if page:
                await page.close()
                await asyncio.sleep(0.5)  # 💤 небольшая задержка для освобождения памяти