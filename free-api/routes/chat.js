/**
 * @fileoverview Claude API Proxy using official Puter.js SDK + fallbacks
 */

const express = require('express');
const axios = require('axios');
const router = express.Router();

// ============================================
// PUTER.JS SDK
// ============================================
let puterSdk;
try {
  const puterModule = require('@heyputer/puter.js');
  puterSdk = puterModule.puter || puterModule.default || puterModule;
  console.log('✅ Puter.js SDK загружен');
} catch (error) {
  console.warn('⚠️ Puter.js SDK не установлен. Установите: npm install @heyputer/puter.js');
}

// ============================================
// СОСТОЯНИЕ
// ============================================
let puterClient = null;
let puterToken = null;
let duckVqd = null;
let duckExpiry = null;

// ============================================
// PUTER - ПОЛУЧЕНИЕ ТОКЕНА (для SDK и прямых запросов)
// ============================================

async function getPuterToken() {
  try {
    console.log('🔄 Получаем Puter токен...');
    
    const response = await axios({
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

    const token = response.data?.access_token;
    if (token) {
      console.log('✅ Puter токен получен');
      return token;
    }
    return null;
  } catch (error) {
    console.log('⚠️ Puter token error:', error.message);
    return null;
  }
}

// ============================================
// PUTER - ИНИЦИАЛИЗАЦИЯ SDK
// ============================================

async function initPuterClient() {
  if (!puterSdk) return null;
  
  try {
    const token = await getPuterToken();
    if (!token) return null;
    
    puterToken = token; // сохраняем для fallback
    
    // Пробуем разные способы инициализации SDK
    if (puterSdk.init) {
      return puterSdk.init(token);
    } else if (puterSdk.default?.init) {
      return puterSdk.default.init(token);
    } else {
      // Если init нет, сохраняем токен в env (некоторые версии SDK так работают)
      process.env.PUTER_AUTH_TOKEN = token;
      return puterSdk;
    }
  } catch (error) {
    console.error('❌ Puter SDK init error:', error.message);
    return null;
  }
}

// ============================================
// PUTER - ЗАПРОС ЧЕРЕЗ SDK
// ============================================

async function callPuterSDK(messages, model = 'claude3.5') {
  if (!puterClient) return null;
  
  try {
    console.log(`🔄 Puter SDK запрос (${model})...`);
    
    // Формируем промпт из сообщений
    const userMessages = messages
      .filter(m => m.role === 'user')
      .map(m => m.content)
      .join('\n\n');
    
    const systemMessage = messages.find(m => m.role === 'system')?.content || '';
    const prompt = systemMessage 
      ? `System: ${systemMessage}\n\nUser: ${userMessages}`
      : userMessages;
    
    // Пробуем разные методы SDK
    let response;
    if (puterClient.ai?.chat) {
      response = await puterClient.ai.chat(prompt);
    } else if (puterClient.chat) {
      response = await puterClient.chat(prompt);
    } else if (puterClient.default?.ai?.chat) {
      response = await puterClient.default.ai.chat(prompt);
    } else {
      // Если SDK не работает, пробуем прямой API
      return await callPuterDirect(messages, model);
    }
    
    const content = typeof response === 'string' 
      ? response 
      : (response.text || response.message || response.response || JSON.stringify(response));
    
    return {
      content: content,
      usage: { total_tokens: 0 },
      provider: 'puter-sdk'
    };
    
  } catch (error) {
    console.log('⚠️ Puter SDK error:', error.message);
    return await callPuterDirect(messages, model);
  }
}

// ============================================
// PUTER - ПРЯМОЙ API (FALLBACK)
// ============================================

async function callPuterDirect(messages, model = 'claude3.5') {
  if (!puterToken) {
    puterToken = await getPuterToken();
    if (!puterToken) return null;
  }
  
  try {
    console.log('🔄 Puter direct API запрос...');
    
    const modelMap = {
      'claude3.5': 'claude-3-5-sonnet',
      'claude3.7': 'claude-3-7-sonnet'
    };
    
    const response = await axios({
      method: 'post',
      url: 'https://api.puter.com/chat/completions',
      headers: {
        'Authorization': `Bearer ${puterToken}`,
        'Content-Type': 'application/json',
        'Origin': 'https://puter.com'
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
      usage: response.data?.usage || { total_tokens: 0 },
      provider: 'puter-direct'
    };
    
  } catch (error) {
    console.log('⚠️ Puter direct API error:', error.message);
    if (error.response?.status === 401) puterToken = null;
    return null;
  }
}

// ============================================
// DUCKDUCKGO
// ============================================

async function getDuckVqd() {
  try {
    const response = await axios({
      method: 'get',
      url: 'https://duckduckgo.com/duckchat/v1/status',
      headers: {
        'x-vqd-accept': '1',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      },
      timeout: 10000
    });
    
    return response.headers['x-vqd-4'] || null;
  } catch (error) {
    return null;
  }
}

async function callDuck(messages, retryCount = 0) {
  if (!duckVqd) return null;
  
  try {
    const response = await axios({
      method: 'post',
      url: 'https://duckduckgo.com/duckchat/v1/chat',
      headers: {
        'Content-Type': 'application/json',
        'x-vqd-4': duckVqd,
        'User-Agent': 'Mozilla/5.0'
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
      usage: { total_tokens: 0 },
      provider: 'duckai'
    };
  } catch (error) {
    if (error.response?.status === 401 && retryCount < 2) {
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

setInterval(async () => {
  puterClient = await initPuterClient();
}, 30 * 60 * 1000);

setInterval(async () => {
  duckVqd = await getDuckVqd();
}, 5 * 60 * 1000);

// Инициализация при старте
(async () => {
  puterClient = await initPuterClient();
  duckVqd = await getDuckVqd();
})();

// ============================================
// ОСНОВНОЙ ЭНДПОИНТ
// ============================================

router.post('/v1/chat/completions', async (req, res) => {
  const startTime = Date.now();
  
  try {
    const { model = 'claude3.5', messages = [] } = req.body;
    
    console.log(`\n📨 [${new Date().toISOString()}] Запрос к Claude (${model})`);
    
    if (!messages.length) {
      return res.status(400).json({ error: 'No messages provided' });
    }
    
    let result = null;
    let provider = null;
    
    // 1. Puter SDK (основной)
    if (puterClient) {
      result = await callPuterSDK(messages, model);
      provider = result?.provider;
    }
    
    // 2. Puter Direct (если SDK не сработал)
    if (!result?.content) {
      result = await callPuterDirect(messages, model);
      provider = result?.provider;
    }
    
    // 3. DuckDuckGo (если Puter не работает)
    if (!result?.content) {
      result = await callDuck(messages);
      provider = result?.provider;
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
      puter_token: puterToken ? '✅' : '❌',
      duckai: duckVqd ? '✅' : '❌'
    },
    timestamp: new Date().toISOString(),
    uptime: process.uptime()
  });
});

router.get('/v1/models', (req, res) => {
  res.json({
    object: 'list',
    data: [
      { id: 'claude3.5', object: 'model', owned_by: 'puter' },
      { id: 'claude3.7', object: 'model', owned_by: 'puter' },
      { id: 'claude-3-haiku', object: 'model', owned_by: 'duckai' }
    ]
  });
});

module.exports = router;