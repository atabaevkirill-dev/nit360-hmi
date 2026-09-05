// Копирует клиент Socket.IO из node_modules в renderer/vendor,
// чтобы интерфейс не зависел от сети и работал по file://.
const fs = require('fs');
const path = require('path');

const src = path.join(__dirname, '..', 'node_modules', 'socket.io', 'client-dist', 'socket.io.min.js');
const dest = path.join(__dirname, '..', 'renderer', 'vendor', 'socket.io.min.js');

fs.mkdirSync(path.dirname(dest), { recursive: true });
fs.copyFileSync(src, dest);
console.log(`[sync-client] ${path.relative(process.cwd(), dest)} обновлён`);
