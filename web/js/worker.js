/*
 * worker.js — خيط العمل الذي يشغّل محرّك PDF2MD داخل المتصفح.
 *
 * لماذا خيط منفصل: التحويل عملية بايثون متزامنة تمتدّ ثوانيَ إلى دقائق،
 * وتشغيلها في الخيط الرئيسي يجمّد الصفحة كلها — لا شريط تقدّم يتحرّك ولا
 * زرّ يستجيب. الخيط هنا يبثّ التقدّم برسائل بينما يعمل.
 *
 * ولماذا الإيقاف يقتل الخيط: بايثون داخل Pyodide لا يُقاطَع من الخارج إلا
 * بذاكرة مشتركة (SharedArrayBuffer)، وهي تتطلّب ترويستَي COOP/COEP لا
 * تُرسلهما GitHub Pages. فالإيقاف الصادق هو إنهاء الخيط ثم إقلاع جديد من
 * الذاكرة المؤقتة للمتصفح — انظر engine.js.
 */

'use strict';

const VENDOR = new URL('../vendor/', self.location.href).href;
const SRC = new URL('../../src/', self.location.href).href;
const MANIFEST = new URL('../runtime.json', self.location.href).href;

// مجلد العمل داخل نظام ملفات المتصفح — مطابق لـ src/web.py:WORK_DIR
const WORK = '/pdf2md';

let pyodide = null;

async function grab(url, what) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`تعذّر تحميل ${what} (${response.status}) من ${url}`);
  }
  return response;
}

async function boot() {
  const manifest = await (await grab(MANIFEST, 'بيان زمن التشغيل')).json();

  self.postMessage({ type: 'boot', pct: 5, msg: 'تحميل مفسّر بايثون…' });
  importScripts(VENDOR + 'pyodide.js');
  pyodide = await loadPyodide({
    indexURL: VENDOR,
    stdout: (line) => self.postMessage({ type: 'stdout', msg: line }),
    stderr: (line) => self.postMessage({ type: 'stdout', msg: line }),
  });

  self.postMessage({ type: 'boot', pct: 45, msg: 'تحميل المكتبات…' });
  // ترتيب مقصود: numpy أولًا لأنه اعتمادية قياس الحبر، ثم PyMuPDF وهو
  // الأثقل (١٨ ميغابايت) فيظهر شريط التقدّم متحرّكًا لا واقفًا عليه وحده.
  const wheels = manifest.wheels;
  for (let i = 0; i < wheels.length; i += 1) {
    await pyodide.loadPackage(VENDOR + wheels[i].file);
    const pct = 45 + Math.round((35 * (i + 1)) / wheels.length);
    self.postMessage({ type: 'boot', pct, msg: `حُمّل ${wheels[i].name}` });
  }

  self.postMessage({ type: 'boot', pct: 82, msg: 'تحميل محرّك PDF2MD…' });
  pyodide.FS.mkdirTree(WORK + '/src');
  pyodide.FS.mkdirTree(WORK + '/work');
  for (const name of manifest.sources) {
    const text = await (await grab(SRC + name, `المصدر ${name}`)).text();
    pyodide.FS.writeFile(`${WORK}/src/${name}`, text, { encoding: 'utf8' });
  }

  pyodide.runPython(`
import sys
if ${JSON.stringify(WORK)} not in sys.path:
    sys.path.insert(0, ${JSON.stringify(WORK)})
import src.web as bridge
`);

  const about = JSON.parse(pyodide.runPython('bridge.about()'));
  self.postMessage({ type: 'ready', about });
}

/**
 * يكتب ملف PDF في نظام ملفات المتصفح ويرجّع مساره.
 * الاسم لا يُشتقّ من اسم الملف الأصلي: أسماء المستخدمين تحمل مسارات
 * وشرطات مائلة وحروفًا لا يقبلها MEMFS، والاسم الحقيقي يُمرَّر بيانًا
 * منفصلًا لبناء اسم المخرَج.
 */
function stage(id, bytes) {
  const path = `${WORK}/work/job-${id}.pdf`;
  pyodide.FS.writeFile(path, new Uint8Array(bytes));
  return path;
}

function unstage(path) {
  try {
    pyodide.FS.unlink(path);
  } catch (err) {
    // ملف مؤقّت تعذّر حذفه لا يُسقط المهمّة — الخيط يُنهى بعد الدفعة
    self.postMessage({ type: 'log', msg: `تعذّر حذف ملف مؤقّت: ${err && err.message}` });
  }
}

/** يشغّل دالّة الجسر ويحرّر ما ينشئه من وسطاء بين اللغتين. */
function callBridge(expression, bindings) {
  const keys = Object.keys(bindings);
  for (const key of keys) pyodide.globals.set(key, bindings[key]);
  try {
    return JSON.parse(pyodide.runPython(expression));
  } finally {
    for (const key of keys) pyodide.globals.delete(key);
  }
}

function handleConvert(msg) {
  const path = stage(msg.id, msg.data);
  const call = 'bridge.convert_file(_path, _opts, _tick, _say, _name)';
  try {
    const result = callBridge(call, {
      _path: path,
      _name: msg.name || '',
      _opts: JSON.stringify(msg.options || {}),
      _tick: (pct, text) =>
        self.postMessage({ type: 'progress', id: msg.id, pct, msg: text }),
      _say: (text) => self.postMessage({ type: 'log', id: msg.id, msg: text }),
    });
    result.source = msg.name;
    self.postMessage({ type: 'result', id: msg.id, kind: 'convert', result });
  } finally {
    unstage(path);
  }
}

function handleDiagnose(msg) {
  const path = stage(msg.id, msg.data);
  try {
    const result = callBridge('bridge.diagnose_file(_path, _tick, _name)', {
      _path: path,
      _name: msg.name || '',
      _tick: (pct, text) =>
        self.postMessage({ type: 'progress', id: msg.id, pct, msg: text }),
    });
    result.source = msg.name;
    self.postMessage({ type: 'result', id: msg.id, kind: 'diagnose', result });
  } finally {
    unstage(path);
  }
}

self.onmessage = async (event) => {
  const msg = event.data;
  try {
    if (msg.type === 'boot') {
      await boot();
    } else if (msg.type === 'convert') {
      handleConvert(msg);
    } else if (msg.type === 'diagnose') {
      handleDiagnose(msg);
    }
  } catch (err) {
    self.postMessage({
      type: 'error',
      id: msg && msg.id,
      fatal: !msg || msg.type === 'boot',
      msg: (err && (err.message || String(err))) || 'خطأ غير معروف',
    });
  }
};
