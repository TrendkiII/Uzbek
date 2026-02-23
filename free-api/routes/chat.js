/**
 * @fileoverview Claude API Proxy using official Puter.js SDK and DuckDuckGo
 */

const express = require('express');
const axios = require('axios');
const router = express.Router();

// ============================================
// ИМПОРТ PUTER.JS SDK
// ============================================
let puterSdk;
try {
  // Пытаемся загрузить Puter.js
  const puterModule = require('@heyputer/puter.js');
  // SDK может экспортироваться по-разному, пробуем разные варианты
  puterSdk = puterModule.puter || puterModule.default || puterModule;
  console.log('✅ Puter.js SDK загружен');
} catch (error) {
  console.warn('⚠️ Puter.js SDK не установлен. Установите: npm install @heyputer/puter.js');
}

// ============================================
// СОСТОЯНИЕ
// ============================================
let puterClient = null; // Будет хранить инициализированный клиент Puter
let duckVqd = null;     // Токен для DuckDuckGo
let duckExpiry = null;  // Время истечения VQD

// ============================================
// PUTER - ИНИЦИАЛИЗАЦИЯ КЛИЕНТА
// ============================================

/**
 * Инициализирует клиент Puter с токеном
 * @returns {Promise<Object|null>} Инициализированный клиент Puter
 */
async function initPuterClient() {
  try {
    console.log('🔄 Инициализация Puter.js клиента...');
    
    if (!puterSdk) {
      throw new Error('Puter.js SDK не загружен');
    }

    // Используем гостевой токен (без браузера)
    // В документации: для Node.js нужен токен через init()
    // Мы можем использовать тот же метод получения токена, что и раньше,
    // но теперь передадим его в SDK для консистентности.
    const tokenResponse = await axios({
      method: 'post',
      url: 'https://api.puter.com/auth/token',
      headers: {
        'Content-Type': 'application/json',
        'Origin': 'https://puter.com'
      },
      data: {
        grant_type: 'guest'
      },
      timeout: 10000
    });

    const accessToken = tokenResponse.data?.access_token;
    
    if (!accessToken) {
      throw new Error('Не удалось получить токен доступа');
    }

    // Инициализируем SDK с токеном
    // Примечание: путь к init может отличаться, проверим по документации
    let client;
    if (puterSdk.init) {
      client = puterSdk.init(accessToken);
    } else if (puterSdk.default?.init) {
      client = puterSdk.default.init(accessToken);
    } else {
      // Если init не найден, просто используем SDK как есть (он может сам управлять токенами)
      console.log('ℹ️ Используем Puter SDK без явной инициализации (токен будет передан в запросах)');
      client = puterSdk;
      // Сохраним токен для передачи в заголовках (если потребуется)
      process.env.puterAuthToken = accessToken;
    }
    
    console.log('✅ Puter клиент инициализирован');
    return client;
    
  } catch (error) {
    console.error('❌ Ошибка инициализации Puter:', error.message);
    return null;
  }
}

// ============================================
// DUCKDUCKGO - ПОЛУЧЕНИЕ VQD
// ============================================

/**
 * Получает VQD токен для DuckDuckGo
 * @returns {Promise<string|null>} VQD токен
 */
async function getDuckVqd() {
  try {
    console.log('🔄 Получаем DuckDuckGo VQD...');
    
    const response = await axios({
      method: 'get',
      url: 'https://duckduckgo.com/duckchat/v1/status',
      headers: {
        'x-vqd-accept': '1',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      },
      timeout: 10000
    });
    
    const vqd = response.headers['x-vqd-4'];
    if (vqd) {
      console.log('✅ DuckDuckGo VQD получен');
      return vqd;
    }
    return null;
  } catch (error) {
    console.log('⚠️ Duck VQD error:', error.message);
    return null;
  }
}

// ============================================
// PUTER - ЗАПРОС К CLAUDE ЧЕРЕЗ SDK
// ============================================

/**
 * Отправляет запрос к Claude через Puter.js SDK
 * @param {Array} messages - Массив сообщений
 * @param {string} model - Модель ('claude3.5' или 'claude3.7')
 * @returns {Promise<Object|null>} Ответ с контентом
 */
async function callPuterWithSDK(messages, model = 'claude3.5') {
  if (!puterClient) {
    console.log('⚠️ Puter клиент не инициализирован');
    return null;
  }
  
  try {
    console.log(`🔄 Отправка запроса в Puter SDK (модель: ${model})...`);
    
    // Преобразуем сообщения в формат, понятный Puter.ai.chat
    // SDK ожидает простой текст для чата
    const userMessages = messages
      .filter(m => m.role === 'user')
      .map(m => m.content)
      .join('\n\n');
    
    const systemMessage = messages.find(m => m.role === 'system')?.content || '';
    
    // Формируем промпт с системным сообщением
    const prompt = systemMessage 
      ? `[System: ${systemMessage}]\n\nUser: ${userMessages}`
      : userMessages;
    
    // Используем Puter.ai.chat
    let response;
    if (puterClient.ai?.chat) {
      // Прямой вызов chat
      response = await puterClient.ai.chat(prompt);
    } else if (puterClient.default?.ai?.chat) {
      response = await puterClient.default.ai.chat(prompt);
    } else if (puterClient.chat) {
      response = await puterClient.chat(prompt);
    } else {
      // Если ничего не работает, пробуем через прямые заголовки (старый способ)
      console.log('⚠️ Метод chat не найден в SDK, пробуем прямой API...');
      return await callPuterDirect(messages, model);
    }
    
    console.log('✅ Ответ получен от Puter SDK');
    
    return {
      content: typeof response === 'string' ? response : (response.text || response.message || JSON.stringify(response)),
      usage: { total_tokens: 0 } // SDK не даёт информацию о токенах
    };
    
  } catch (error) {
    console.error('❌ Puter SDK error:', error.message);
    // Если SDK упал, пробуем прямой API как запасной
    console.log('🔄 SDK не сработал, пробуем прямой API...');
    return await callPuterDirect(messages, model);
  }
}

// ============================================
// PUTER - ЗАПРОС ЧЕРЕЗ ПРЯМОЙ API (ЗАПАСНОЙ)
// ============================================

/**
 * Запасной метод: прямой запрос к Puter API
 */
async function callPuterDirect(messages, model = 'claude3.5') {
  try {
    const tokenResponse = await axios({
      method: 'post',
      url: 'https://api.puter.com/auth/token',
      data: { grant_type: 'guest' }
    });
    
    const token = tokenResponse.data?.access_token;
    if (!token) return null;
    
    // Маппинг моделей
    const modelMap = {
      'claude3.5': 'claude-3-5-sonnet',
      'claude3.7': 'claude-3-7-sonnet'
    };
    
    const response = await axios({
      method: 'post',
      url: 'https://api.puter.com/chat/completions',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      data: {
        model: modelMap[model] || 'claude-3-5-sonnet',
        messages: messages,
        stream: false
      },
      timeout: 60000
    });
    
    return {
      content: response.data?.choices?.[0]?.message?.content || '',
      usage: response.data?.usage || { total_tokens: 0 }
    };
    
  } catch (error) {
    console.log('⚠️ Puter direct API error:', error.message);
    return null;
  }
}

// ============================================
// DUCKDUCKGO - ЗАПРОС К CLAUDE HAIKU
// ============================================

async function callDuck(messages, retryCount = 0) {
  if (!duckVqd) return null;
  
  try {
    const response = await axios({
      method: 'post',
      url: 'https://duckduckgo.com/duckchat/v1/chat',
      headers: {
        'Content-Type': 'application/json',
        'x-vqd-4': duckVqd,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      },
      data: {
        model: 'claude-3-haiku-20240307',
        messages: messages
      },
      timeout: 30000
    });
    
    if (response.headers['x-vqd-4']) {
      duckVqd = response.headers['x-vqd-4'];
    }
    
    return {
      content: response.data?.message || '',
      usage: { total_tokens: 0 }
    };
  } catch (error) {
    console.log('⚠️ Duck API error:', error.message);
    
    if (error.response?.status === 401 && retryCount < 2) {
      console.log('🔄 VQD протух, обновляем...');
      duckVqd = await getDuckVqd();
      if (duckVqd) {
        return callDuck(messages, retryCount + 1);
      }
    }
    return null;
  }
}

// ============================================
// ПЕРИОДИЧЕСКОЕ ОБНОВЛЕНИЕ
// ============================================

// Обновляем Puter клиент каждые 30 минут
setInterval(async () => {
  puterClient = await initPuterClient();
}, 30 * 60 * 1000);

// Обновляем VQD каждые 5 минут
setInterval(async () => {
  duckVqd = await getDuckVqd();
  if (duckVqd) duckExpiry = Date.now() + 20 * 60 * 1000;
}, 5 * 60 * 1000);

// Инициализация при старте
(async () => {
  puterClient = await initPuterClient();
  duckVqd = await getDuckVqd();
  if (duckVqd) duckExpiry = Date.now() + 20 * 60 * 1000;
})();

// ============================================
// ОСНОВНОЙ ЭНДПОИНТ
// ============================================

router.post('/v1/chat/completions', async (req, res) => {
  const startTime = Date.now();
  
  try {
    const { model = 'claude3.5', messages = [] } = req.body;
    
    console.log(`\n📨 [${new Date().toISOString()}] Запрос к Claude`);
    
    if (!messages.length) {
      return res.status(400).json({ error: 'No messages provided' });
    }
    
    // Пробуем провайдеров
    let result = null;
    let provider = null;
    
    // 1. Puter (сначала через SDK, если есть)
    if (puterSdk) {
      console.log('🔄 Пробуем Puter SDK...');
      result = await callPuterWithSDK(messages, model);
      provider = 'puter-sdk';
    }
    
    // 2. Если SDK не сработал, пробуем прямой API
    if (!result?.content) {
      console.log('⚠️ SDK не ответил, пробуем прямой Puter API...');
      result = await callPuterDirect(messages, model);
      provider = 'puter-direct';
    }
    
    // 3. Если Puter не сработал - DuckDuckGo
    if (!result?.content) {
      console.log('⚠️ Puter не ответил, пробуем DuckDuckGo...');
      result = await callDuck(messages);
      provider = 'duckai';
    }
    
    const duration = Date.now() - startTime;
    
    if (result?.content) {
      console.log(`✅ Успех (${provider}) за ${duration}ms`);
      
      return res.json({
        id: `chatcmpl-${Date.now()}`,
        object: 'chat.completion',
        created: Math.floor(Date.now() / 1000),
        model: model,
        choices: [{
          index: 0,
          message: {
            role: 'assistant',
            content: result.content
          },
          finish_reason: 'stop'
        }],
        usage: result.usage || { total_tokens: 0 },
        provider: provider
      });
    } else {
      console.log(`❌ Все провайдеры недоступны за ${duration}ms`);
      
      return res.status(503).json({
        error: 'All providers unavailable',
        choices: [{
          index: 0,
          message: {
            role: 'assistant',
            content: 'Извините, Claude временно недоступен. Используйте обычный поиск.'
          },
          finish_reason: 'stop'
        }]
      });
    }
    
  } catch (error) {
    console.error('❌ Критическая ошибка:', error.message);
    res.status(500).json({ error: error.message });
  }
});

// ============================================
// HEALTH CHECK
// ============================================

router.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    providers: {
      puter_sdk: puterClient ? '✅' : '❌',
      duckai: duckVqd ? '✅' : '❌'
    },
    timestamp: new Date().toISOString(),
    uptime: process.uptime()
  });
});

// ============================================
// СПИСОК МОДЕЛЕЙ
// ============================================

router.get('/v1/models', (req, res) => {
  res.json({
    object: 'list',
    data: [
      {
        id: 'claude3.5',
        object: 'model',
        owned_by: 'puter',
        description: 'Claude 3.5 Sonnet через Puter.js SDK'
      },
      {
        id: 'claude3.7',
        object: 'model',
        owned_by: 'puter',
        description: 'Claude 3.7 Sonnet через Puter.js SDK'
      },
      {
        id: 'claude-3-haiku',
        object: 'model',
        owned_by: 'duckai',
        description: 'Claude 3 Haiku через DuckDuckGo'
      }
    ]
  });
});

module.exports = router;