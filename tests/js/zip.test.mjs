/*
 * اختبارات zip.js — كاتب الأرشيف المكتوب بايتًا بايت.
 *
 * الأرشيف هنا يُبنى يدويًا بلا مكتبة، فأي خطأ في إزاحة حقل أو في حساب
 * CRC يُنتج ملفًا يرفضه فكّاك المستخدم — ولا شيء في المتصفّح يكشف ذلك.
 * الحَكَم هنا تطبيق مستقل تمامًا: وحدة `zipfile` في بايثون.
 */

import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { zipText } from '../../web/js/zip.js';

/** يفكّ الأرشيف ببايثون ويرجّع {الاسم: النص} — تحقّق من تطبيق مستقل. */
async function unzip(blob) {
  const dir = mkdtempSync(join(tmpdir(), 'pdf2md-zip-'));
  const path = join(dir, 'a.zip');
  writeFileSync(path, Buffer.from(await blob.arrayBuffer()));
  const out = execFileSync('python3', ['-c', `
import json, sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as z:
    bad = z.testzip()
    assert bad is None, f"عضو تالف: {bad}"
    print(json.dumps({n: z.read(n).decode("utf-8") for n in z.namelist()}))
`, path], { encoding: 'utf-8' });
  return JSON.parse(out);
}

test('الأرشيف يفكّه تطبيق مستقل بأسماء عربية ومحتوى سليم', async () => {
  const entries = [
    { name: 'مذكرة.md', text: '# مذكرة\nنصّ عربي فيه ياء وهمزة: تفيد الأمر.\n' },
    { name: 'نظام العمل.md', text: '## المادة (١)\nمتن.\n' },
  ];
  const back = await unzip(zipText(entries));
  assert.deepEqual(Object.keys(back).sort(), ['مذكرة.md', 'نظام العمل.md'].sort());
  for (const entry of entries) assert.equal(back[entry.name], entry.text);
});

test('الأسماء المكرّرة تُفضّ فلا يبتلع ملفٌ ناتجَ غيره', async () => {
  const back = await unzip(zipText([
    { name: 'ملف.md', text: 'الأول' },
    { name: 'ملف.md', text: 'الثاني' },
    { name: 'ملف.md', text: 'الثالث' },
  ]));
  assert.equal(Object.keys(back).length, 3, 'ضاع ناتج عند فكّ الأرشيف');
  assert.deepEqual(Object.values(back).sort(), ['الأول', 'الثالث', 'الثاني']);
});

test('الأرشيف الفارغ سليم البنية لا ملفًا تالفًا', async () => {
  assert.deepEqual(await unzip(zipText([])), {});
});
