/* ══ NIT-360 HMI — логика интерфейса ══════════════════════════ */
(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const DEMO_PATH = 'DEMO';
  const HOLD_DELAY = 400;   // мс до старта автоповтора
  const HOLD_PERIOD = 260;  // мс между повторами

  const ui = {
    ledService: $('led-service'),
    ledLink: $('led-link'),
    ledTraffic: $('led-traffic'),
    runtime: $('rd-runtime'),
    clock: $('rd-clock'),
    connChip: $('conn-chip'),
    connHint: $('conn-hint'),
    selPort: $('sel-port'),
    selBaud: $('sel-baud'),
    inpId: $('inp-id'),
    btnConnect: $('btn-connect'),
    btnDisconnect: $('btn-disconnect'),
    btnRefresh: $('btn-refresh'),
    log: $('log'),
    cntTx: $('cnt-tx'),
    cntRx: $('cnt-rx'),
    cntErr: $('cnt-err'),
    sbMsg: $('sb-msg'),
    sbVersion: $('sb-version'),
  };

  const counters = { tx: 0, rx: 0, err: 0 };
  let connected = false;
  let logPaused = false;
  let trafficTimer = null;

  // ── Служебные ──────────────────────────────────────────────
  function setStatus(text, state) {
    ui.sbMsg.textContent = text;
    if (state) ui.sbMsg.dataset.state = state;
    else delete ui.sbMsg.dataset.state;
  }

  function blinkTraffic(type) {
    ui.ledTraffic.dataset.state = type === 'error' ? 'error' : 'on';
    clearTimeout(trafficTimer);
    trafficTimer = setTimeout(() => {
      ui.ledTraffic.dataset.state = 'off';
    }, 140);
  }

  const WARRANTY_HOURS = 10000;

  // 1274 → «1 274 ч · 53 сут»
  function formatHours(hours) {
    const grouped = String(hours).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
    const days = Math.floor(hours / 24);
    return days ? `${grouped} ч · ${days} сут` : `${grouped} ч`;
  }

  function stamp(ts) {
    const d = new Date(ts || Date.now());
    return (
      String(d.getHours()).padStart(2, '0') + ':' +
      String(d.getMinutes()).padStart(2, '0') + ':' +
      String(d.getSeconds()).padStart(2, '0') + '.' +
      String(d.getMilliseconds()).padStart(3, '0')
    );
  }

  function appendLog(entry) {
    if (entry.type === 'tx') counters.tx++;
    if (entry.type === 'rx') counters.rx++;
    if (entry.type === 'error') counters.err++;
    ui.cntTx.textContent = counters.tx;
    ui.cntRx.textContent = counters.rx;
    ui.cntErr.textContent = counters.err;
    blinkTraffic(entry.type);

    if (logPaused) return;

    const line = document.createElement('div');
    line.className = 'log-line';
    line.dataset.type = entry.type;
    const tag = { tx: 'TX', rx: 'RX', info: '···', error: 'ERR' }[entry.type] || '···';
    line.innerHTML =
      `<span class="log-time"></span><span class="log-tag"></span><span class="log-data"></span>`;
    line.children[0].textContent = stamp(entry.timestamp);
    line.children[1].textContent = tag;
    line.children[2].textContent = entry.data;

    const atBottom = ui.log.scrollHeight - ui.log.scrollTop - ui.log.clientHeight < 40;
    ui.log.appendChild(line);
    while (ui.log.childElementCount > 500) ui.log.firstElementChild.remove();
    if (atBottom) ui.log.scrollTop = ui.log.scrollHeight;
  }

  // ── Блокировка органов управления по состоянию связи ───────
  function setControlsEnabled(on) {
    document
      .querySelectorAll('[data-cmd], #btn-runtime, #btn-setid, #btn-setbaud, #seg-lang .seg-btn')
      .forEach((el) => {
        el.disabled = !on;
      });
  }

  function applyConnection(s) {
    connected = Boolean(s && s.connected);
    const demo = Boolean(s && s.demo);

    ui.ledLink.dataset.state = connected ? (demo ? 'warn' : 'on') : 'off';
    ui.connChip.textContent = connected ? (demo ? 'ДЕМО-РЕЖИМ' : 'НА СВЯЗИ') : 'НЕТ СВЯЗИ';
    if (connected) ui.connChip.dataset.state = demo ? 'demo' : 'on';
    else delete ui.connChip.dataset.state;

    ui.btnConnect.disabled = connected;
    ui.btnDisconnect.disabled = !connected;
    ui.selPort.disabled = connected;
    ui.selBaud.disabled = connected;
    ui.inpId.disabled = connected;
    ui.btnRefresh.disabled = connected;
    setControlsEnabled(connected);

    if (connected) {
      ui.connHint.textContent = demo
        ? 'Встроенный эмулятор прибора. Команды не уходят в порт.'
        : `${s.port} · ${s.baud} бод · 8N1 · ID ${s.id}`;
      delete ui.connHint.dataset.state;
    } else {
      ui.connHint.textContent = 'Формат кадра 8N1, 7 байт, XOR-контроль.';
    }
  }

  function applyState(state) {
    const text = {
      polarity: { positive: 'БЕЛОЕ-ГОРЯЧЕЕ', negative: 'ЧЁРНОЕ-ГОРЯЧЕЕ' },
      irMode: { auto: 'АВТО', manual: 'РУЧНОЙ' },
      fov: { large: 'БОЛЬШОЕ', small: 'МАЛОЕ' },
    };
    $('st-polarity').textContent = text.polarity[state.polarity] || '—';
    $('st-dzoom').textContent = '×' + String(state.digitalZoom || '').replace('x', '');
    $('st-dde').textContent = state.dde ? 'ВКЛ' : 'ВЫКЛ';
    $('st-crosshair').textContent = state.crosshair ? 'ВКЛ' : 'ВЫКЛ';
    $('st-filter').textContent = state.filter ? 'ВКЛ' : 'ВЫКЛ';
    $('st-fov').textContent = text.fov[state.fov] || '—';
    $('st-ir').textContent = text.irMode[state.irMode] || '—';
    $('st-lang').textContent = state.language === 'EN' ? 'ENG' : 'РУС';
    const hours = state.runtimeHours;
    const alarm = hours > WARRANTY_HOURS;
    const stRuntime = $('st-runtime');

    ui.runtime.textContent = hours ? String(hours).replace(/\B(?=(\d{3})+(?!\d))/g, ' ') + ' ч' : '—';
    stRuntime.textContent = hours ? formatHours(hours) + (alarm ? ' · ВНЕ ГАРАНТИИ' : '') : '—';
    ui.runtime.classList.toggle('is-alarm', alarm);
    stRuntime.classList.toggle('is-alarm', alarm);
    ui.runtime.title = alarm ? `Наработка превысила ресурс ${WARRANTY_HOURS} ч — прибор вне гарантии` : '';

    press('seg-polarity', state.polarity);
    press('seg-ir', state.irMode);
    press('seg-fov', state.fov);
    press('seg-dzoom', state.digitalZoom);
    press('seg-dde', String(Boolean(state.dde)));
    press('seg-crosshair', String(Boolean(state.crosshair)));
    press('seg-filter', String(Boolean(state.filter)));
    press('seg-lang', state.language, 'lang');
  }

  function press(segId, value, attr) {
    const seg = $(segId);
    if (!seg) return;
    const key = attr || 'val';
    seg.querySelectorAll('.seg-btn').forEach((b) => {
      b.setAttribute('aria-pressed', String(b.dataset[key] === value));
    });
  }

  // ── Подключение к сервису ──────────────────────────────────
  async function ioPort() {
    const fromQuery = new URLSearchParams(location.search).get('ioPort');
    if (fromQuery) return Number(fromQuery);
    if (window.electronAPI) {
      try {
        return await window.electronAPI.getIoPort();
      } catch { /* используем значение по умолчанию */ }
    }
    return 3003;
  }

  async function boot() {
    if (window.electronAPI) {
      window.electronAPI
        .getAppVersion()
        .then((v) => { ui.sbVersion.textContent = 'v' + v; })
        .catch(() => {});
    }

    const port = await ioPort();
    const socket = io(`http://127.0.0.1:${port}`, {
      transports: ['websocket', 'polling'],
      reconnectionDelay: 800,
      reconnectionDelayMax: 3000,
    });

    socket.on('connect', () => {
      ui.ledService.dataset.state = 'on';
      setStatus('Сервис RS-422 подключён', 'ok');
      socket.emit('get_ports');
    });

    socket.on('disconnect', () => {
      ui.ledService.dataset.state = 'error';
      setStatus('Сервис RS-422 недоступен', 'error');
      applyConnection({ connected: false });
    });

    socket.on('connect_error', () => {
      ui.ledService.dataset.state = 'error';
      setStatus('Нет соединения с сервисом (порт ' + port + ')', 'error');
    });

    socket.on('ports_list', (ports) => {
      const prev = ui.selPort.value;
      ui.selPort.innerHTML = '';
      for (const p of ports) {
        const opt = document.createElement('option');
        opt.value = p.path;
        opt.textContent = p.manufacturer ? `${p.path} — ${p.manufacturer}` : p.path;
        ui.selPort.appendChild(opt);
      }
      const demo = document.createElement('option');
      demo.value = DEMO_PATH;
      demo.textContent = 'ДЕМО — эмулятор прибора';
      ui.selPort.appendChild(demo);
      ui.selPort.value = prev && [...ui.selPort.options].some((o) => o.value === prev)
        ? prev
        : (ports[0] ? ports[0].path : DEMO_PATH);
      setStatus(ports.length ? `Найдено портов: ${ports.length}` : 'COM-порты не найдены — доступен демо-режим');
    });

    socket.on('connection_status', (s) => {
      const wasConnected = connected;
      applyConnection(s);
      if (connected && !wasConnected) setTimeout(() => socket.emit('get_runtime'), 150);
    });
    socket.on('state', applyState);
    socket.on('log', appendLog);
    socket.on('command_ok', (d) => setStatus(`${d.name} — выполнено`, 'ok'));

    socket.on('command_result', (r) => {
      if (!r.success) {
        setStatus(r.error || `Команда отклонена (статус ${r.status})`, 'error');
      }
    });

    socket.on('error', (e) => {
      setStatus(e.message, 'error');
      appendLog({ type: 'error', data: e.message, timestamp: Date.now() });
    });

    socket.on('runtime', (d) => {
      const text = d.text || formatHours(d.hours);
      if (d.alarm) setStatus(`Наработка прибора: ${text} — ВНЕ ГАРАНТИИ`, 'error');
      else setStatus(`Наработка прибора: ${text}`, 'ok');
    });

    // ── Обработчики интерфейса ───────────────────────────────
    ui.btnRefresh.addEventListener('click', () => socket.emit('get_ports'));

    ui.btnConnect.addEventListener('click', () => {
      const path = ui.selPort.value;
      if (!path) {
        setStatus('Выберите порт', 'error');
        return;
      }
      setStatus(`Подключение к ${path}…`);
      socket.emit('connect_port', {
        path,
        baud: Number(ui.selBaud.value),
        id: Number(ui.inpId.value),
      });
    });

    ui.btnDisconnect.addEventListener('click', () => socket.emit('disconnect_port'));
    $('btn-runtime').addEventListener('click', () => socket.emit('get_runtime'));
    $('btn-setid').addEventListener('click', () => socket.emit('set_id', Number($('inp-newid').value)));
    $('btn-setbaud').addEventListener('click', () => socket.emit('set_baud', $('sel-newbaud').value));

    $('seg-lang').addEventListener('click', (e) => {
      const btn = e.target.closest('.seg-btn');
      if (btn && !btn.disabled) socket.emit('set_language', btn.dataset.lang);
    });

    $('btn-clear').addEventListener('click', () => {
      ui.log.innerHTML = '';
      counters.tx = counters.rx = counters.err = 0;
      ui.cntTx.textContent = ui.cntRx.textContent = ui.cntErr.textContent = '0';
    });

    $('btn-pause').addEventListener('click', (e) => {
      logPaused = !logPaused;
      e.target.textContent = logPaused ? 'ПРОДОЛЖИТЬ' : 'ПАУЗА';
      e.target.style.color = logPaused ? 'var(--amber)' : '';
    });

    // Кнопки с data-cmd: клик, а для .btn-hold — автоповтор при удержании
    const fire = (el) => {
      if (el.disabled || !connected) return;
      socket.emit('send_command', el.dataset.cmd);
      el.classList.add('is-firing');
      setTimeout(() => el.classList.remove('is-firing'), 120);
    };

    document.querySelectorAll('[data-cmd]').forEach((el) => {
      if (!el.classList.contains('btn-hold')) {
        el.addEventListener('click', () => fire(el));
        return;
      }
      let startTimer = null;
      let repeatTimer = null;
      const stop = () => {
        clearTimeout(startTimer);
        clearInterval(repeatTimer);
        startTimer = repeatTimer = null;
      };
      el.addEventListener('pointerdown', (e) => {
        if (e.button !== 0) return;
        fire(el);
        startTimer = setTimeout(() => {
          repeatTimer = setInterval(() => fire(el), HOLD_PERIOD);
        }, HOLD_DELAY);
      });
      ['pointerup', 'pointerleave', 'pointercancel'].forEach((ev) =>
        el.addEventListener(ev, stop)
      );
      window.addEventListener('blur', stop);
    });

    applyConnection({ connected: false });
  }

  // дата приглушена, время — основной акцент; обе части в одном поле шапки
  function tickClock() {
    const now = new Date();
    const date = now.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
    const time = now.toLocaleTimeString('ru-RU', { hour12: false });
    ui.clock.innerHTML = '';
    const dateEl = document.createElement('span');
    dateEl.className = 'clock-date';
    dateEl.textContent = date;
    ui.clock.appendChild(dateEl);
    ui.clock.appendChild(document.createTextNode(time));
  }
  setInterval(tickClock, 1000);
  tickClock();

  boot();
})();
