# playwright_fallback.py
import asyncio
from playwright.async_api import async_playwright
from config import logger

async def fetch_html_playwright(url, expected_selector=None, timeout=30000):
    """
    Получает HTML через Playwright с ожиданием появления селектора.
    Возвращает HTML или None при ошибке.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            logger.info(f"🌐 Playwright загружает {url}")
            await page.goto(url, timeout=timeout)
            if expected_selector:
                await page.wait_for_selector(expected_selector, timeout=10000)
            html = await page.content()
            return html
        except Exception as e:
            logger.warning(f"⚠️ Playwright error for {url}: {e}")
            return None
        finally:
            await browser.close()