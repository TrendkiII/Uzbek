
const express = require('express');
const axios = require('axios');
const router = express.Router();

// Состояние токенов
let puterJwtToken = null;
let duckVqd = null;
let tokenExpiry = null;
let vqdExpiry = null;

// Конфигурация
const PUTER_TOKEN_REFRESH = 10 * 60 * 60 * 1000; // 10 часов
const DUCK_VQD_REFRESH = 30 * 60 * 1000; // 30 минут

// Карта моделей
const MODEL_MAP = {
  'claude3.5': { provider: 'puter', model: 'claude-3-5-sonnet-20241022' },
  'claude3.7': { provider: 'puter', model: 'claude-3-7-sonnet-latest' },
  'claude-3-5-sonnet-20241022': { provider: 'puter', model: 'claude-3-5-sonnet-20241022' },
  'claude-3-7-sonnet-latest': { provider: 'puter', model: 'claude-3-7-sonnet-latest' },
  'gpt-4o-mini': { provider: 'duckai', model: 'gpt-4o-mini' },
  'o3-mini': { provider: 'duckai', model: 'o3-mini' },
  'claude-3-haiku': { provider: 'duckai', model: 'claude-3-haiku-20240307' }
};

async function generateJwtToken() {
  try {
    console.log('🔄 Generating JWT token...');
    
    // Пробуем несколько способов получить токен
    let token = null;
    
    // Способ 1: Через signup (как у тебя)
    try {
      const response = await axios({
        method: 'post',
        url: 'https://puter.com/signup',
        headers: {
          'Content-Type': 'application/json',
          'Accept': '*/*',
          'Origin': 'https://puter.com',
          'Referer': 'https://puter.com/app/editor',
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
          'X-Requested-With': 'XMLHttpRequest'
        },
        data: {
          "referrer": "/app/editor",
          "is_temp": true
        },
        timeout: 10000
      });
      
      if (response.data && response.data.token) {
        token = response.data.token;
        console.log('✅ JWT token generated via signup');
      }
    } catch (signupError) {
      console.log('⚠️ Signup method failed, trying auth...');
      
      // Способ 2: Через гостевой вход
      const authResponse = await axios({
        method: 'post',
        url: 'https://api.puter.com/auth/login',
        headers: {
          'Content-Type': 'application/json',
          'Origin': 'https://puter.com'
        },
        data: {
          username: `guest_${Date.now()}`,
          password: 'temporary',
          is_guest: true
        },
        timeout: 10000
      });
      
      if (authResponse.data && authResponse.data.token) {
        token = authResponse.data.token;
        console.log('✅ JWT token generated via guest login');
      }
    }
    
    if (token) {
      puterJwtToken = token;
      tokenExpiry = Date.now() + PUTER_TOKEN_REFRESH;
      return true;
    } else {
      throw new Error('No token received');
    }
    
  } catch (error) {
    console.error('❌ JWT error:', error.message);
    return false;
  }
}

async function initDuckVqd() {
  try {
    console.log('🔄 Initializing DuckDuckGo VQD...');
    
    const response = await axios({
      method: 'get',
      url: 'https://duckduckgo.com/duckchat/v1/status',
      headers: {
        'x-vqd-accept': '1',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      },
      timeout: 10000
    });
    
    if (response.headers && response.headers['x-vqd-4']) {
      duckVqd = response.headers['x-vqd-4'];
      vqdExpiry = Date.now() + DUCK_VQD_REFRESH;
      console.log('✅ DuckDuckGo VQD initialized');
      return true;
    }
    
    return false;
  } catch (error) {
    console.error('❌ VQD error:', error.message);
    return false;
  }
}

// Инициализация при старте
(async () => {
  await generateJwtToken();
  await initDuckVqd();
})();

// Периодическое обновление
setInterval(async () => {
  if (!puterJwtToken || Date.now() > tokenExpiry) {
    await generateJwtToken();
  }
}, PUTER_TOKEN_REFRESH);

setInterval(async () => {
  if (!duckVqd || Date.now() > vqdExpiry) {
    await initDuckVqd();
  }
}, DUCK_VQD_REFRESH);

// Health check endpoint
router.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    puter_token: puterJwtToken ? '✅' : '❌',
    duck_vqd: duckVqd ? '✅' : '❌',
    timestamp: new Date().toISOString()
  });
});

// Основной эндпоинт чата
router.post('/v1/chat/completions', async (req, res) => {
  const startTime = Date.now();
  
  try {
    const { model = 'claude3.5', messages = [], stream = false } = req.body;
    
    // Определяем модель и провайдера
    const modelConfig = MODEL_MAP[model] || MODEL_MAP['claude3.5'];
    const { provider, model: actualModel } = modelConfig;
    
    console.log(`📨 [${new Date().toISOString()}] Request: ${model} → ${provider} (${actualModel})`);
    
    if (!messages.length) {
      return res.status(400).json({ 
        error: 'No messages provided',
        code: 'INVALID_REQUEST'
      });
    }
    
    // Подготовка сообщений
    const formattedMessages = messages.map(m => ({
      role: m.role,
      content: m.content
    }));
    
    let response;
    
    if (provider === 'duckai') {
      // DuckDuckGo AI
      if (!duckVqd) {
        const success = await initDuckVqd();
        if (!success) {
          throw new Error('Failed to initialize DuckDuckGo VQD');
        }
      }
      
      try {
        const duckRes = await axios({
          method: 'post',
          url: 'https://duckduckgo.com/duckchat/v1/chat',
          headers: {
            'Content-Type': 'application/json',
            'x-vqd-4': duckVqd,
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
          },
          data: {
            model: actualModel,
            messages: formattedMessages
          },
          timeout: 60000
        });
        
        response = {
          model: actualModel,
          content: duckRes.data?.message || '',
          usage: { total_tokens: 0 },
          provider: 'duckai'
        };
        
      } catch (duckError) {
        // Если ошибка VQD, пробуем обновить
        if (duckError.response?.status === 401) {
          await initDuckVqd();
        }
        throw duckError;
      }
      
    } else {
      // Puter Claude
      if (!puterJwtToken) {
        const success = await generateJwtToken();
        if (!success) {
          throw new Error('Failed to generate Puter JWT token');
        }
      }
      
      const puterRes = await axios({
        method: 'post',
        url: 'https://api.puter.com/drivers/call',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${puterJwtToken}`,
          'Origin': 'https://puter.com'
        },
        data: {
          interface: 'puter-chat-completion',
          driver: 'claude',
          method: 'complete',
          args: {
            messages: formattedMessages,
            model: actualModel
          }
        },
        timeout: 120000 // 2 минуты для Claude
      });
      
      const content = puterRes.data?.result?.message?.content;
      let text = '';
      
      if (Array.isArray(content)) {
        text = content.find(c => c.type === 'text')?.text || '';
      } else if (typeof content === 'string') {
        text = content;
      }
      
      response = {
        model: actualModel,
        content: text,
        usage: puterRes.data?.result?.usage || { 
          prompt_tokens: 0,
          completion_tokens: 0,
          total_tokens: 0 
        },
        provider: 'puter'
      };
    }
    
    const duration = Date.now() - startTime;
    console.log(`✅ [${duration}ms] Response from ${provider}`);
    
    // Форматируем ответ в стиле OpenAI
    res.json({
      id: `chatcmpl-${Date.now()}`,
      object: 'chat.completion',
      created: Math.floor(Date.now() / 1000),
      model: response.model,
      choices: [{
        index: 0,
        message: {
          role: 'assistant',
          content: response.content
        },
        finish_reason: 'stop'
      }],
      usage: response.usage
    });
    
  } catch (error) {
    const duration = Date.now() - startTime;
    console.error(`❌ [${duration}ms] API error:`, error.message);
    
    // Детальный ответ об ошибке
    const statusCode = error.response?.status || 500;
    const errorMessage = error.response?.data?.error || error.message;
    
    res.status(statusCode).json({
      error: {
        message: errorMessage,
        type: error.response?.status === 401 ? 'authentication_error' : 'api_error',
        code: error.code || 'UNKNOWN_ERROR'
      }
    });
  }
});

// Эндпоинт для списка моделей
router.get('/v1/models', (req, res) => {
  res.json({
    object: 'list',
    data: [
      {
        id: 'claude3.5',
        object: 'model',
        created: Math.floor(Date.now() / 1000),
        owned_by: 'puter'
      },
      {
        id: 'claude3.7',
        object: 'model',
        created: Math.floor(Date.now() / 1000),
        owned_by: 'puter'
      },
      {
        id: 'gpt-4o-mini',
        object: 'model',
        created: Math.floor(Date.now() / 1000),
        owned_by: 'duckai'
      }
    ]
  });
});

module.exports = router;