# -*- coding: utf-8 -*-
"""
core.py — محرّك الاستخراج في PDF2MD.

معايَر على ملفات PDF عربية مصدَّرة من Word ثم معالَجة عبر macOS/iOS
(محرّك Quartz). هذه الملفات تحمل خللًا في خريطة ToUnicode يجعل الرباطات
العربية تُخزَّن معكوسة، فتخرج «املادة» بدل «المادة».

كل الإصلاحات هنا هندسية بحتة: مبنية على إحداثيات الحروف وعلى بكسلات
الصفحة المرسومة. لا قاموس ولا تخمين لغوي.

المشاكل التي يعالجها هذا الملف — وكلها مرصودة فعليًا في ملفات حقيقية:
  1. رباط مقلوب     : الحرف الثاني بعرض صفر      -> نبدّله      (املادة → المادة)
  2. سطر مكسور      : PyMuPDF يقسّم عند تغيّر الاتجاه -> نعيد بناءه بصريًا
  3. مسافة وهمية    : مسافة في المجرى لا تُرسم    -> فحص الحبر   (يقتض ي → يقتضي)
  4. مسافة مفقودة   : لا مسافة في المجرى          -> قاعدة الفجوة
  5. رقم معكوس      : LTR داخل RTL               -> عكس التسلسل (6/5/1436 → 1436/6/5)
  6. تشكيل طائر     : يسبق حرفه في المجرى         -> ربط إحداثي  (يوما.ً → يوماً.)
"""

import re
import unicodedata

# الاسم `fitz` مهجور معلَن بالإزالة داخل خط 1.x من PyMuPDF، والحدّ `<2` في
# requirements.txt لا يحمي منه. نستورد الاسم الجديد أولًا ونسقط للقديم على
# الإصدارات الأقدم من 1.24.3 التي لا تعرفه بعد.
try:
    import pymupdf as fitz
except ImportError:                     # PyMuPDF < 1.24.3
    import fitz

import numpy as np

__version__ = "2.0.0"

# ═══════════════ ثوابت المعايرة ═══════════════
# مستخرَجة من قياس فعلي على ٢٨ ألف فجوة في مستندات حقيقية.
# عدّلها فقط إن واجهت ملفًا بخصائص مختلفة جذريًا.

ZERO_W = 0.05        # عرض الحرف الذي يُعتبر «صفرًا» -> جزء رباط
GAP_RATIO = 0.13     # فجوة ÷ حجم الخط أكبر منها = مسافة بين كلمتين
INK_MAX = 0.06       # كثافة حبر داخل المسافة أعلى منها = المسافة وهمية
INK_BAND = 0.78      # نفحص أعلى ٧٨٪ من السطر (نتجاهل الذيول والتسطير)
Y_TOL = 0.55         # تسامح رأسي (× أقصى ارتفاع) لضم جزأين في سطر بصري
CELL_GAP = 6.0       # فجوة أفقية تفصل خلايا الجدول
INK_DPI = 150        # دقة رسم الصفحة لفحص الحبر

# نسبة التقليص من كل جهة قبل قياس الحبر داخل الفجوة
INK_PAD = 0.30
# تداخل أفقي أكبر من هذه النسبة من أصغر عرض = الجزآن ليسا على سطر واحد
SEG_CLASH = 0.50

# ═══════════════ خرائط ورموز ═══════════════

AR_LETTER = re.compile(r"[ء-ي]")

MARK = "\u0000"     # علامة حدّ داخلية (موضع مسافة مرشّحة)
DIAC = "\u0001"     # بادئة وحدة تشكيل

TASHKEEL = set(
    "ًٌٍَُِّْ"
    "ٰٕٖٓٔٗ٘ـ"
)

# الأرقام الهندية والفارسية أرقام «قوية» مثل اللاتينية في اتجاه الكتابة،
# لأنها تظهر مختلطة داخل العدد الواحد.
LTR_STRONG = re.compile(r"[0-9A-Za-z٠-٩۰-۹]")
NUM_SEP = set("/.,:-٫٬")

# رموز التحكم الاتجاهي — تُحذف نهائيًا
BIDI_CTRL = dict.fromkeys(
    [0x200E, 0x200F, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
     0x2066, 0x2067, 0x2068, 0x2069, 0x00AD, 0xFEFF], None
)

AR2WEST = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩"
    "۰۱۲۳۴۵۶۷۸۹",
    "01234567890123456789"
)


class Unit:
    """وحدة نصية واحدة (حرف أو رباط مُصلَح) مع موقعها على الصفحة."""

    __slots__ = ("t", "x0", "y0", "x1", "y1",
                 "size", "font", "flags", "sid", "lid", "glue")

    def __init__(self, t, bbox, size, font, flags, sid=-1, lid=0):
        self.t = t
        self.x0, self.y0, self.x1, self.y1 = bbox
        self.size, self.font, self.flags = size, font, flags
        self.sid = sid          # رقم الـ span
        self.lid = lid          # رقم سطر rawdict (الجزء)
        self.glue = False       # لا تُدرج مسافة قبلها مهما كانت الفجوة

    @property
    def yc(self):
        return (self.y0 + self.y1) / 2

    @property
    def h(self):
        return self.y1 - self.y0

    @property
    def w(self):
        return self.x1 - self.x0

    @property
    def bold(self):
        return bool(self.flags & 16) or "Bold" in self.font

    @property
    def is_mark(self):
        return self.t == MARK

    @property
    def is_diac(self):
        return self.t.startswith(DIAC)


# ═══════════════ ١. الاستخراج وإصلاح الرباطات ═══════════════

def page_units(page, stats=None, fix_ligatures=True):
    """
    يقرأ الصفحة بـ rawdict ويحوّلها إلى قائمة وحدات بإحداثياتها.

    إصلاح الرباط المقلوب
    ────────────────────
    في هذه الملفات يُرسم الرباط بجليف واحد، فيُصدَّر حرفاه كالتالي:
    الحرف الأول بعرض صفر (لأنه ملتصق بالجليف)، والحرف الثاني يحمل
    الصندوق كاملًا — لكن ترتيبهما في المجرى معكوس.

    القاعدة: أي حرف عرضه <= ZERO_W وليس علامة تشكيل، يُبدَّل مع الحرف
    الذي يليه مباشرة. النتيجة: chars[i+1] + chars[i].

    القاعدة عامة ولا تُقيَّد بحرف اللام، فتغطي تلقائيًا:
    لا لأ لإ لآ لم لح لج لخ تا با في — وأي رباط آخر في أي خط.
    """
    units = []
    sid = lid = 0

    for blk in page.get_text("rawdict")["blocks"]:
        if blk["type"] != 0:           # صور وغيرها
            continue
        for line in blk["lines"]:
            lid += 1
            for span in line["spans"]:
                chars = span.get("chars") or []
                size, font = span["size"], span["font"]
                flags = span.get("flags", 0)
                sid += 1

                i, n = 0, len(chars)
                while i < n:
                    c = chars[i]
                    g = c["c"]

                    # مسافة -> علامة حدّ. نحتفظ بموقعها لفحص الحبر لاحقًا،
                    # ولا نثبتها كمسافة حقيقية إلا بعد أن تنجو من الفحص.
                    if g.isspace():
                        units.append(Unit(MARK, c["bbox"], size, font, 0, sid, lid))
                        i += 1
                        continue

                    # تشكيل -> يُؤجَّل ويُربط لاحقًا بالحرف الذي يحتويه إحداثيًا
                    if g in TASHKEEL:
                        units.append(Unit(DIAC + g, c["bbox"], size, font,
                                          flags, sid, lid))
                        i += 1
                        continue

                    # رباط مقلوب
                    if (fix_ligatures
                            and (c["bbox"][2] - c["bbox"][0]) <= ZERO_W
                            and i + 1 < n
                            and not chars[i + 1]["c"].isspace()
                            and chars[i + 1]["c"] not in TASHKEEL):
                        base = chars[i + 1]
                        units.append(Unit(base["c"] + g, base["bbox"], size,
                                          font, flags, sid, lid))
                        if stats is not None:
                            stats["lig"] = stats.get("lig", 0) + 1
                            pairs = stats.setdefault("pairs", {})
                            key = base["c"] + g
                            pairs[key] = pairs.get(key, 0) + 1
                        i += 2
                        continue

                    units.append(Unit(g, c["bbox"], size, font, flags, sid, lid))
                    i += 1
    return units


# ═══════════════ ٢. فحص الحبر ═══════════════

def ink_map(page, dpi=INK_DPI):
    """
    يرسم الصفحة رماديًا ويرجّع (خريطة ثنائية للحبر، معامل التكبير).
    البكسل الأغمق من ١٢٨ يُعدّ حبرًا.
    """
    z = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(z, z), colorspace=fitz.csGRAY)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    return (arr < 128), z


def _inked(right, left, ink, z, y0, y1):
    """
    هل الفجوة بين وحدتين عربيتين مرسوم فيها حبر؟

    بعض المسافات موجودة في مجرى النص لكنها لا تُرسم، لأن الحرف المجاور
    مرسوم فوق موضعها — فتخرج «يقتض ي» و«الأ صلي» و«المرسو م».

    نأخذ المنطقة بين x1 للحرف الأيسر و x0 للحرف الأيمن، ونقلّصها INK_PAD
    من كل جهة (حتى لا نلتقط حواف الحرفين)، ونحدّ النطاق الرأسي بأعلى
    INK_BAND من السطر (لتجاهل الذيول والتسطير).

    القياس الفعلي: المسافة الحقيقية <= ٢٪ حبر، والوهمية ٩–٢١٪.
    فالعتبة INK_MAX = ٦٪ تفصل بينهما بهامش واسع من الجهتين.
    """
    if ink is None:
        return False
    # الفحص للعربي فقط — الفجوات اللاتينية ليس فيها هذا العيب
    if not (AR_LETTER.match(right.t[0]) and AR_LETTER.match(left.t[0])):
        return False
    if right.x0 < left.x0:                # ضمان أن right هو الأيمن فعلًا
        right, left = left, right

    gx0, gx1 = left.x1, right.x0
    if gx1 - gx0 <= 0.3:
        return True                       # لا فجوة أصلًا => نفس الكلمة

    pad = (gx1 - gx0) * INK_PAD
    px0, px1 = int((gx0 + pad) * z), int((gx1 - pad) * z)
    if px1 <= px0:                        # فجوة أضيق من أن تُقلَّص
        px0, px1 = int(gx0 * z), int(gx1 * z)

    py0, py1 = int(y0 * z), int(y1 * z)
    if py1 <= py0 or px1 <= px0:
        return False

    band = ink[max(0, py0):py1, max(0, px0):px1]
    return bool(band.size) and float(band.mean()) > INK_MAX


# ═══════════════ ٣. عكس تسلسلات الأرقام ═══════════════

def reverse_ltr_runs(units):
    """
    الأرقام تُكتب من اليسار لليمين داخل نص RTL، فبعد الترتيب البصري
    يمين->يسار تخرج معكوسة. نعكس كل تسلسل رقمي/لاتيني ليعود لترتيبه المنطقي.

    الفواصل العددية (/ . , : -) الواقعة بين رقمين تُضمّ داخل التسلسل نفسه،
    وإلا انكسر التاريخ إلى أجزاء معكوسة كل جزء على حدة.

    كل وحدة داخل التسلسل المعكوس (عدا الأولى) تُعلَّم glue، حتى لا تعيد
    قاعدة الفجوة إدراج مسافة داخل العدد بعد أن تغيّر ترتيبه.
    """
    out, i, n = [], 0, len(units)
    while i < n:
        u = units[i]
        if u.is_mark or not LTR_STRONG.match(u.t[0]):
            out.append(u)
            i += 1
            continue

        # نمدّ التسلسل ما دام رقمًا/لاتينيًا، أو فاصلًا عدديًا يليه رقم
        j = i
        while j < n:
            k = j
            while k < n and not units[k].is_mark and LTR_STRONG.match(units[k].t[0]):
                k += 1
            j = k
            if (j < n and not units[j].is_mark and units[j].t in NUM_SEP
                    and j + 1 < n and not units[j + 1].is_mark
                    and LTR_STRONG.match(units[j + 1].t[0])):
                j += 1
                continue
            break

        run = list(reversed(units[i:j]))
        for r in run[1:]:
            r.glue = True
        out.extend(run)
        i = j
    return out


# ═══════════════ ٤. بناء السطر البصري ═══════════════

def _seg_box(seg):
    """(x0, x1, مركز y، أقصى ارتفاع) لجزء — بتجاهل علامات الحدّ."""
    real = [u for u in seg if not u.is_mark] or seg
    return (min(u.x0 for u in real), max(u.x1 for u in real),
            sum(u.yc for u in real) / len(real), max(u.h for u in real))


def _group_segments(units):
    """
    يجمع أجزاء rawdict في أسطر بصرية.

    PyMuPDF يقسّم السطر الواحد عند كل تغيّر اتجاه، فسطر مثل
    «المادة الثانية والعشرون (22): (1)» يخرج خمسة أجزاء.

    الشرطان معًا لضمّ جزء إلى سطر:
      • تقارب رأسي  : فرق مركز y <= Y_TOL × أقصى ارتفاع
      • عدم تداخل أفقي: التداخل < SEG_CLASH من أصغر عرض

    فحص التداخل يجري على كل جزء سبق ضمّه بمفرده، لا على الصندوق الجامع.
    لو فُحص على الصندوق الجامع لرُفضت الأرقام الواقعة بين جزأين عربيين،
    لأنها تقع داخل امتداد الصندوق الكلي وإن لم تلامس أي جزء منه.

    يرجّع (قائمة المجموعات، قائمة صناديق الأجزاء لكل مجموعة).
    """
    segs = {}
    for u in units:
        segs.setdefault(u.lid, []).append(u)
    segs = sorted(segs.values(), key=lambda s: min(u.yc for u in s))

    groups, meta = [], []      # meta[k] = (صناديق الأجزاء، مركز y، أقصى ارتفاع)
    for seg in segs:
        x0, x1, yc, hh = _seg_box(seg)
        placed = False
        for k, (boxes, gyc, gh) in enumerate(meta):
            if abs(yc - gyc) > max(hh, gh, 1.0) * Y_TOL:
                continue
            clash = any(
                min(x1, bx1) - max(x0, bx0) > min(x1 - x0, bx1 - bx0) * SEG_CLASH
                for bx0, bx1 in boxes
            )
            if clash:
                continue
            groups[k].extend(seg)
            boxes.append((x0, x1))
            meta[k] = (boxes, gyc + (yc - gyc) / len(boxes), max(gh, hh))
            placed = True
            break
        if not placed:
            groups.append(list(seg))
            meta.append(([(x0, x1)], yc, hh))

    order = sorted(range(len(groups)), key=lambda k: meta[k][1])
    return [groups[k] for k in order], [meta[k][0] for k in order]


def _attach_diacritics(group):
    """
    يربط كل علامة تشكيل بالحرف العربي الذي يحتوي موقعها إحداثيًا.

    علامات التشكيل تُصدَّر وحدات منفصلة وقد تسبق حرفها في المجرى، فلو
    رُبطت بالحرف السابق في المجرى لخرجت «يوما.ً» بدل «يوماً.».

    كثير من العلامات يُصدَّر بعرض صفر عند موضع القلم، أي على الحدّ تمامًا
    بين حرفين — فيحتويها الحرفان معًا. عندها نرجّح الأقرب مركزًا، وهو
    ترجيح هندسي محض لا يعتمد على ترتيب المجرى.
    """
    letters = [u for u in group
               if not u.is_mark and not u.is_diac and AR_LETTER.match(u.t[0])]
    if letters:
        for u in group:
            if not u.is_diac:
                continue
            xm = (u.x0 + u.x1) / 2
            host = min(letters, key=lambda v: (
                0.0 if v.x0 <= xm <= v.x1 else min(abs(v.x0 - xm), abs(v.x1 - xm)),
                abs((v.x0 + v.x1) / 2 - xm),
            ))
            host.t += u.t[1:]
    return [u for u in group if not u.is_diac]


def _is_numeric(u):
    return (not u.is_mark) and (LTR_STRONG.match(u.t[0]) or u.t in NUM_SEP)


def _join_units(units, rtl, ink, z, band_y0, band_y1):
    """
    يجمع وحدات مرتّبة بترتيب القراءة في نص واحد.

    المسافات من المجرى (علامات الحدّ) ومن الفجوات كلتاهما تمرّان على فحص
    الحبر، وإلا أعادت قاعدة الفجوة إدراج المسافة الوهمية بعد أن حذفها الفحص.

    الفجوة تُقاس من «الجبهة» — أبعد حافة بلغها السطر بصريًا — لا من إحداثيات
    الوحدة السابقة في ترتيب القراءة. الفرق يظهر بعد عكس تسلسل رقمي: آخر وحدة
    في القراءة تقع عند الطرف المقابل من العدد، فتُحسب فجوة وهمية بعرض العدد
    كله (3/1 - بدل 3/1-).
    """
    parts, prev, pending, front = [], None, False, None
    for u in units:
        if u.is_mark:
            pending = True
            continue
        if prev is not None and not pending and not u.glue:
            gap = (front - u.x1) if rtl else (u.x0 - front)
            if gap > GAP_RATIO * max(prev.size, u.size):
                pending = True
        if pending and parts and prev is not None:
            if not _inked(prev, u, ink, z, band_y0, band_y1):
                parts.append(" ")
        parts.append(u.t)
        edge = u.x0 if rtl else u.x1
        front = edge if front is None else (min(front, edge) if rtl
                                            else max(front, edge))
        prev, pending = u, False
    return tidy("".join(parts))


def _split_cells(units, seg_boxes, rtl, ink, z, band_y0, band_y1):
    """
    يقسّم وحدات صف جدول إلى خلايا نصية، خلية لكل جزء من أجزاء rawdict.

    الأجزاء تُرتَّب باتجاه القراءة (تنازليًا حسب الحافة اليمنى في RTL)، وكل
    وحدة تُنسب للصندوق الذي يحتوي مركزها. الترتيب داخل الخلية محفوظ لأن
    `units` وصلت مرتّبة أصلًا، والترشيح لا يغيّر ترتيبها.
    """
    ordered = sorted(seg_boxes, key=(lambda b: -b[1]) if rtl else (lambda b: b[0]))
    cells = []
    for bx0, bx1 in ordered:
        part = [u for u in units if bx0 - 0.5 <= (u.x0 + u.x1) / 2 <= bx1 + 0.5]
        text = _join_units(part, rtl, ink, z, band_y0, band_y1) if part else ""
        cells.append(text)
    return cells


def build_lines(units, ink=None, z=1.0):
    """يحوّل وحدات الصفحة إلى أسطر نصية مرتّبة بصريًا."""
    if not units:
        return []

    groups, boxes = _group_segments(units)
    lines = []

    for group, seg_boxes in zip(groups, boxes):
        # صف جدول: أربعة أجزاء فأكثر تفصلها فجوات أفقية واسعة
        ordered = sorted(seg_boxes, key=lambda b: -b[1])
        is_row = len(ordered) >= 4 and all(
            ordered[k][0] - ordered[k + 1][1] >= CELL_GAP
            for k in range(len(ordered) - 1)
        )

        group = _attach_diacritics(group)

        # اتجاه السطر: فيه حرف عربي => تنازليًا حسب x1، وإلا تصاعديًا حسب x0
        rtl = any(AR_LETTER.match(u.t[0]) for u in group if not u.is_mark)
        group.sort(key=(lambda u: -u.x1) if rtl else (lambda u: u.x0))

        real = [u for u in group if not u.is_mark]
        if not real:
            continue

        # النطاق الرأسي لفحص الحبر: أعلى INK_BAND من السطر
        band_y0 = min(u.y0 for u in real)
        band_y1 = band_y0 + (max(u.y1 for u in real) - band_y0) * INK_BAND

        # مسافة محصورة بين رقمين أو فواصل عددية تكسر التاريخ
        # (6/5/1436 بدل 1436/6/5) — تُسقط قبل عكس التسلسل.
        group = [u for k, u in enumerate(group)
                 if not (u.is_mark and 0 < k < len(group) - 1
                         and _is_numeric(group[k - 1]) and _is_numeric(group[k + 1]))]

        if rtl:
            group = reverse_ltr_runs(group)

        text = _join_units(group, rtl, ink, z, band_y0, band_y1)
        if text:
            # خلايا الصف تُستخرَج فقط لصفوف الجداول، وتُستهلَك في
            # structure.py لبناء جدول Markdown حقيقي.
            cells = (_split_cells(group, seg_boxes, rtl, ink, z, band_y0, band_y1)
                     if is_row else [])
            lines.append({
                "text": text,
                "x0": min(u.x0 for u in real), "x1": max(u.x1 for u in real),
                "y0": min(u.y0 for u in real), "y1": max(u.y1 for u in real),
                "size": max(u.size for u in real),
                "bold": any(u.bold for u in real),
                "row": is_row,
                "cells": cells,
            })
    return lines


# ═══════════════ ٥. التنظيف النهائي ═══════════════

_RE_OPEN = re.compile(r"([\(\[\{«])\s+")
_RE_CLOSE = re.compile(r"\s+([\)\]\}»])")
_RE_PUNCT = re.compile(r"\s+([،؛,:.!؟])")
_RE_SLASH = re.compile(r"(?<=\d)\s*/\s*(?=\d)")
_RE_HIJRI = re.compile(r"(?<=\d)\s+(هـ|هجري[ةه]?|م)(?=[\s.،؛)\]]|$)")
_RE_WS = re.compile(r"\s+")


def tidy(s):
    """
    تنظيف نهائي على مستوى السطر:
      • حذف رموز التحكم الاتجاهي، وتطبيع NFC
      • إزالة المسافة بعد فتح القوس وقبل إغلاقه وقبل علامات الترقيم
      • توحيد الشرطة المائلة بين رقمين
      • ضمّ لاحقة التاريخ:  «1442 هـ» -> «1442هـ»
    """
    s = unicodedata.normalize("NFC", s.translate(BIDI_CTRL))
    s = _RE_WS.sub(" ", s)
    s = _RE_OPEN.sub(r"\1", s)
    s = _RE_CLOSE.sub(r"\1", s)
    s = _RE_PUNCT.sub(r"\1", s)
    s = _RE_SLASH.sub("/", s)
    s = _RE_HIJRI.sub(r"\1", s)
    s = _RE_WS.sub(" ", s)
    return s.strip()


# ═══════════════ الواجهة العامة ═══════════════

def page_lines(page, stats=None, unify_digits=True, check_ink=True,
               fix_ligatures=True):
    """
    يرجّع أسطر صفحة واحدة: قائمة قواميس فيها
    text / x0 / x1 / y0 / y1 / size / bold / row.

    stats قاموس اختياري يُجمَّع فيه عدد الرباطات المُصلَحة وأنواعها.
    """
    ink, z = ink_map(page) if check_ink else (None, 1.0)
    lines = build_lines(page_units(page, stats, fix_ligatures), ink, z)
    if unify_digits:
        for line in lines:
            line["text"] = line["text"].translate(AR2WEST)
    return lines
