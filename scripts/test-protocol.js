// Проверка кодека протокола NIT-360: сборка кадра, разбор ответа,
// пересборка потока байтов в кадры. Запуск: npm test
const assert = require('assert');
const {
  buildCommand,
  parseResponse,
  calculateChecksum,
  formatHours,
  isOutOfWarranty,
  WARRANTY_HOURS,
  FrameParser,
} = require('../electron/serial-service');

function frame(code, b4, b5) {
  const f = Buffer.from([0xff, 9, 0, code, b4, b5, 0]);
  f[6] = calculateChecksum(f);
  return f;
}

const tests = {
  'кадр имеет длину 7 байт и заголовок 0xFF'() {
    const f = buildCommand(0x09, 0x91);
    assert.strictEqual(f.length, 7);
    assert.strictEqual(f[0], 0xff);
  },
  'контрольная сумма — XOR байтов 1..5'() {
    const f = buildCommand(0x09, 0x91, 0x02);
    assert.strictEqual(f[6], calculateChecksum(f));
    assert.strictEqual(f[6], f[1] ^ f[2] ^ f[3] ^ f[4] ^ f[5]);
  },
  'корректный ответ разбирается как успешный'() {
    const r = parseResponse(Buffer.from([0xff, 9, 0, 0x91, 0x01, 0, 0x99]));
    assert.strictEqual(r.success, true);
  },
  'битая контрольная сумма отвергается'() {
    assert.strictEqual(parseResponse(Buffer.from([0xff, 9, 0, 0x91, 1, 0, 0x00])).status, -3);
  },
  'кадр неверной длины отвергается'() {
    assert.strictEqual(parseResponse(Buffer.from([0xff, 9, 0])).status, -1);
  },
  'ответ с наработкой не проверяется по байту статуса'() {
    // 1274 ч = 0x04FA: старший байт 0x04, а не 0x01 — ответ обязан быть успешным
    const r = parseResponse(frame(0xb5, 0x04, 0xfa), 0xb5);
    assert.strictEqual(r.success, true);
    assert.strictEqual(r.value, 1274);
  },
  'у обычной команды байт статуса по-прежнему решает исход'() {
    assert.strictEqual(parseResponse(frame(0x91, 0x04, 0x00), 0x91).success, false);
    assert.strictEqual(parseResponse(frame(0x91, 0x01, 0x00), 0x91).success, true);
  },
  'наработка разбирается на краях диапазона'() {
    for (const hours of [0, 1, 255, 256, 1274, 0xffff]) {
      const r = parseResponse(frame(0xb5, (hours >> 8) & 0xff, hours & 0xff), 0xb5);
      assert.strictEqual(r.value, hours);
    }
  },
  'порог гарантии — строго больше 10 000 ч'() {
    assert.strictEqual(WARRANTY_HOURS, 10000);
    assert.strictEqual(isOutOfWarranty(10000), false);
    assert.strictEqual(isOutOfWarranty(10001), true);
    assert.strictEqual(isOutOfWarranty(0), false);
  },
  'часы форматируются с разрядами и сутками'() {
    assert.strictEqual(formatHours(1274), '1 274 ч · 53 сут');
    assert.strictEqual(formatHours(12), '12 ч');
  },
  'парсер отбрасывает мусор и собирает кадры из потока по байту'() {
    const f = buildCommand(0x09, 0x01);
    const got = [];
    const parser = new FrameParser((fr) => got.push(fr.toString('hex')));
    for (const b of Buffer.concat([Buffer.from([0x00, 0x11]), f, f])) {
      parser.push(Buffer.from([b]));
    }
    assert.strictEqual(got.length, 2);
    assert.strictEqual(got[0], f.toString('hex'));
  },
};

let failed = 0;
for (const [name, fn] of Object.entries(tests)) {
  try {
    fn();
    console.log(`  ✓ ${name}`);
  } catch (err) {
    failed++;
    console.error(`  ✗ ${name}\n    ${err.message}`);
  }
}
console.log(`\n${Object.keys(tests).length - failed} из ${Object.keys(tests).length} пройдено`);
process.exit(failed ? 1 : 0);
