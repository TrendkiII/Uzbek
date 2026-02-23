const express = require('express');
const axios = require('axios');
const router = express.Router();

// ============================================
// КОНФИГУРАЦИЯ
// ============================================

let puterToken = null;
let duckVqd = null;
let duckExpiry = null;

// ============================================
// PUTER - ПОЛУЧЕНИЕ ТОКЕНА
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
    
    if (response.data?.access_token) {
      console.log('✅ Puter токен получен');
      return response.data.access_token;
    }
    
    return null;
  } catch (error) {
    console.log('⚠️ Puter token error:', error.message);
    return null;
  }
}

// ============================================
// DUCKDUCKGO - ПОЛУЧЕНИЕ VQD
// ============================================

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
// PUTER - ЗАПРОС К CLAUDE
// ============================================

async function callPuter(messages, model = 'claude-3-5-sonnet') {
  if (!puterToken) return null;
  
  try {
    const response = await axios({
      method: 'post',
      url: 'https://api.puter.com/chat/completions',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${puterToken}`,
        'Origin': 'https://puter.com'
      },
      data: {
        model: model,
        messages: messages,
        stream: false
      },
      timeout: 60000
    });
    
    return {
      content: response.data?.choices[0]?.message?.content || '',
      usage: response.data?.usage || { total_tokens: 0 }
    };
  } catch (error) {
    console.log('⚠️ Puter API error:', error.message);
    if (error.response?.status === 401) {
      puterToken = null;
    }
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
// ОБНОВЛЕНИЕ ТОКЕНОВ
// ============================================

setInterval(async () => {
  puterToken = await getPuterToken();
}, 30 * 60 * 1000);

setInterval(async () => {
  duckVqd = await getDuckVqd();
  if (duckVqd) duckExpiry = Date.now() + 20 * 60 * 1000;
}, 5 * 60 * 1000);

// Инициализация
(async () => {
  puterToken = await getPuterToken();
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
    
    console.log(`\n📨 [${new Date().toISOString()}] ЗАПРОС:`);
    
    if (!messages.length) {
      return res.status(400).json({ error: 'No messages provided' });
    }
    
    // Пробуем провайдеров
    let result = null;
    let provider = null;
    
    // 1. Puter
    console.log('🔄 Пробуем Puter...');
    let puterModel = model === 'claude3.7' ? 'claude-3-7-sonnet' : 'claude-3-5-sonnet';
    result = await callPuter(messages, puterModel);
    provider = 'puter';
    
    // 2. Если Puter не сработал - DuckDuckGo
    if (!result?.content) {
      console.log('⚠️ Puter не ответил, пробуем DuckDuckGo...');
      result = await callDuck(messages);
      provider = 'duckai';
    }
    
    const duration = Date.now() - startTime;
    
    if (result?.content) {
      console.log(`✅ УСПЕХ (${provider}) за ${duration}ms`);
      
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
    console.error('❌ Ошибка:', error.message);
    res.status(500).json({ error: error.message });
  }
});

router.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    providers: {
      puter: puterToken ? '✅' : '❌',
      duckai: duckVqd ? '✅' : '❌'
    },
    timestamp: new Date().toISOString()
  });
});

module.exports = router;