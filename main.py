import os
import subprocess
import sys
import time
import threading
import logging
from database import init_db

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Конфигурация для Puter
PUTER_PORT = int(os.environ.get("PORT", 8080))  # Puter использует PORT или 8080
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def check_puter_environment():
    """Проверяет, запущено ли на Puter, и адаптирует конфигурацию"""
    is_puter = 'PUTER_USER' in os.environ or os.path.exists('/puter')
    
    if is_puter:
        logger.info("✅ Обнаружена платформа Puter, адаптирую конфигурацию...")
        
        # Puter имеет ограниченный доступ к npm, нужно проверить
        npm_check = subprocess.run(['which', 'npm'], capture_output=True, text=True)
        if npm_check.returncode != 0:
            logger.warning("⚠️ npm не найден! Node.js API не запустится")
            return False
    
    return True

def start_node_api():
    """Запускает Node.js API с адаптацией для Puter"""
    try:
        # Проверяем Puter
        is_puter = 'PUTER_USER' in os.environ or os.path.exists('/puter')
        
        # В Puter используем абсолютный путь
        if is_puter:
            api_path = os.path.join(BASE_DIR, 'free-api')
        else:
            api_path = os.path.join(os.path.dirname(__file__), 'free-api')
        
        # Проверяем существование
        if not os.path.exists(api_path):
            logger.error(f"❌ Папка {api_path} не найдена!")
            logger.info("Создаю папку free-api...")
            os.makedirs(api_path, exist_ok=True)
            os.makedirs(os.path.join(api_path, 'routes'), exist_ok=True)
            
            # На Puter создаём минимальный package.json
            if is_puter:
                package_json = os.path.join(api_path, 'package.json')
                if not os.path.exists(package_json):
                    with open(package_json, 'w') as f:
                        f.write('''{
  "name": "free-sonnetapi",
  "version": "1.0.0",
  "main": "index.js",
  "scripts": {
    "start": "node index.js"
  },
  "dependencies": {
    "express": "^4.18.2",
    "cors": "^2.8.5"
  }
}''')
            return None
        
        # Проверяем node_modules
        node_modules = os.path.join(api_path, 'node_modules')
        if not os.path.exists(node_modules):
            logger.info("📦 Установка Node.js зависимостей...")
            
            # Для Puter используем --no-package-lock и --no-audit для экономии ресурсов
            npm_cmd = ['npm', 'install', '--no-package-lock', '--no-audit']
            if is_puter:
                npm_cmd.append('--production')  # Только production зависимости
            
            result = subprocess.run(npm_cmd, cwd=api_path, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"❌ Ошибка установки: {result.stderr}")
                # На Puter пробуем альтернативный вариант
                if is_puter:
                    logger.info("Пробую установить только необходимые пакеты...")
                    alt_result = subprocess.run(
                        ['npm', 'install', 'express', 'cors', '--no-save'],
                        cwd=api_path,
                        capture_output=True,
                        text=True
                    )
                    if alt_result.returncode != 0:
                        return None
            else:
                logger.info("✅ Зависимости установлены")
        
        # Запускаем API
        logger.info(f"🚀 Запуск free-sonnetapi на порту 3032...")
        
        # Для Puter используем spawn с правильным окружением
        env = os.environ.copy()
        env['PORT'] = '3032'  # Явно указываем порт
        
        process = subprocess.Popen(
            ['node', 'index.js'],
            cwd=api_path,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        def log_output():
            for line in process.stdout:
                if line.strip():
                    logger.info(f"[free-api] {line.strip()}")
        
        threading.Thread(target=log_output, daemon=True).start()
        
        # Даем API время запуститься
        time.sleep(5)
        
        # Проверяем, что процесс жив
        if process.poll() is None:
            # Дополнительная проверка: пробуем подключиться к API
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.connect(('localhost', 3032))
                s.close()
                logger.info("✅ free-sonnetapi запущен и отвечает на порту 3032")
            except:
                logger.warning("⚠️ Процесс запущен, но порт 3032 не отвечает")
            
            return process
        else:
            logger.error("❌ free-sonnetapi сразу завершился")
            return None
        
    except Exception as e:
        logger.error(f"❌ Ошибка запуска Node.js API: {e}")
        return None

def start_bot():
    """Запускает бота с адаптацией для Puter"""
    try:
        logger.info("🚀 Запуск simple_bot.py...")
        
        # Для Puter используем правильный Python
        python_executable = sys.executable
        
        # На Puter может не быть всех зависимостей, проверяем
        is_puter = 'PUTER_USER' in os.environ or os.path.exists('/puter')
        
        env = os.environ.copy()
        if is_puter:
            # Puter может требовать явного указания порта для бота
            env['BOT_PORT'] = str(PUTER_PORT)
        
        process = subprocess.Popen(
            [python_executable, 'simple_bot.py'],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        def log_output():
            for line in process.stdout:
                if line.strip():
                    logger.info(f"[bot] {line.strip()}")
        
        threading.Thread(target=log_output, daemon=True).start()
        
        # Даем боту время запуститься
        time.sleep(3)
        
        if process.poll() is None:
            logger.info("✅ Бот запущен")
            return process
        else:
            # Читаем ошибку
            stdout, _ = process.communicate(timeout=1)
            logger.error(f"❌ Бот сразу завершился: {stdout}")
            return None
        
    except Exception as e:
        logger.error(f"❌ Ошибка запуска бота: {e}")
        return None

def create_puter_start_script():
    """Создаёт start.sh для Puter"""
    start_script = os.path.join(BASE_DIR, 'start.sh')
    with open(start_script, 'w') as f:
        f.write('''#!/bin/bash
# Start script for Puter
echo "🚀 Запуск бота на Puter..."
python main.py
''')
    os.chmod(start_script, 0o755)
    logger.info("✅ Создан start.sh для Puter")

def main():
    """Главная функция с адаптацией для Puter"""
    logger.info("🚀 ЗАПУСК БОТА С FREE-SONNETAPI")
    
    # Проверяем Puter
    is_puter = check_puter_environment()
    
    if is_puter:
        create_puter_start_script()
    
    # Инициализация БД
    try:
        # Для Puter используем абсолютный путь к БД
        if is_puter:
            os.environ['DB_PATH'] = os.path.join(BASE_DIR, 'items.db')
        
        init_db()
        logger.info("✅ База данных инициализирована")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")
        # На Puter продолжаем даже с ошибкой БД
    
    # Запуск Node.js API (на Puter может не работать, но пробуем)
    node_process = None
    if not is_puter or os.path.exists('/usr/bin/node'):
        node_process = start_node_api()
    else:
        logger.warning("⚠️ Node.js не найден, пропускаю запуск API")
    
    if not node_process:
        logger.warning("⚠️ free-sonnetapi не запущен. Бот будет работать без Claude.")
    
    # Запуск бота
    bot_process = start_bot()
    
    if not bot_process:
        logger.error("❌ Не удалось запустить бота!")
        if node_process:
            node_process.terminate()
        sys.exit(1)
    
    # Создаём health check сервер для Puter
    if is_puter:
        from flask import Flask
        health_app = Flask(__name__)
        
        @health_app.route('/')
        def health():
            return {"status": "ok", "bot": "running"}
        
        @health_app.route('/health')
        def health_check():
            return {"status": "alive"}
        
        def run_health_server():
            health_app.run(host='0.0.0.0', port=PUTER_PORT)
        
        threading.Thread(target=run_health_server, daemon=True).start()
        logger.info(f"✅ Health server запущен на порту {PUTER_PORT}")
    
    try:
        # Держим главный процесс живым
        while True:
            time.sleep(5)
            
            # Проверяем, живы ли процессы
            if bot_process.poll() is not None:
                logger.error("❌ Бот неожиданно остановился!")
                # Пробуем перезапустить на Puter
                if is_puter:
                    logger.info("🔄 Пробую перезапустить бота...")
                    bot_process = start_bot()
                    if not bot_process:
                        break
                else:
                    break
            
            # Проверяем Node.js процесс
            if node_process and node_process.poll() is not None:
                logger.warning("⚠️ Node.js API остановился, пробую перезапустить...")
                node_process = start_node_api()
                
    except KeyboardInterrupt:
        logger.info("🛑 Остановка по Ctrl+C...")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
    finally:
        logger.info("🛑 Останавливаю процессы...")
        if bot_process and bot_process.poll() is None:
            bot_process.terminate()
            bot_process.wait(timeout=5)
        if node_process and node_process.poll() is None:
            node_process.terminate()
            node_process.wait(timeout=5)
        logger.info("✅ Все процессы остановлены")

if __name__ == "__main__":
    main()