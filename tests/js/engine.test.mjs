/*
 * اختبارات engine.js — الحدّ بين الواجهة والخيط العامل.
 *
 * كان هذا الملف بلا اختبار إطلاقًا، ومرّ منه عيبان يُجمّدان الصفحة تجمّدًا
 * دائمًا لا مخرج منه إلا تحديثها. الخيط العامل يُستبدَل هنا بكائن وهمي
 * يحاكي رسائله، فتُختبر آلة الحالات كلها بلا متصفّح ولا Pyodide.
 *
 *   node --test tests/js/
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import { Engine, Stopped } from '../../web/js/engine.js';

/** ملف وهمي بواجهة File التي يستعملها المحرّك. */
const fakeFile = (name = 'مذكرة.pdf') => ({
  name,
  arrayBuffer: async () => new ArrayBuffer(8),
});

/**
 * يزرع صنف Worker وهميًا يتصرّف حسب `plan`: خطة لكل إقلاع بالترتيب.
 *   'ready'  → يقلع بنجاح          'boot-error' → onerror أثناء الإقلاع
 *   'silent' → يقلع ثم لا يردّ على المهام (خيط مات بلا إشعار)
 */
function installWorker(plan) {
  const workers = [];
  globalThis.Worker = class {
    constructor() {
      this.mode = plan[workers.length] || plan[plan.length - 1];
      this.terminated = false;
      workers.push(this);
    }

    postMessage(msg) {
      if (msg.type !== 'boot') return;          // المهام بلا ردّ ما لم يُطلب
      setTimeout(() => {
        if (this.terminated) return;
        if (this.mode === 'boot-error') this.onerror({ message: 'فشل تحميل زمن التشغيل' });
        else this.onmessage({ data: { type: 'ready', about: { version: '2.0.0' } } });
      }, 1);
    }

    terminate() {
      this.terminated = true;
    }
  };
  return workers;
}

/** يُنشئ محرّكًا ويضمن إسقاط خيطه ومهلته بعد الاختبار. */
function makeEngine(t, silenceMs = 50, listen = () => {}) {
  const engine = new Engine(listen, { silenceMs });
  t.after(() => engine.shutdown());
  return engine;
}

const settles = (promise, ms = 120) =>
  Promise.race([
    promise.then(() => 'resolved', (e) => `rejected: ${e.message}`),
    new Promise((r) => setTimeout(() => r('HANG'), ms)),
  ]);

test('الإقلاع الناجح يسلّم بطاقة التعريف', async (t) => {
  installWorker(['ready']);
  const engine = makeEngine(t);
  assert.deepEqual(await engine.start(), { version: '2.0.0' });
  assert.equal(engine.booting, false);
});

test('الانحدار: إقلاع بديل فاشل بعد «إيقاف» يُرفض ولا يعلَّق', async (t) => {
  // كان `about` يبقى محمّلًا من الجلسة الأولى، فيمنع الشرط `!this.about`
  // رفضَ الوعد، فتبقى الواجهة تحسب المحرّك جاهزًا وأي تحويل يعلّق للأبد.
  installWorker(['ready', 'boot-error']);
  const engine = makeEngine(t);
  await engine.start();

  engine.cancel();
  assert.equal(engine.about, null, 'about لم يُصفَّر مع الخيط الذي جاء منه');

  const outcome = await settles(engine.start());
  assert.match(outcome, /^rejected/, `توقّعنا رفضًا، فجاء: ${outcome}`);
});

test('الانحدار: بعد انهيار قاتل تُقلع مهمة جديدة بخيط جديد', async (t) => {
  // كان الخيط الميت يبقى مرجَّعًا و`ready` محسومًا، فتُرسَل المهمة التالية
  // إلى خيط لا يردّ ولا يُرفض وعدها أبدًا.
  const workers = installWorker(['ready', 'ready']);
  const engine = makeEngine(t);
  await engine.start();

  const first = engine.convert(fakeFile(), {});
  await new Promise((r) => setTimeout(r, 5));
  workers[0].onerror({ message: 'نفاد ذاكرة في الخيط العامل' });
  assert.match(await settles(first), /^rejected: نفاد ذاكرة/);

  assert.equal(engine.worker, null, 'الخيط الميت ما زال مرجَّعًا');
  assert.equal(engine.ready, null, 'ready ما زال محسومًا على خيط ميت');
  assert.equal(workers[0].terminated, true, 'الخيط الميت لم يُنهَ');

  await engine.start();
  assert.equal(workers.length, 2, 'لم يُقلع خيط بديل');
  assert.deepEqual(engine.about, { version: '2.0.0' });
});

test('مهلة الصمت تُنهي المهمة التي لا يردّ عليها الخيط', async (t) => {
  installWorker(['silent']);
  const engine = makeEngine(t, 30);
  await engine.start();
  assert.match(await settles(engine.convert(fakeFile(), {}), 300),
               /^rejected: انقطع الخيط العامل/);
  assert.equal(engine.worker, null);
});

test('رسائل التقدّم تمدّد المهلة فلا تُقطع عملية بطيئة', async (t) => {
  const workers = installWorker(['silent']);
  const engine = makeEngine(t, 60);
  await engine.start();

  const job = engine.convert(fakeFile(), {});
  // نبضات تقدّم كل ٢٠ مللي ثانية لمدة تتجاوز المهلة ثلاث مرات
  const beat = setInterval(
    () => workers[0].onmessage({ data: { type: 'progress', pct: 10, msg: 'جارٍ' } }), 20);
  const outcome = await settles(job, 200);
  clearInterval(beat);
  assert.equal(outcome, 'HANG', `المهلة قطعت عملية حيّة: ${outcome}`);

  workers[0].onmessage({ data: { type: 'result', id: 1, result: { ok: true } } });
  assert.deepEqual(await job, { ok: true });
});

test('«إيقاف» يرفض المهمة الجارية بـStopped لا بخطأ', async (t) => {
  installWorker(['ready']);
  const engine = makeEngine(t);
  await engine.start();
  const job = engine.convert(fakeFile(), {});
  await new Promise((r) => setTimeout(r, 5));
  engine.cancel();
  await assert.rejects(job, (e) => e instanceof Stopped);
});

test('لا مهمتان في وقت واحد — المحرّك خيط واحد', async (t) => {
  installWorker(['ready']);
  const engine = makeEngine(t);
  await engine.start();
  engine.convert(fakeFile(), {}).catch(() => {});
  await new Promise((r) => setTimeout(r, 5));
  await assert.rejects(engine.convert(fakeFile(), {}), /مشغول/);
});
