import os
from simple_bot import app
from database import init_db
from config import logger

if __name__ == "__main__":
    logger.info("🚀 ЗАПУСК БОТА")
    init_db()
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)