// ══════════════════════════════════════════════════════════════
//  NIT-360 — протокол, последовательный порт и Socket.IO сервис.
//  Используется и Electron-процессом (electron/main.js), и
//  браузерным dev-режимом (scripts/dev-server.js).
// ══════════════════════════════════════════════════════════════
const { Server } = require('socket.io');
const { SerialPort } = require('serialport');

const STATUS_SUCCESS = 0x01;
const DEFAULT_ID = 0x09;
const FRAME_LEN = 7;
const RESPONSE_TIMEOUT = 2000;
const DEMO_PATH = 'DEMO';

const BAUD_MAP = { '2400': 0x00, '9600': 0x01, '19200': 0x02 };
const LANGUAGE_MAP = { EN: 0x00, RU: 0x01 };

const COMMANDS = {
  focus_far:        { code: 0x01, nameRu: 'Фокус Далеко' },
  focus_near:       { code: 0x08, nameRu: 'Фокус Близко' },
  focus_auto:       { code: 0x2B, nameRu: 'Автофокус' },
  zoom_tele:        { code: 0x20, nameRu: 'Зум +' },
  zoom_wide:        { code: 0x40, nameRu: 'Зум -' },
  polarity_pos:     { code: 0x7F, nameRu: 'Полярность +' },
  polarity_neg:     { code: 0x81, nameRu: 'Полярность -' },
  int_time_plus:    { code: 0x83, nameRu: 'Время интеграции +' },
  int_time_minus:   { code: 0x85, nameRu: 'Время интеграции -' },
  dde_on:           { code: 0x87, nameRu: 'DDE ВКЛ' },
  dde_off:          { code: 0x89, nameRu: 'DDE ВЫКЛ' },
  dzoom_x1:         { code: 0x8B, nameRu: 'Цифр. зум x1' },
  dzoom_x2:         { code: 0x8D, nameRu: 'Цифр. зум x2' },
  dzoom_x4:         { code: 0x8F, nameRu: 'Цифр. зум x4' },
  nuc:              { code: 0x91, nameRu: 'НУК' },
  brightness_plus:  { code: 0x93, nameRu: 'Яркость +' },
  brightness_minus: { code: 0x95, nameRu: 'Яркость -' },
  contrast_plus:    { code: 0x97, nameRu: 'Контраст +' },
  contrast_minus:   { code: 0x99, nameRu: 'Контраст -' },
  ir_manual:        { code: 0xA7, nameRu: 'Ручная ИК' },
  ir_auto:          { code: 0xA9, nameRu: 'Авто ИК' },
  crosshair_on:     { code: 0x9B, nameRu: 'Перекрестие ВКЛ' },
  crosshair_off:    { code: 0x9D, nameRu: 'Перекрестие ВЫКЛ' },
  set_id:           { code: 0x9F, nameRu: 'Установить ID' },
  set_baud:         { code: 0xA1, nameRu: 'Установить скорость' },
  fov_large:        { code: 0xA3, nameRu: 'Большое ПЗ' },
  fov_small:        { code: 0xA5, nameRu: 'Малое ПЗ' },
  filter_on:        { code: 0xAD, nameRu: 'Фильтр ВКЛ' },
  filter_off:       { code: 0xAF, nameRu: 'Фильтр ВЫКЛ' },
  check_comm:       { code: 0xB1, nameRu: 'Проверка связи' },
  set_language:     { code: 0xB3, nameRu: 'Смена языка' },
  get_runtime:      { code: 0xB5, nameRu: 'Наработка часов' },
};

const CODE_TO_NAME = Object.fromEntries(
  Object.values(COMMANDS).map((c) => [c.code, c.nameRu])
);

// ── Кадр: FF <id> 00 <code> <param> 00 <xor байтов 1..5> ──────
function calculateChecksum(bytes) {
  let cs = 0;
  for (let i = 1; i <= 5; i++) cs ^= bytes[i];
  return cs;
}

function buildCommand(deviceId, code, param = 0x00) {
  const frame = Buffer.alloc(FRAME_LEN);
  frame[0] = 0xff;
  frame[1] = deviceId;
  frame[2] = 0x00;
  frame[3] = code;
  frame[4] = param;
  frame[5] = 0x00;
  frame[6] = calculateChecksum(frame);
  return frame;
}

// Команды, у которых байты 4 и 5 несут не статус, а 16-битное значение
// (старший байт первым). Статус у них не проверяется: у наработки 1274 ч
// старший байт равен 0x04, и правило «0x01 = успех» забраковало бы
// совершенно нормальный ответ.
const DATA_REPLY_CODES = new Set([COMMANDS.get_runtime.code]);

// code — опкод запроса; по нему решается, статус в байте 4 или данные.
function parseResponse(data, code) {
  if (data.length !== FRAME_LEN) return { success: false, status: -1, error: 'Длина кадра' };
  if (data[0] !== 0xff) return { success: false, status: -2, error: 'Заголовок кадра' };
  if (data[6] !== calculateChecksum(data)) return { success: false, status: -3, error: 'Контрольная сумма' };

  const value = ((data[4] << 8) | data[5]) & 0xffff;
  const isData = code !== undefined && DATA_REPLY_CODES.has(code);
  return {
    success: isData ? true : data[4] === STATUS_SUCCESS,
    status: data[4],
    t1: data[4],
    t2: data[5],
    value,
  };
}

// Ресурс, после которого прибор считается вышедшим из гарантии.
const WARRANTY_HOURS = 10000;

function isOutOfWarranty(hours) {
  return hours > WARRANTY_HOURS;
}

// 1274 → «1 274 ч · 53 сут»
function formatHours(hours) {
  const grouped = String(hours).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  const days = Math.floor(hours / 24);
  return days ? `${grouped} ч · ${days} сут` : `${grouped} ч`;
}

function bufferToHex(buf) {
  return Array.from(buf)
    .map((b) => b.toString(16).toUpperCase().padStart(2, '0'))
    .join(' ');
}

// ── Сборка потока байтов в кадры по 7 байт с ресинхронизацией ─
class FrameParser {
  constructor(onFrame) {
    this.buf = Buffer.alloc(0);
    this.onFrame = onFrame;
  }
  push(chunk) {
    this.buf = Buffer.concat([this.buf, chunk]);
    for (;;) {
      const start = this.buf.indexOf(0xff);
      if (start === -1) {
        this.buf = Buffer.alloc(0);
        return;
      }
      if (start > 0) this.buf = this.buf.subarray(start);
      if (this.buf.length < FRAME_LEN) return;
      const frame = Buffer.from(this.buf.subarray(0, FRAME_LEN));
      this.buf = this.buf.subarray(FRAME_LEN);
      this.onFrame(frame);
    }
  }
  reset() {
    this.buf = Buffer.alloc(0);
  }
}

// ── Эмулятор устройства для работы без железа ─────────────────
class DemoDevice {
  constructor() {
    // NIT360_DEMO_HOURS позволяет проверить пороги, например негарантийную наработку
    this.runtime = (Number(process.env.NIT360_DEMO_HOURS) || 1274) & 0xffff;
  }
  respond(frame) {
    const code = frame[3];
    const param = frame[4];
    const out = Buffer.alloc(FRAME_LEN);
    out[0] = 0xff;
    out[1] = frame[1];
    out[2] = 0x00;
    out[3] = code;
    if (code === 0xb5) {
      out[4] = (this.runtime >> 8) & 0xff;
      out[5] = this.runtime & 0xff;
    } else {
      out[4] = STATUS_SUCCESS;
      out[5] = param;
    }
    out[6] = calculateChecksum(out);
    return out;
  }
}

// ── Транспорт: одна команда за раз, FIFO-очередь ──────────────
class Transport {
  constructor(log) {
    this.log = log;
    this.port = null;
    this.demo = null;
    this.queue = [];
    this.pending = null;
    this.parser = new FrameParser((frame) => this.handleFrame(frame));
  }

  get isOpen() {
    return Boolean(this.demo) || Boolean(this.port && this.port.isOpen);
  }

  get path() {
    if (this.demo) return DEMO_PATH;
    return this.port && this.port.isOpen ? this.port.path : null;
  }

  async close() {
    this.failAll('Порт закрыт');
    this.parser.reset();
    this.demo = null;
    const port = this.port;
    this.port = null;
    if (port && port.isOpen) {
      await new Promise((resolve) => port.close(() => resolve()));
    }
  }

  async open({ path, baud }) {
    await this.close();
    if (path === DEMO_PATH) {
      this.demo = new DemoDevice();
      return;
    }
    await new Promise((resolve, reject) => {
      const port = new SerialPort(
        { path, baudRate: baud, dataBits: 8, stopBits: 1, parity: 'none' },
        (err) => (err ? reject(err) : resolve())
      );
      this.port = port;
      port.on('data', (chunk) => this.parser.push(chunk));
      port.on('error', (err) => this.log('error', `Ошибка порта: ${err.message}`));
      port.on('close', () => this.failAll('Порт закрыт'));
    });
  }

  handleFrame(frame) {
    this.log('rx', bufferToHex(frame));
    const pending = this.pending;
    if (!pending) return; // незапрошенный кадр — игнорируем
    if (frame[3] !== pending.frame[3]) return; // ответ не на текущую команду
    clearTimeout(pending.timer);
    this.pending = null;
    pending.resolve(parseResponse(frame, pending.frame[3]));
    this.drain();
  }

  failAll(message) {
    if (this.pending) {
      clearTimeout(this.pending.timer);
      this.pending.reject(new Error(message));
      this.pending = null;
    }
    const queued = this.queue.splice(0);
    for (const item of queued) item.reject(new Error(message));
  }

  send(deviceId, code, param = 0x00) {
    if (!this.isOpen) return Promise.reject(new Error('Порт не подключён'));
    const frame = buildCommand(deviceId, code, param);
    return new Promise((resolve, reject) => {
      this.queue.push({ frame, resolve, reject });
      this.drain();
    });
  }

  drain() {
    if (this.pending || this.queue.length === 0) return;
    const item = this.queue.shift();
    this.pending = item;
    item.timer = setTimeout(() => {
      if (this.pending !== item) return;
      this.pending = null;
      item.reject(new Error(`Таймаут ответа (${RESPONSE_TIMEOUT} мс)`));
      this.drain();
    }, RESPONSE_TIMEOUT);

    this.log('tx', bufferToHex(item.frame));

    if (this.demo) {
      const reply = this.demo.respond(item.frame);
      setTimeout(() => this.parser.push(reply), 60);
      return;
    }
    this.port.write(item.frame, (err) => {
      if (err && this.pending === item) {
        clearTimeout(item.timer);
        this.pending = null;
        item.reject(err);
        this.drain();
      }
    });
  }
}

// ── Socket.IO сервис ──────────────────────────────────────────
const STATE_MAP = {
  polarity_pos: ['polarity', 'positive'],
  polarity_neg: ['polarity', 'negative'],
  dde_on: ['dde', true],
  dde_off: ['dde', false],
  dzoom_x1: ['digitalZoom', 'x1'],
  dzoom_x2: ['digitalZoom', 'x2'],
  dzoom_x4: ['digitalZoom', 'x4'],
  crosshair_on: ['crosshair', true],
  crosshair_off: ['crosshair', false],
  fov_large: ['fov', 'large'],
  fov_small: ['fov', 'small'],
  filter_on: ['filter', true],
  filter_off: ['filter', false],
  ir_manual: ['irMode', 'manual'],
  ir_auto: ['irMode', 'auto'],
};

function startService({ port = 3003 } = {}) {
  const io = new Server({ cors: { origin: '*' }, path: '/socket.io' });

  let deviceId = DEFAULT_ID;
  let currentBaud = 9600;

  const deviceState = {
    polarity: 'positive',
    dde: false,
    digitalZoom: 'x1',
    crosshair: false,
    fov: 'large',
    filter: false,
    irMode: 'auto',
    language: 'RU',
    runtimeHours: 0,
  };

  const log = (type, data) => io.emit('log', { type, data, timestamp: Date.now() });
  const transport = new Transport(log);

  const statusPayload = () => ({
    connected: transport.isOpen,
    port: transport.path,
    baud: currentBaud,
    id: deviceId,
    demo: Boolean(transport.demo),
  });
  const broadcastStatus = () => io.emit('connection_status', statusPayload());

  async function run(socket, cmdId, code, param) {
    try {
      const result = await transport.send(deviceId, code, param);
      socket.emit('command_result', { cmdId, success: result.success, status: result.status });
      if (result.success) {
        io.emit('command_ok', { code, name: CODE_TO_NAME[code] || 'Команда' });
      } else if (result.error) {
        log('error', `${CODE_TO_NAME[code] || cmdId}: ${result.error}`);
      }
      return result;
    } catch (err) {
      socket.emit('command_result', { cmdId, success: false, status: -1, error: err.message });
      log('error', `${CODE_TO_NAME[code] || cmdId}: ${err.message}`);
      return null;
    }
  }

  io.on('connection', (socket) => {
    socket.emit('state', deviceState);
    socket.emit('connection_status', statusPayload());

    socket.on('get_ports', async () => {
      try {
        const ports = await SerialPort.list();
        socket.emit(
          'ports_list',
          ports.map((p) => ({
            path: p.path,
            manufacturer: p.manufacturer || '',
            vendorId: p.vendorId || '',
          }))
        );
      } catch (err) {
        socket.emit('ports_list', []);
        socket.emit('error', { message: 'Не удалось получить список портов: ' + err.message });
      }
    });

    socket.on('connect_port', async (config = {}) => {
      try {
        deviceId = Number(config.id) || DEFAULT_ID;
        currentBaud = Number(config.baud) || 9600;
        await transport.open({ path: config.path, baud: currentBaud });
        broadcastStatus();
        log(
          'info',
          transport.demo
            ? 'Демо-режим: команды обрабатывает встроенный эмулятор'
            : `Подключено: ${config.path} @ ${currentBaud} бод, ID: ${deviceId}`
        );
      } catch (err) {
        broadcastStatus();
        socket.emit('error', { message: err.message });
        log('error', `Не удалось открыть порт: ${err.message}`);
      }
    });

    socket.on('disconnect_port', async () => {
      await transport.close();
      broadcastStatus();
      log('info', 'Порт закрыт');
    });

    socket.on('send_command', async (cmdId) => {
      const cmd = COMMANDS[cmdId];
      if (!cmd) {
        socket.emit('error', { message: `Неизвестная команда: ${cmdId}` });
        return;
      }
      const result = await run(socket, cmdId, cmd.code);
      if (result && result.success && STATE_MAP[cmdId]) {
        const [key, value] = STATE_MAP[cmdId];
        deviceState[key] = value;
        io.emit('state', deviceState);
      }
    });

    socket.on('set_id', async (newId) => {
      const id = Number(newId);
      if (!Number.isInteger(id) || id < 0 || id > 255) {
        socket.emit('error', { message: 'ID должен быть в диапазоне 0–255' });
        return;
      }
      const result = await run(socket, 'set_id', COMMANDS.set_id.code, id);
      if (result && result.success) {
        deviceId = id;
        broadcastStatus();
      }
    });

    socket.on('set_baud', async (baudStr) => {
      const baudCode = BAUD_MAP[String(baudStr)];
      if (baudCode === undefined) {
        socket.emit('error', { message: 'Неизвестная скорость' });
        return;
      }
      const result = await run(socket, 'set_baud', COMMANDS.set_baud.code, baudCode);
      if (result && result.success) {
        currentBaud = parseInt(baudStr, 10);
        broadcastStatus();
        log('info', `Скорость устройства изменена на ${currentBaud} бод — переподключитесь на этой скорости`);
      }
    });

    socket.on('set_language', async (lang) => {
      const langCode = LANGUAGE_MAP[lang];
      if (langCode === undefined) {
        socket.emit('error', { message: 'Неизвестный язык' });
        return;
      }
      const result = await run(socket, 'set_language', COMMANDS.set_language.code, langCode);
      if (result && result.success) {
        deviceState.language = lang;
        io.emit('state', deviceState);
      }
    });

    socket.on('get_runtime', async () => {
      const result = await run(socket, 'get_runtime', COMMANDS.get_runtime.code);
      if (result && result.success) {
        deviceState.runtimeHours = result.value;
        io.emit('state', deviceState);
        const alarm = isOutOfWarranty(result.value);
        socket.emit('runtime', { hours: result.value, text: formatHours(result.value), alarm });
        log(
          alarm ? 'error' : 'info',
          `Наработка прибора: ${formatHours(result.value)}${alarm ? ' — ВНЕ ГАРАНТИИ' : ''}`
        );
      }
    });
  });

  io.listen(port);

  return {
    io,
    async stop() {
      await transport.close();
      io.close();
    },
  };
}

module.exports = {
  startService,
  formatHours,
  isOutOfWarranty,
  WARRANTY_HOURS,
  COMMANDS,
  DEMO_PATH,
  buildCommand,
  parseResponse,
  calculateChecksum,
  FrameParser,
};
