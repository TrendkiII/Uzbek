import time
from threading import Thread

from config import BOT_STATE, state_lock, logger, stop_event, scheduler_busy, scheduler_lock
from brands import expand_selected_brands_for_platforms, BRAND_GROUPS
from scheduler_common import run_search

def check_all_marketplaces(chat_id=None):
    """
    Запускает поиск на всех выбранных площадках по выбранным брендам или всем вариациям.
    Вызывается как из планировщика, так и вручную из telegram_bot.
    """
    with state_lock:
        platforms = BOT_STATE['selected_platforms'].copy()
        mode = BOT_STATE['mode']
        selected_brands = BOT_STATE['selected_brands'].copy()
        turbo = BOT_STATE.get('turbo_mode', False)

    logger.info(f"🚀 Запуск проверки (планировщик/ручной) в режиме {'ТУРБО' if turbo else 'обычном'}")

    # Формируем список ключевых слов для поиска
    if mode == 'auto':
        # Автоматический режим: собираем все вариации из всех групп
        all_vars = []
        for group in BRAND_GROUPS:
            for typ in ['latin', 'jp', 'cn', 'universal']:
                if typ in group['variations']:
                    all_vars.extend(group['variations'][typ])
        keywords = list(set(all_vars))
        if not turbo:
            keywords = keywords[:20]  # в обычном режиме ограничиваем 20 ключами
    else:
        # Ручной режим: берём вариации выбранных брендов
        if not selected_brands:
            logger.warning("Ручной режим, но бренды не выбраны")
            return
        # Для упрощения берём вариации для первой выбранной площадки
        sample_platform = platforms[0] if platforms else 'Mercari JP'
        keywords = []
        for brand in selected_brands:
            keywords.extend(expand_selected_brands_for_platforms([brand], [sample_platform])[sample_platform])
        keywords = list(set(keywords))[:20]  # также ограничиваем

    # Определяем количество воркеров в зависимости от режима
    max_workers = 10 if turbo else 5

    # Запускаем поиск (синхронно, но внутри себя он асинхронный)
    result = run_search(keywords, platforms, chat_id, max_workers=max_workers)

    return result

def run_scheduler():
    """
    Планировщик, запускающий проверки через заданные интервалы.
    Использует флаг scheduler_busy для предотвращения наложения проверок.
    """
    global scheduler_busy
    logger.info("⏰ Планировщик запущен")
    last_run = 0
    first = True

    while not BOT_STATE.get('shutdown', False):
        with state_lock:
            turbo = BOT_STATE.get('turbo_mode', False)
            if turbo:
                interval = 10 * 60  # 10 минут для турбо-режима
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