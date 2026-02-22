const express = require('express');
const axios = require('axios');
const router = express.Router();

let puterJwtToken = null;
let duckVqd = null;

async function generateJwtToken() {
  try {
    console.log('🔄 Generating JWT token...');
    
    // Новый способ для Puter (2026)
    const response = await axios({
      method: 'post',
      url: 'https://api.puter.com/auth/token',
      headers: {
        'Content-Type': 'application/json',
        'Origin': 'https://puter.com',
        'Referer': 'https://puter.com/',
        'User-Agent': 'Mozilla/5.0'
      },
      data: {
        "grant_type": "guest"
      }
    });
    
    if (response.data && response.data.access_token) {
      puterJwtToken = response.data.access_token;
      console.log('✅ JWT token generated');
      return true;
    }
    
    // Запасной вариант
    const backupResponse = await axios({
      method: 'post',
      url: 'https://puter.com/api/auth/guest',
      headers: {
        'Content-Type': 'application/json',
      }
    });
    
    if (backupResponse.data && backupResponse.data.token) {
      puterJwtToken = backupResponse.data.token;
      console.log('✅ JWT token generated (backup)');
      return true;
    }
    
    throw new Error('No token received');
    
  } catch (error) {
    console.error('❌ JWT error:', error.message);
    return false;
  }
}

async function initDuckVqd() {
  try {
    const response = await axios({
      method: 'get',
      url: 'https://duckduckgo.com/duckchat/v1/status',
      headers: {
        'x-vqd-accept': '1',
        'User-Agent': 'Mozilla/5.0'
      }
    });
    
    if (response.headers['x-vqd-4']) {
      duckVqd = response.headers['x-vqd-4'];
      console.log('✅ DuckDuckGo VQD initialized');
    }
  } catch (error) {
    console.error('❌ VQD error:', error.message);
  }
}

// Инициализация
(async () => {
  await generateJwtToken();
  await initDuckVqd();
})();

// Обновление каждые 6 часов
setInterval(generateJwtToken, 6 * 60 * 60 * 1000);
setInterval(initDuckVqd, 6 * 60 * 60 * 1000);

router.post('/v1/chat/completions', async (req, res) => {
  try {
    const { model = 'claude3.5', messages = [] } = req.body;
    
    if (!messages.length) {
      return res.status(400).json({ error: 'No messages' });
    }
    
    // Пробуем Puter
    if (!puterJwtToken) {
      await generateJwtToken();
    }
    
    if (puterJwtToken) {
      try {
        const puterRes = await axios({
          method: 'post',
          url: 'https://api.puter.com/ai/chat',
          headers: {
            'Authorization': `Bearer ${puterJwtToken}`,
            'Content-Type': 'application/json'
          },
          data: {
            messages: messages,
            model: model === 'claude3.7' ? 'claude-3-7-sonnet' : 'claude-3-5-sonnet'
          },
          timeout: 60000
        });
        
        return res.json({
          content: puterRes.data?.message?.content || puterRes.data?.choices?.[0]?.message?.content || '',
          model: model
        });
      } catch (puterError) {
        console.log('Puter error, trying DuckDuckGo...');
      }
    }
    
    // Если Puter не сработал, пробуем DuckDuckGo
    if (!duckVqd) {
      await initDuckVqd();
    }
    
    const duckRes = await axios({
      method: 'post',
      url: 'https://duckduckgo.com/duckchat/v1/chat',
      headers: {
        'x-vqd-4': duckVqd,
        'Content-Type': 'application/json'
      },
      data: {
        model: 'claude-3-haiku',
        messages: messages
      }
    });
    
    res.json({
      content: duckRes.data?.message || '',
      model: 'claude-3-haiku'
    });
    
  } catch (error) {
    console.error('❌ Error:', error.message);
    res.status(500).json({ error: error.message });
  }
});

module.exports = router;