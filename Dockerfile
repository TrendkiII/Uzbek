FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Системные зависимости для Chromium
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    ca-certificates \
    fonts-liberation \
    libasound2t64 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libxshmfence1 \
    libxkbcommon0 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libatspi2.0-0 \
    libxss1 \
    && rm -rf /var/lib/apt/lists/*

# Копируем зависимости Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем Chromium через Playwright
RUN python -m playwright install chromium
RUN python -m playwright install-deps

# Копируем весь код
COPY . .

# Порт для Railway
ENV PORT=8080

# Запускаем main.py (он запустит Flask и всю инициализацию)
CMD ["python", "main.py"]