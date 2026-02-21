import asyncio
from threading import Thread
from config import logger

_loop = None
_loop_thread = None

def start_background_loop():
    """Запускает бесконечный event loop в отдельном потоке"""
    global _loop, _loop_thread
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _loop_thread = Thread(target=_loop.run_forever, daemon=True)
    _loop_thread.start()
    logger.info("✅ Background event loop started")

def get_loop():
    return _loop

def run_coro(coro):
    """Запускает корутину в фоновом цикле и возвращает Future"""
    if not _loop:
        raise RuntimeError("Background loop not started")
    return asyncio.run_coroutine_threadsafe(coro, _loop)

def stop_loop():
    """Останавливает фоновый цикл (для завершения)"""
    global _loop
    if _loop:
        _loop.call_soon_threadsafe(_loop.stop)
        logger.info("🛑 Background event loop stopped")