FROM python:3.11-slim

# Установка Node.js и npm
RUN apt-get update && apt-get install -y \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем зависимости Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект
COPY . .

# Установка Node.js зависимостей для free-api
RUN if [ -d "free-api" ]; then \
        cd free-api && npm install; \
    fi

# Запуск
CMD ["python", "main.py"]