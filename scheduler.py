import time
from threading import Thread

from config import BOT_STATE, state_lock, logger, stop_event, scheduler_busy, scheduler_lock
from brands import expand_selected_brands_for_platforms, BRAND_GROUPS
from scheduler_common import run_search

def check_all_marketplaces(chat_id=None):
    with state_lock:
        platforms = BOT_STATE['selected_platforms'].copy()
        mode = BOT_STATE['mode']
        selected_brands = BOT_STATE['selected_brands'].copy()
        turbo = BOT_STATE.get('turbo_mode', False)
    
    logger.info(f"🚀 Запуск проверки (планировщик/ручной) в режиме {'ТУРБО' if turbo else 'обычном'}")
    
    # Формируем ключевые слова
    if mode == 'auto':
        all_vars = []
        for group in BRAND_GROUPS:
            for typ in ['latin', 'jp', 'cn', 'universal']:
                if typ in group['variations']:
                    all_vars.extend(group['variations'][typ])
        keywords = list(set(all_vars))
        if not turbo:
            keywords = keywords[:20]  # ограничим до 20 в обычном режиме
    else:
        if not selected_brands:
            logger.warning("Ручной режим, но бренды не выбраны")
            return
        sample_platform = platforms[0] if platforms else 'Mercari JP'
        keywords = []
        for brand in selected_brands:
            keywords.extend(expand_selected_brands_for_platforms([brand], [sample_platform])[sample_platform])
        keywords = list(set(keywords))[:20]  # тоже ограничим
    
    # Запускаем поиск с уменьшенным max_concurrent (5 для обычного, 10 для турбо)
    max_conc = 10 if turbo else 5
    result = run_search(keywords, platforms, chat_id, max_concurrent=max_conc)
    
    return result

def run_scheduler():
    global scheduler_busy
    logger.info("⏰ Планировщик запущен")
    last_run = 0
    first = True
    
    while not BOT_STATE.get('shutdown', False):
        with state_lock:
            turbo = BOT_STATE.get('turbo_mode', False)
            if turbo:
                interval = 10 * 60  # 10 минут (увеличено с 5)
            else:
                interval = BOT_STATE['interval'] * 60
            paused = BOT_STATE['paused']
        
        now = time.time()
        if not paused and not first and (now - last_run) >= interval:
            with scheduler_lock:
                if scheduler_busy:
                    logger.info("⏰ Предыдущая проверка планировщика ещё выполняется, пропускаю запуск")
                else:
                    scheduler_busy = True
                    logger.info(f"⏰ Запуск по расписанию (интервал {interval//60} мин)")
                    def run_and_clear():
                        try:
                            check_all_marketplaces()
                        finally:
                            with scheduler_lock:
                                global scheduler_busy
                                scheduler_busy = False
                    Thread(target=run_and_clear).start()
                    last_run = now
        elif first:
            first = False
            last_run = now
        time.sleep(30)