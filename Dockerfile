FROM python:3.11-slim

# Устанавливаем Node.js
RUN apt-get update && apt-get install -y \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Создаем рабочую директорию
WORKDIR /app

# Копируем Python зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем Node.js API
COPY free-api/ ./free-api/
WORKDIR /app/free-api
RUN npm install

# Возвращаемся в основную директорию
WORKDIR /app

# Копируем весь проект
COPY . .

# Railway дает порт через переменную PORT
ENV PORT=8080

# Запускаем
CMD ["python", "main.py"]