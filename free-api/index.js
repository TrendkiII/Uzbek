const express = require('express');
const bodyParser = require('body-parser');
const cors = require('cors');
const chatRoute = require('./routes/chat');

const app = express();
const PORT = process.env.PORT || 3032;

app.use(cors());
app.use(bodyParser.json());

// ВАЖНО: монтируем роутер
app.use('/', chatRoute);

// Альтернативный health check
app.get('/health', (req, res) => {
  res.json({ status: 'alive' });
});

app.get('/', (req, res) => {
  res.json({ 
    status: 'ok', 
    message: 'Claude API Proxy',
    endpoints: ['/health', '/v1/models', '/v1/chat/completions']
  });
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`✅ Free API running on port ${PORT}`);
});