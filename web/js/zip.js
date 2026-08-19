/*
 * zip.js — كاتب ZIP صغير بلا ضغط، لتنزيل دفعة ملفات Markdown في ملف واحد.
 *
 * لماذا بلا ضغط (طريقة store): الضغط في المتصفح يعني إمّا مكتبة خارجية —
 * وهي تخرق سياسة المصدر الواحد التي تحمي خصوصية الأداة — أو واجهة
 * CompressionStream غير المتاحة في كل المتصفحات. والملفات نصّ Markdown
 * ينتظره المستخدم على قرصه لا على الشبكة، فالحجم ليس العائق.
 *
 * الأسماء العربية تتطلّب الرايةَ 0x0800 التي تعلن أن اسم الملف UTF-8؛
 * بدونها يفكّها ويندوز بترميز صفحة الرموز المحلية فتخرج طلاسم.
 */

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let c = n;
    for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c >>> 0;
  }
  return table;
})();

function crc32(bytes) {
  let c = 0xffffffff;
  for (let i = 0; i < bytes.length; i += 1) {
    c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  }
  return (c ^ 0xffffffff) >>> 0;
}

/**
 * يبني ملف ZIP من [{name, text}] ويرجّع Blob.
 * الأسماء المكرّرة تُميَّز بلاحقة رقمية: أرشيف فيه اسمان متطابقان يفكّه
 * بعض الأدوات إلى ملف واحد، فيختفي ناتجُ أحد الملفات بلا إنذار.
 */
export function zipText(entries) {
  const encoder = new TextEncoder();
  const seen = new Map();
  const parts = [];
  const central = [];
  let offset = 0;

  for (const entry of entries) {
    let name = entry.name;
    if (seen.has(name)) {
      const n = seen.get(name) + 1;
      seen.set(name, n);
      const dot = name.lastIndexOf('.');
      name = dot > 0 ? `${name.slice(0, dot)}-${n}${name.slice(dot)}` : `${name}-${n}`;
    } else {
      seen.set(name, 1);
    }

    const nameBytes = encoder.encode(name);
    const data = encoder.encode(entry.text);
    const crc = crc32(data);

    const local = new DataView(new ArrayBuffer(30));
    local.setUint32(0, 0x04034b50, true); // توقيع الترويسة المحلية
    local.setUint16(4, 20, true); // أدنى إصدار لازم للفك
    local.setUint16(6, 0x0800, true); // الاسم بترميز UTF-8
    local.setUint16(8, 0, true); // بلا ضغط
    local.setUint16(10, 0, true); // وقت — ثابت ليكون البناء قابلًا للتكرار
    local.setUint16(12, 0x0021, true); // تاريخ ١٩٨٠-٠١-٠١
    local.setUint32(14, crc, true);
    local.setUint32(18, data.length, true);
    local.setUint32(22, data.length, true);
    local.setUint16(26, nameBytes.length, true);
    local.setUint16(28, 0, true); // بلا حقول إضافية
    parts.push(new Uint8Array(local.buffer), nameBytes, data);

    const dir = new DataView(new ArrayBuffer(46));
    dir.setUint32(0, 0x02014b50, true);
    dir.setUint16(4, 20, true);
    dir.setUint16(6, 20, true);
    dir.setUint16(8, 0x0800, true);
    dir.setUint16(10, 0, true);
    dir.setUint16(12, 0, true);
    dir.setUint16(14, 0x0021, true);
    dir.setUint32(16, crc, true);
    dir.setUint32(20, data.length, true);
    dir.setUint32(24, data.length, true);
    dir.setUint16(28, nameBytes.length, true);
    dir.setUint32(42, offset, true);
    central.push(new Uint8Array(dir.buffer), nameBytes);

    offset += 30 + nameBytes.length + data.length;
  }

  const dirBytes = central.reduce((sum, part) => sum + part.length, 0);
  const end = new DataView(new ArrayBuffer(22));
  end.setUint32(0, 0x06054b50, true);
  end.setUint16(8, entries.length, true);
  end.setUint16(10, entries.length, true);
  end.setUint32(12, dirBytes, true);
  end.setUint32(16, offset, true);

  return new Blob([...parts, ...central, new Uint8Array(end.buffer)], {
    type: 'application/zip',
  });
}
