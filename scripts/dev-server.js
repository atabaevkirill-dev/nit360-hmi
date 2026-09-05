// Браузерный dev-режим: отдаёт renderer/ по HTTP и поднимает тот же
// сервис RS-422, что и Electron. Нужен только для отладки интерфейса
// в браузере — самому приложению (npm start) он не требуется.
const http = require('http');
const fs = require('fs');
const path = require('path');
const { startService } = require('../electron/serial-service');

const ROOT = path.join(__dirname, '..', 'renderer');
const PORT = Number(process.env.PORT) || 3000;
const IO_PORT = Number(process.env.NIT360_IO_PORT) || 3003;

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
};

function resolve(urlPath) {
  const clean = decodeURIComponent(urlPath.split('?')[0]);
  let file = path.join(ROOT, path.normalize(clean));
  if (!file.startsWith(ROOT)) return null;
  if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
  return fs.existsSync(file) ? file : null;
}

startService({ port: IO_PORT });
console.log(`[dev] сервис RS-422 слушает порт ${IO_PORT}`);

http
  .createServer((req, res) => {
    const file = resolve(req.url === '/' ? '/index.html' : req.url);
    if (!file) {
      console.warn('[dev] 404', req.url);
      res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
      res.end('404 ' + req.url);
      return;
    }
    res.writeHead(200, { 'Content-Type': MIME[path.extname(file)] || 'application/octet-stream' });
    fs.createReadStream(file).pipe(res);
  })
  .listen(PORT, () => console.log(`[dev] интерфейс: http://localhost:${PORT}`));
