/*
 * app.js — واجهة PDF2MD في المتصفح.
 *
 * نظير gui.py: القائمة نفسها، والخيارات نفسها، والألسنة الثلاثة نفسها —
 * فوق المحرّك نفسه حرفيًا (src/*.py يعمل داخل المتصفح بلا تعديل).
 */

import { Engine, Stopped } from './engine.js';
import { zipText } from './zip.js';

const $ = (id) => document.getElementById(id);

const OPTION_FIELDS = {
  profile: { el: 'optProfile', kind: 'value' },
  title: { el: 'optTitle', kind: 'value' },
  footnotes: { el: 'optFootnotes', kind: 'value' },
  h_top: { el: 'optHTop', kind: 'int' },
  h_sub: { el: 'optHSub', kind: 'int' },
  page_from: { el: 'optFrom', kind: 'int' },
  page_to: { el: 'optTo', kind: 'int' },
  para_gap: { el: 'optGap', kind: 'float' },
  fix_ligatures: { el: 'optLig', kind: 'bool' },
  check_ink: { el: 'optInk', kind: 'bool' },
  unify_digits: { el: 'optDigits', kind: 'bool' },
  drop_headers: { el: 'optHeaders', kind: 'bool' },
  drop_watermark: { el: 'optWatermark', kind: 'bool' },
  drop_toc: { el: 'optDropToc', kind: 'bool' },
  build_toc: { el: 'optBuildToc', kind: 'bool' },
  tables: { el: 'optTables', kind: 'bool' },
};

const STORE_OPTIONS = 'pdf2md.options';
const STORE_THEME = 'pdf2md.theme';
const LOG_LIMIT = 4000; // أسطر — سجل بلا سقف يلتهم الذاكرة على الدفعات

const state = {
  files: [], // {id, file, status}
  results: [], // {name, markdown, source}
  running: false,
  stopping: false,
  logLines: [],
  nextId: 1,
};

// ═══════════════ أدوات صغيرة ═══════════════

function human(bytes) {
  if (bytes < 1024) return `${bytes} بايت`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} ك.ب`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} م.ب`;
}

function say(line) {
  state.logLines.push(line);
  if (state.logLines.length > LOG_LIMIT) {
    state.logLines.splice(0, state.logLines.length - LOG_LIMIT);
  }
  const box = $('log');
  box.textContent = state.logLines.join('\n');
  box.scrollTop = box.scrollHeight;
}

function status(text) {
  $('status').textContent = text;
}

function progress(pct) {
  $('jobBar').style.width = `${Math.max(0, Math.min(100, pct))}%`;
}

function download(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // التحرير مؤجَّل: إبطال العنوان فورًا يسبق بدء التنزيل في بعض المتصفحات
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

// ═══════════════ المظهر ═══════════════

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  $('btnTheme').textContent = theme === 'dark' ? '☀️' : '🌙';
  try {
    localStorage.setItem(STORE_THEME, theme);
  } catch (err) {
    void err; // تصفّح خاص يمنع التخزين — المظهر يبقى لهذه الجلسة فقط
  }
}

function initTheme() {
  let saved = null;
  try {
    saved = localStorage.getItem(STORE_THEME);
  } catch (err) {
    void err;
  }
  const dark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  applyTheme(saved || (dark ? 'dark' : 'light'));
  $('btnTheme').addEventListener('click', () => {
    applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
  });
}

// ═══════════════ الخيارات ═══════════════

function readOptions() {
  const out = {};
  for (const [key, spec] of Object.entries(OPTION_FIELDS)) {
    const el = $(spec.el);
    if (spec.kind === 'bool') out[key] = el.checked;
    else if (spec.kind === 'int') out[key] = parseInt(el.value, 10) || 0;
    else if (spec.kind === 'float') out[key] = parseFloat(el.value) || 0.75;
    else out[key] = el.value;
  }
  return out;
}

function writeOptions(values) {
  for (const [key, spec] of Object.entries(OPTION_FIELDS)) {
    if (!(key in values)) continue;
    const el = $(spec.el);
    if (spec.kind === 'bool') el.checked = Boolean(values[key]);
    else el.value = values[key];
  }
}

function saveOptions() {
  try {
    localStorage.setItem(STORE_OPTIONS, JSON.stringify(readOptions()));
  } catch (err) {
    void err;
  }
}

function initOptions() {
  // الافتراضي يُلتقط من الصفحة نفسها قبل أي استعادة، فيبقى «استعادة
  // الافتراضي» صادقًا حتى لو تغيّرت القيم في index.html لاحقًا.
  const defaults = readOptions();
  try {
    const saved = localStorage.getItem(STORE_OPTIONS);
    if (saved) writeOptions(JSON.parse(saved));
  } catch (err) {
    say(`تعذّرت استعادة الإعدادات المحفوظة: ${err.message}`);
  }
  for (const spec of Object.values(OPTION_FIELDS)) {
    $(spec.el).addEventListener('change', saveOptions);
  }
  $('btnReset').addEventListener('click', () => {
    writeOptions(defaults);
    saveOptions();
    status('أُعيدت الخيارات إلى الافتراضي.');
  });
}

// ═══════════════ قائمة الملفات ═══════════════

function renderFiles() {
  const list = $('fileList');
  list.textContent = '';
  for (const item of state.files) {
    const li = document.createElement('li');

    const name = document.createElement('span');
    name.className = 'name';
    name.textContent = item.file.name;
    name.title = item.file.name;

    const size = document.createElement('span');
    size.className = 'size';
    size.textContent = human(item.file.size);

    const stateTag = document.createElement('span');
    stateTag.className = `state ${item.status.kind}`;
    stateTag.textContent = item.status.text;

    const x = document.createElement('button');
    x.className = 'x';
    x.type = 'button';
    x.textContent = '×';
    x.setAttribute('aria-label', `حذف ${item.file.name} من القائمة`);
    x.addEventListener('click', () => {
      if (state.running) return;
      state.files = state.files.filter((f) => f.id !== item.id);
      renderFiles();
    });

    li.append(name, size, stateTag, x);
    list.appendChild(li);
  }
  syncButtons();
}

function addFiles(fileList) {
  const pdfs = Array.from(fileList).filter(
    (f) => f.type === 'application/pdf' || /\.pdf$/i.test(f.name),
  );
  const rejected = fileList.length - pdfs.length;
  for (const file of pdfs) {
    state.files.push({ id: state.nextId++, file, status: { kind: '', text: '' } });
  }
  if (pdfs.length) say(`أُضيف ${pdfs.length} ملف إلى القائمة.`);
  if (rejected) {
    status(`تُجوهل ${rejected} ملف — المقبول ملفات PDF فقط.`);
    say(`تُجوهل ${rejected} ملف ليس بصيغة PDF.`);
  }
  renderFiles();
}

function initFiles() {
  const zone = $('dropZone');
  const input = $('fileInput');

  zone.addEventListener('click', () => input.click());
  zone.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      input.click();
    }
  });
  input.addEventListener('change', () => {
    addFiles(input.files);
    input.value = '';
  });

  for (const type of ['dragenter', 'dragover']) {
    zone.addEventListener(type, (e) => {
      e.preventDefault();
      zone.classList.add('over');
    });
  }
  for (const type of ['dragleave', 'drop']) {
    zone.addEventListener(type, (e) => {
      e.preventDefault();
      zone.classList.remove('over');
    });
  }
  zone.addEventListener('drop', (e) => {
    if (e.dataTransfer && e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
  });
  // الإفلات خارج المنطقة يفتح الملف في لسان جديد ويضيّع عمل المستخدم
  window.addEventListener('dragover', (e) => e.preventDefault());
  window.addEventListener('drop', (e) => e.preventDefault());

  $('btnClear').addEventListener('click', () => {
    state.files = [];
    renderFiles();
    status('أُفرغت القائمة.');
  });
}

// ═══════════════ الألسنة ═══════════════

function initTabs() {
  const tabs = [
    ['tabPreview', 'panePreview'],
    ['tabDiag', 'paneDiag'],
    ['tabLog', 'paneLog'],
  ];
  for (const [tabId] of tabs) {
    $(tabId).addEventListener('click', () => {
      for (const [t, p] of tabs) {
        const on = t === tabId;
        $(t).setAttribute('aria-selected', String(on));
        $(p).hidden = !on;
      }
    });
  }
}

function showTab(tabId) {
  $(tabId).click();
}

// ═══════════════ المخرَجات ═══════════════

function renderResults() {
  const pick = $('outPick');
  pick.textContent = '';
  for (let i = 0; i < state.results.length; i += 1) {
    const option = document.createElement('option');
    option.value = String(i);
    option.textContent = state.results[i].name;
    pick.appendChild(option);
  }
  const has = state.results.length > 0;
  pick.disabled = !has;
  $('btnDownload').disabled = !has;
  $('btnCopy').disabled = !has;
  $('btnDownloadAll').disabled = state.results.length < 2;
  if (has) {
    pick.value = String(state.results.length - 1);
    showResult();
  }
}

function showResult() {
  const item = state.results[Number($('outPick').value)];
  if (!item) return;
  $('preview').textContent = item.preview;
  $('previewNote').hidden = !item.truncated;
  $('previewNote').textContent = item.truncated
    ? 'المعروض أول ٢٠٠ ألف حرف فقط — التنزيل والنسخ يأخذان الناتج كاملًا.'
    : '';
}

function initOutputs() {
  $('outPick').addEventListener('change', showResult);

  $('btnDownload').addEventListener('click', () => {
    const item = state.results[Number($('outPick').value)];
    if (item) download(new Blob([item.markdown], { type: 'text/markdown' }), item.name);
  });

  $('btnDownloadAll').addEventListener('click', () => {
    download(zipText(state.results), 'pdf2md.zip');
  });

  $('btnCopy').addEventListener('click', async () => {
    const item = state.results[Number($('outPick').value)];
    if (!item) return;
    try {
      await navigator.clipboard.writeText(item.markdown);
      status(`نُسخ ناتج ${item.name} إلى الحافظة.`);
    } catch (err) {
      status(`تعذّر النسخ إلى الحافظة: ${err.message}`);
    }
  });
}

// ═══════════════ التشخيص ═══════════════

function renderDiagnosis(d) {
  $('diagInfo').textContent = '';
  const facts = [
    ['الصفحات', d.pages],
    ['العيّنة', `${d.sampled} صفحة`],
    ['الخطوط', d.fonts],
    ['طبقة نص', d.has_text ? 'نعم' : 'لا — يحتاج OCR'],
    ['المنتج', d.producer || '—'],
    ['المُنشئ', d.creator || '—'],
    ['رباطات مُصلَحة في العيّنة', d.ligatures.toLocaleString('ar-EG')],
    ['أكثر الرباطات', d.pairs.map((p) => `${p.pair}×${p.count}`).join('، ') || '—'],
  ];
  for (const [key, value] of facts) {
    const line = document.createElement('div');
    const strong = document.createElement('strong');
    strong.textContent = `${key}: `;
    line.append(strong, document.createTextNode(String(value)));
    $('diagInfo').appendChild(line);
  }

  const verdict = $('diagVerdict');
  verdict.hidden = false;
  verdict.className = `verdict ${d.healthy ? 'ok' : 'bad'}`;
  verdict.textContent = `${d.healthy ? '✓' : '!'} ${d.verdict}`;

  const body = $('diagTable').querySelector('tbody');
  body.textContent = '';
  for (const row of d.rows) {
    const tr = document.createElement('tr');
    if (row.after_bad > 0) tr.className = 'bad';
    for (const cell of [row.word, row.before_ok, row.before_bad, row.after_ok, row.after_bad]) {
      const td = document.createElement('td');
      td.textContent = String(cell);
      tr.appendChild(td);
    }
    body.appendChild(tr);
  }
  $('diagTable').hidden = false;

  $('diagSample').textContent = d.sample || '—';
  $('diagSampleWrap').hidden = false;
  showTab('tabDiag');
}

// ═══════════════ التشغيل ═══════════════

const engine = new Engine((event) => {
  if (event.type === 'boot') {
    $('bootBar').style.width = `${event.pct}%`;
    $('bootMsg').textContent = event.msg;
  } else if (event.type === 'progress') {
    progress(event.pct);
    status(event.msg);
  } else if (event.type === 'log' || event.type === 'stdout') {
    say(event.msg);
  } else if (event.type === 'ready') {
    const a = event.about;
    $('engineChip').textContent = `PDF2MD ${a.version} · PyMuPDF ${a.pymupdf} · Python ${a.python}`;
    $('bootPanel').hidden = true;
    $('main').hidden = false;
    say(`جاهز — PDF2MD ${a.version} على بايثون ${a.python} و PyMuPDF ${a.pymupdf}.`);
    syncButtons();
  } else if (event.type === 'reboot') {
    say('— أُوقفت العملية، وتُعاد تهيئة المحرّك.');
  } else if (event.type === 'error') {
    say(`✗ ${event.msg}`);
  }
});

function syncButtons() {
  const has = state.files.length > 0;
  const ready = Boolean(engine.about);
  $('btnGo').disabled = state.running || !has || !ready;
  $('btnDiag').disabled = state.running || !has || !ready;
  $('btnClear').disabled = state.running || !has;
  $('btnStop').disabled = !state.running;
  $('btnDiag').textContent = has ? `فحص: ${state.files[0].file.name}` : 'فحص تشخيصي';
}

function mark(item, kind, text) {
  item.status = { kind, text };
  renderFiles();
}

async function runBatch() {
  if (state.running) return;
  state.running = true;
  state.stopping = false;
  syncButtons();

  const options = readOptions();
  const queue = state.files.slice();
  let done = 0;
  let failed = 0;

  for (const item of queue) {
    // الملفات المحذوفة من القائمة أثناء الدفعة لا تُحوَّل
    if (state.stopping || !state.files.includes(item)) break;
    mark(item, '', 'جارٍ…');
    say(`\n── ${item.file.name}`);
    try {
      const result = await engine.convert(item.file, options);
      if (!result.ok) {
        failed += 1;
        mark(item, 'bad', 'فشل');
        say(`✗ فشل التحويل: ${result.error}`);
        if (result.trace) say(result.trace);
        continue;
      }
      done += 1;
      mark(item, 'ok', 'تم');
      state.results.push({
        name: result.name,
        markdown: result.markdown,
        preview: result.preview,
        truncated: result.truncated,
        text: result.markdown, // ما يكتبه zip.js
      });
      say(`✓ ${result.name} (${result.stats.chars.toLocaleString('ar-EG')} حرف — ${result.summary})`);
      renderResults();
    } catch (err) {
      if (err instanceof Stopped) {
        mark(item, '', 'أُوقف');
        break;
      }
      failed += 1;
      mark(item, 'bad', 'فشل');
      say(`✗ ${err.message}`);
    }
  }

  state.running = false;
  progress(state.stopping ? 0 : 100);
  syncButtons();
  if (state.stopping) status('أُوقف التحويل بطلب المستخدم.');
  else if (failed) status(`اكتملت الدفعة: ${done} نجحت و${failed} فشلت — راجع السجل.`);
  else status(`تم تحويل ${done} ملف.`);
  if (done) showTab('tabPreview');
}

async function runDiagnose() {
  if (state.running || !state.files.length) return;
  const item = state.files[0];
  state.running = true;
  state.stopping = false;
  syncButtons();
  say(`\n— فحص: ${item.file.name}`);
  try {
    const result = await engine.diagnose(item.file);
    if (result.ok) {
      renderDiagnosis(result);
      status(`اكتمل فحص ${item.file.name}.`);
    } else {
      say(`✗ فشل الفحص: ${result.error}`);
      status('فشل الفحص — راجع السجل.');
    }
  } catch (err) {
    if (err instanceof Stopped) status('أُوقف الفحص بطلب المستخدم.');
    else {
      say(`✗ ${err.message}`);
      status('فشل الفحص — راجع السجل.');
    }
  }
  state.running = false;
  progress(100);
  syncButtons();
}

function initActions() {
  $('btnGo').addEventListener('click', runBatch);
  $('btnDiag').addEventListener('click', runDiagnose);
  $('btnStop').addEventListener('click', () => {
    state.stopping = true;
    status('جارٍ الإيقاف…');
    engine.cancel();
  });
}

// ═══════════════ الإقلاع ═══════════════

initTheme();
initOptions();
initFiles();
initTabs();
initOutputs();
initActions();
renderFiles();

engine.start().catch((err) => {
  $('bootMsg').textContent = `تعذّر إقلاع المحرّك: ${err.message}`;
  $('bootPanel').classList.add('failed');
  document.querySelector('.spinner').style.animation = 'none';
});
