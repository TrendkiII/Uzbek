import asyncio
from threading import Thread, Lock
from config import logger

_loop = None
_loop_thread = None
_loop_lock = Lock()
_is_shutting_down = False

def start_background_loop():
    """Запускает бесконечный event loop в отдельном потоке"""
    global _loop, _loop_thread
    with _loop_lock:
        if _loop is not None:
            logger.warning("Background loop already running")
            return
        
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        _loop_thread = Thread(target=_run_loop, daemon=True)
        _loop_thread.start()
        logger.info("✅ Background event loop started")

def _run_loop():
    """Внутренняя функция для запуска цикла с обработкой исключений"""
    global _loop
    try:
        _loop.run_forever()
    except Exception as e:
        logger.error(f"Background loop error: {e}")
    finally:
        # Закрываем все незавершённые задачи
        if _loop and not _is_shutting_down:
            _cleanup_loop()

def _cleanup_loop():
    """Очищает и закрывает цикл"""
    global _loop
    if _loop and _loop.is_running():
        pending = asyncio.all_tasks(_loop)
        for task in pending:
            task.cancel()
        _loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        _loop.close()
        _loop = None

def get_loop():
    """Возвращает фоновый event loop"""
    with _loop_lock:
        if _loop is None:
            raise RuntimeError("Background loop not started. Call start_background_loop() first.")
        return _loop

def run_coro(coro):
    """Запускает корутину в фоновом цикле и возвращает Future"""
    loop = get_loop()
    if not loop.is_running():
        raise RuntimeError("Background loop is not running")
    return asyncio.run_coroutine_threadsafe(coro, loop)

def stop_loop():
    """Останавливает фоновый цикл (для завершения)"""
    global _loop, _is_shutting_down
    _is_shutting_down = True
    with _loop_lock:
        if _loop and _loop.is_running():
            _loop.call_soon_threadsafe(_loop.stop)
            if _loop_thread:
                _loop_thread.join(timeout=5)
            _cleanup_loop()
        logger.info("🛑 Background event loop stopped")