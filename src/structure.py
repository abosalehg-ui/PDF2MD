# -*- coding: utf-8 -*-
"""
structure.py — طبقة البنية في PDF2MD.

تأخذ الأسطر التي أخرجها core.py وتحوّلها إلى Markdown منظَّم: عناوين،
فقرات ملمومة، بنود مرقّمة، حواشي مؤجَّلة، وفهرس بروابط داخلية.

ثلاثة أنماط (Profiles):
  auto       : كشف العناوين بمقارنة حجم السطر بحجم المتن الغالب
  saudi_law  : أنماط الباب / الفصل / المادة / اللائحة التنفيذية
  plain      : فقرات بلا عناوين

كل الإعدادات تمرّ عبر Options، والتحويل يبثّ تقدّمه عبر progress و log.
"""

import re
from collections import Counter
from dataclasses import dataclass

try:                                  # انظر التعليق في core.py
    import pymupdf as fitz
except ImportError:                     # PyMuPDF < 1.24.3
    import fitz

from . import core


class ConversionCancelled(Exception):
    """أُلغي التحويل بطلب من المستخدم — ليست حالة خطأ."""


# ═══════════════════════ الإعدادات ═══════════════════════

@dataclass
class Options:
    """خيارات التحويل — تُمرَّر كاملة من الواجهة أو من سطر الأوامر."""

    profile: str = "auto"          # auto | saudi_law | plain
    fix_ligatures: bool = True     # إصلاح الرباطات المقلوبة
    check_ink: bool = True         # فحص الحبر (أدق، أبطأ ~٣×)
    unify_digits: bool = True      # توحيد الأرقام الهندية إلى عربية
    drop_headers: bool = True      # حذف الترويسة والتذييل المتكررة
    drop_watermark: bool = True    # حذف العلامة المائية (نص مائل أو باهت)
    drop_toc: bool = True          # تخطّي صفحات الفهرس الأصلية
    footnotes: str = "quote"       # quote | inline | drop
    build_toc: bool = True         # توليد فهرس بروابط داخلية
    tables: bool = True            # بناء جداول Markdown من صفوف الجداول المرصودة
    title: str = ""                # العنوان الرئيسي (فارغ = بلا عنوان)
    page_from: int = 0             # 0 = من البداية
    page_to: int = 0               # 0 = حتى النهاية
    h_top: int = 2                 # مستوى العناوين العليا
    h_sub: int = 3                 # مستوى العناوين الفرعية
    para_gap: float = 0.75         # فجوة رأسية (× ارتفاع السطر) تبدأ فقرة


# ═══════════════════════ الأنماط ═══════════════════════

# saudi_law
RE_BAB = re.compile(r"^الباب\s+\S+")
RE_FASL = re.compile(r"^الفصل\s+\S+")
RE_LAIHA = re.compile(r"^اللائح[ةه]\s+التنفيذي[ةه]\s*:?\s*$")
RE_MADDA = re.compile(r"^الماد[ةه]\s+.{0,60}?\(\s*\d+\s*\)")
RE_MADDA_N = re.compile(r"^الماد[ةه]\s*\(\s*\d+\s*\)")

# عامة
RE_ITEM = re.compile(r"^(\d+(?:\s*/\s*\d+)*)\s*[-–—.)]\s*\S")
RE_BULLET = re.compile(r"^[•▪◦*·]\s*\S")
RE_PAGENO = re.compile(r"^[\d٠-٩]{1,4}$")
RE_FOOT = re.compile(r"^\(\s*[\d٠-٩]+\s*\)")
RE_DEF = re.compile(r"^([^:：]{2,45}?)\s*:\s*(.+)$")
RE_TOCLINE = re.compile(r".+\s[\d٠-٩]{1,4}$")

END_PUNCT = tuple(".:؛!؟")
HEADER_ZONE = 0.085     # أعلى الصفحة — منطقة الترويسة
FOOTER_ZONE = 0.88      # أسفل الصفحة — منطقة التذييل ورقم الصفحة
NOTE_ZONE = 0.45        # الحواشي لا تُلتقط إلا في النصف السفلي
NOTE_SMALLER = 2.0      # الحاشية أصغر من المتن بهذا المقدار على الأقل
INDENT_TOL = 40         # إزاحة أفقية تدل على بداية فقرة جديدة
LINE_WEIGHT_CAP = 80    # سقف مساهمة السطر الواحد في ترجيح حجم المتن


# ═══════════════════════ المُجمِّع ═══════════════════════

class Builder:
    """يجمع مخرجات Markdown سطرًا سطرًا، ويؤجّل الحواشي لنهاية القسم."""

    def __init__(self, opt):
        self.opt = opt
        self.out = []       # أسطر الناتج
        self.buf = []       # أسطر الفقرة الجارية
        self.toc = []       # (المستوى، النص) لتوليد الفهرس
        self.notes = []     # حواشي مؤجَّلة حتى نهاية القسم

    def flush(self):
        """يُنهي الفقرة الجارية بلمّ أسطرها في سطر واحد."""
        if self.buf:
            self.out += [" ".join(self.buf), ""]
            self.buf = []

    def dump_notes(self):
        """يفرغ الحواشي المؤجَّلة — تُستدعى عند كل عنوان جديد وفي النهاية."""
        self.flush()
        if self.opt.footnotes == "drop":
            self.notes = []
            return
        for note in self.notes:
            self.out += [("> " + note) if self.opt.footnotes == "quote" else note, ""]
        self.notes = []

    def para(self, text, new):
        if new:
            self.flush()
        self.buf.append(text)

    def head(self, level, text):
        self.flush()
        self.dump_notes()
        self.out += ["", "#" * level + " " + text, ""]
        self.toc.append((level, text))

    def table(self, rows):
        """
        يبني جدول Markdown من صفوف خلايا. الصف الأول رأس الجدول.

        الصفوف تُسوّى إلى أعرض صف (الخلايا الناقصة تُملأ فراغًا) لأن Markdown
        يتطلب عدد أعمدة ثابتًا، والشرطة العمودية داخل الخلية تُهرَّب وإلا
        كسرت الجدول.
        """
        self.flush()
        width = max(len(r) for r in rows)
        norm = [[c.replace("|", "\\|") for c in r] + [""] * (width - len(r))
                for r in rows]
        self.out.append("| " + " | ".join(norm[0]) + " |")
        self.out.append("|" + "---|" * width)
        for row in norm[1:]:
            self.out.append("| " + " | ".join(row) + " |")
        self.out.append("")


# ═══════════════════════ التصنيف ═══════════════════════

def heading_shaped(text):
    """
    هل يصلح النص أن يكون عنوانًا شكلًا، بغضّ النظر عن حجم خطه؟

    العنوان قصير ولا ينتهي بنقطة أو فاصلة أو فاصلة منقوطة — تلك خواتيم
    الجُمل. النقطتان مستثناتان لأن العناوين القانونية تنتهي بهما كثيرًا
    («المادة الأولى:»)، وتُجرَّد لاحقًا عند بناء العنوان.
    """
    stripped = text.rstrip()
    return len(stripped) < 120 and not stripped.endswith((".", "،", "؛"))


def classify(line, opt, body_size):
    """يرجّع أحد: top | sub | laiha | item | definition | para."""
    t, size, bold = line["text"], line["size"], line["bold"]

    if opt.profile == "saudi_law":
        if RE_LAIHA.match(t):
            return "laiha"
        if size >= body_size + 4 and RE_BAB.match(t):
            return "top"
        if size >= body_size + 1.5 and RE_FASL.match(t):
            return "top"
        if bold and size >= body_size - 0.5 and (RE_MADDA_N.match(t)
                                                 or RE_MADDA.match(t)):
            return "sub"
        if RE_ITEM.match(t) or RE_BULLET.match(t):
            return "item"
        if bold and size >= body_size - 0.5 and RE_DEF.match(t):
            return "definition"
        return "para"

    if opt.profile == "plain":
        return "item" if (RE_ITEM.match(t) or RE_BULLET.match(t)) else "para"

    # auto — الحكم بحجم الخط مقارنًا بحجم المتن الغالب، بشرط شكل العنوان.
    # الحجم وحده لا يكفي: في الصفحة المحشوّة بنص صغير كثيف يخرج حجم المتن
    # الغالب أصغر من المتن الحقيقي، فترتفع الفقرات كلها فوق العتبة وتصير
    # «عناوين». الشكل يمنع ذلك — والجملة المنتهية بنقطة ليست عنوانًا.
    if heading_shaped(t):
        if size >= body_size + 3.5:
            return "top"
        if size >= body_size + 1.2 or (bold and size >= body_size + 0.5):
            return "sub"
    if RE_ITEM.match(t) or RE_BULLET.match(t):
        return "item"
    return "para"


def is_toc_page(lines, body_size):
    """صفحة فهرس أصلية: أغلب أسطرها أصغر من المتن وتنتهي برقم صفحة."""
    cand = [line for line in lines if line["size"] < body_size - 1]
    if len(cand) < 6:
        return False
    hits = sum(1 for line in cand if RE_TOCLINE.match(line["text"]))
    return hits >= max(6, 0.6 * len(cand))


def body_font_size(pages):
    """
    حجم خط المتن الغالب: الأكثر تكرارًا موزونًا بعدد الحروف لا بعدد الأسطر،
    حتى لا يطغى عشرون عنوانًا قصيرًا على مئة سطر متن.

    مساهمة السطر الواحد مسقوفة بـ LINE_WEIGHT_CAP: بدون السقف تغلب حاشيةٌ
    من ثلاثة أسطر طويلة عشرةَ أسطر متن، لأن الوزن يقيس الحروف لا الأسطر.

    السقف وحده لا يكفي حين يكون النص الصغير كثيرَ الأسطر أيضًا (صفحة جدول
    كثيف)، فقد يخرج حجم المتن أصغر من الحقيقي. الحارس ضد الضرر الفعلي —
    ترقية المتن إلى عناوين — في classify لا هنا، فهو يشترط شكل العنوان
    لا مجرد كِبَر الحجم.
    """
    weight = Counter()
    for _, lines, _ in pages:
        for line in lines:
            weight[round(line["size"] * 2) / 2] += min(len(line["text"]),
                                                       LINE_WEIGHT_CAP)
    return weight.most_common(1)[0][0] if weight else 12.0


def boiler_key(text):
    """
    مفتاح مقارنة الترويسة والتذييل: الأرقام مجرّدة لأنها تتغيّر كل صفحة.

    الدالة واحدة عمدًا — الكود الذي يبني مجموعة الترويسات والكود الذي يبحث
    فيها لازم يتفقان حرفيًا على صيغة التطبيع، وأي انحراف بينهما يعطّل حذف
    الترويسات بصمت بلا خطأ ولا تحذير.
    """
    return re.sub(r"[\d٠-٩]+", "#", text)


def repeated_headers(pages, total):
    """
    الترويسة والتذييل تُرصدان بتكرارهما عبر الصفحات لا بموضعهما وحده:
    السطر الواقع في منطقة الترويسة أو التذييل ويتكرر (بعد تجريد
    الأرقام) في ٥٪ من الصفحات على الأقل.
    """
    counter = Counter()
    for _, lines, height in pages:
        counter.update({
            boiler_key(line["text"]) for line in lines
            if (line["y0"] / height < HEADER_ZONE
                or line["y0"] / height > FOOTER_ZONE) and len(line["text"]) > 4
        })
    return {k for k, v in counter.items() if v >= max(3, 0.05 * total)}


def anchor_of(text, seen=None):
    """
    مرساة عنوان صالحة للروابط الداخلية في Markdown.

    التصغير إلزامي: مصيّرات Markdown (ومنها GitHub) تصغّر المراسي دائمًا،
    فعنوان «Chapter One» مرساه `#chapter-one`، ورابط `#Chapter-One` لا يفتح
    شيئًا. العناوين العربية لا تتأثر لأنها بلا حالة أحرف.

    مرّر قاموس `seen` لفضّ تعارض العناوين المتكررة — وهو شائع جدًّا في
    المستندات القانونية («الفصل الأول» تحت كل باب). بدونه تشترك العناوين
    المتطابقة في مرساة واحدة فتذهب كل روابطها إلى الأول.
    """
    anchor = re.sub(r"[^\w\s؀-ۿ-]", "", text).strip().replace(" ", "-").lower()
    if seen is None:
        return anchor
    seen[anchor] = seen.get(anchor, 0) + 1
    return anchor if seen[anchor] == 1 else f"{anchor}-{seen[anchor] - 1}"


# ═══════════════════════ التحويل ═══════════════════════

def convert(pdf_path, opt=None, progress=None, log=None, cancel=None):
    """
    يحوّل ملف PDF كاملًا إلى Markdown.

    يرجّع (markdown, stats).
    progress(pct:int, msg:str) و log(msg:str) اختياريتان.
    cancel كائن اختياري له is_set() (مثل threading.Event) — عند ضبطه
    يتوقف التحويل ويُرفع ConversionCancelled.
    """
    opt = opt or Options()
    say = log or (lambda m: None)
    tick = progress or (lambda p, m: None)

    doc = fitz.open(pdf_path)
    try:
        if doc.needs_pass:
            raise ValueError("الملف محمي بكلمة مرور — أزل الحماية أولًا.")
        n = len(doc)
        # نطاق خارج المدى خطأ صريح لا يُبتلع: لو سقط بصمت إلى «الملف كله»
        # لاستلم من طلب الصفحات ٥٠٠–٦٠٠ كتابًا كاملًا وهو يظنّه الجزء المطلوب.
        if opt.page_from and opt.page_from > n:
            raise ValueError(
                f"بداية النطاق ({opt.page_from}) تتجاوز عدد صفحات الملف ({n}).")
        lo = max(0, (opt.page_from or 1) - 1)
        hi = min(n - 1, (opt.page_to or n) - 1)
        if hi < lo:
            hi = n - 1
            say(f"⚠ نهاية النطاق ({opt.page_to}) أصغر من بدايته "
                f"({opt.page_from}) — حُوّل الملف من الصفحة {lo + 1} إلى نهايته.")
        total = hi - lo + 1
        st = {"lig": 0, "pairs": {}, "pages": total, "toc_skipped": 0,
              "headings": 0, "notes": 0, "chars": 0, "tables": 0,
              "watermark": 0}

        # ── ١) الاستخراج ──
        pages = []
        for k, i in enumerate(range(lo, hi + 1)):
            if cancel is not None and cancel.is_set():
                raise ConversionCancelled("أُلغي التحويل.")
            page = doc[i]
            lines = core.page_lines(page, st,
                                    unify_digits=opt.unify_digits,
                                    check_ink=opt.check_ink,
                                    fix_ligatures=opt.fix_ligatures,
                                    drop_watermark=opt.drop_watermark)
            pages.append((i, lines, page.rect.height))
            if k % 5 == 0 or k == total - 1:
                tick(int(70 * (k + 1) / total), f"استخراج ص {i + 1} / {hi + 1}")
        say(f"استُخرجت {total} صفحة — أُصلح {st['lig']:,} رباطًا مقلوبًا.")
        if st["watermark"]:
            say(f"حُذفت علامة مائية: {st['watermark']:,} جزء نصي مائل أو باهت.")

        # ── ٢) قياسات المستند ──
        body_size = body_font_size(pages)
        say(f"حجم خط المتن الغالب: {body_size}")

        boiler = set()
        if opt.drop_headers:
            boiler = repeated_headers(pages, total)
            say(f"أسطر ترويسة متكررة سيتم حذفها: {len(boiler)}")

        # ── ٣) البناء ──
        builder = Builder(opt)
        prev = None
        in_laiha = False
        pending_rows = []      # صفوف جدول متتالية بانتظار الإغلاق

        def close_table():
            """يفرغ الصفوف المتراكمة: صفّان فأكثر جدول، والصف الواحد فقرة."""
            if not pending_rows:
                return
            if len(pending_rows) >= 2:
                builder.table([r["cells"] for r in pending_rows])
                st["tables"] += 1
            else:
                builder.para(pending_rows[0]["text"], True)
            pending_rows.clear()

        for k, (i, lines, height) in enumerate(pages):
            if cancel is not None and cancel.is_set():
                raise ConversionCancelled("أُلغي التحويل.")
            if opt.drop_toc and is_toc_page(lines, body_size):
                st["toc_skipped"] += 1
                continue

            has_body = any(line["size"] >= body_size - 0.5 for line in lines)
            body, notes = [], []

            for line in lines:
                t, rel = line["text"], line["y0"] / height
                # الترويسة: المتكررة أو أي سطر صغير في منطقتها.
                # التذييل: المتكرر (بعد تجريد الأرقام) — الحاشية نص فريد فلا تُمس.
                if opt.drop_headers and (
                        (rel < HEADER_ZONE and (boiler_key(t) in boiler
                                                or line["size"] < body_size - 2))
                        or (rel > FOOTER_ZONE and boiler_key(t) in boiler)):
                    continue
                if rel > FOOTER_ZONE and RE_PAGENO.match(t):
                    continue
                # الحاشية: أصغر خط في النصف السفلي — تُؤجَّل لنهاية القسم
                if (has_body and line["size"] <= body_size - NOTE_SMALLER
                        and rel > NOTE_ZONE):
                    notes.append(t)
                    continue
                body.append(line)

            for idx, line in enumerate(body):
                t = line["text"]

                # صف جدول: يُراكَم حتى ينقطع التتابع، ثم يُبنى الجدول دفعةً
                if opt.tables and line.get("row") and len(line.get("cells", [])) >= 2:
                    pending_rows.append(line)
                    prev = line
                    continue
                close_table()

                kind = classify(line, opt, body_size)

                # فقرة جديدة إذا اتسعت الفجوة الرأسية عن ارتفاع السطر × para_gap
                gap_big = False
                if prev is not None and idx > 0:
                    lh = max(line["y1"] - line["y0"], 1.0)
                    gap_big = (line["y0"] - prev["y1"]) > lh * opt.para_gap

                if kind == "top":
                    builder.head(opt.h_top, t)
                    in_laiha = False
                elif kind == "laiha":
                    # عنوان «اللائحة التنفيذية» يقف وحده: نعلّم ما بعده فقط
                    builder.flush()
                    in_laiha = True
                elif kind == "sub":
                    title = re.sub(r"\s*:\s*$", "", t)
                    if in_laiha and RE_MADDA_N.match(t):
                        title = "اللائحة التنفيذية: " + title
                        in_laiha = False
                    builder.head(opt.h_sub, title)
                elif kind == "item":
                    # البند يُحفظ بترقيمه الأصلي كما هو، بلا إعادة ترقيم
                    builder.para(t, True)
                elif kind == "definition":
                    m = RE_DEF.match(t)
                    builder.para(f"**{m.group(1).strip()}:** {m.group(2).strip()}",
                                 True)
                else:
                    new_para = gap_big or (
                        prev is not None and idx > 0
                        and prev["text"].endswith(END_PUNCT)
                        and line["x1"] < prev["x1"] - INDENT_TOL
                    )
                    builder.para(t, new_para or not builder.buf)
                prev = line

            close_table()

            # سطر الحاشية الذي لا يبدأ برقم إشارة = تكملة للحاشية السابقة
            for note in notes:
                if RE_FOOT.match(note) or not builder.notes:
                    builder.notes.append(note)
                    st["notes"] += 1
                else:
                    builder.notes[-1] += " " + note

            tick(70 + int(25 * (k + 1) / len(pages)), f"بناء ص {i + 1}")

        close_table()
        builder.dump_notes()
        st["headings"] = len(builder.toc)

        # ── ٤) التجميع ──
        head = []
        if opt.title:
            head += [f"# {opt.title}", ""]
        if opt.build_toc and builder.toc:
            head += [f"{'#' * max(2, opt.h_top)} الفهرس", ""]
            base = min(lvl for lvl, _ in builder.toc)
            seen = {}       # يفضّ تعارض العناوين المتكررة عبر الفهرس كله
            for lvl, text in builder.toc:
                head.append("  " * (lvl - base)
                            + f"- [{text}](#{anchor_of(text, seen)})")
            head += ["", "---", ""]

        md = "\n".join(head + builder.out)
        md = re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"
        st["chars"] = len(md)
        tick(100, "تم")
        return md, st
    finally:
        doc.close()


# ═══════════════════════ التشخيص ═══════════════════════

# كلمات مؤشّرة: الشكل السليم مقابل الشكل التالف الناتج عن قلب الرباط
CANARY = [
    ("المادة", "املادة"),
    ("اللائحة", "الالئحة"),
    ("المملكة", "اململكة"),
    ("الأول", "األول"),
    ("وتاريخ", "واتريخ"),
    ("اللازم", "الالزم"),
    ("الإجازة", "اإلجازة"),
    ("المعلومات", "املعلومات"),
]


def diagnose(pdf_path, sample_every=7, progress=None, cancel=None):
    """
    فحص سريع لحالة الملف قبل التحويل — على عيّنة صفحات لا على الملف كله.

    فحص الحبر معطَّل هنا عمدًا: هو يكشف المسافات الوهمية، ولا علاقة له بقياس
    تلف الرباطات وهو كل ما يقيسه التشخيص. تشغيله كان يرسم كل صفحة من العيّنة
    بدقة ١٥٠ نقطة (١٢٩ عملية رسم على كتاب من ٩٠٠ صفحة) بلا فائدة.

    cancel كائن اختياري له is_set() — عند ضبطه يُرفع ConversionCancelled.

    يرجّع dict فيه:
      pages / sampled / has_text / needs_ocr — بيانات الملف
      ligatures / pairs                      — الرباطات المُصلَحة وأنواعها
      rows                                   — جدول قبل/بعد للكلمات المؤشّرة
      sample / raw_sample                    — عيّنة نص بعد وقبل الإصلاح
      fonts / producer / creator             — بيانات وصفية
    """
    doc = fitz.open(pdf_path)
    try:
        if doc.needs_pass:
            raise ValueError("الملف محمي بكلمة مرور — أزل الحماية أولًا.")
        idx = list(range(0, len(doc), max(1, sample_every)))
        tick = progress or (lambda p, m: None)

        raw = "".join(doc[i].get_text() for i in idx)
        st = {"lig": 0, "pairs": {}}
        parts = []
        for k, i in enumerate(idx):
            if cancel is not None and cancel.is_set():
                raise ConversionCancelled("أُلغي الفحص.")
            parts.append("\n".join(
                line["text"] for line in core.page_lines(doc[i], st,
                                                         check_ink=False)))
            tick(int(100 * (k + 1) / len(idx)), f"فحص ص {i + 1}")
        fixed = "\n".join(parts)

        rows = [{
            "word": good,
            "before_ok": raw.count(good), "before_bad": raw.count(bad),
            "after_ok": fixed.count(good), "after_bad": fixed.count(bad),
        } for good, bad in CANARY]

        has_text = bool(raw.strip())
        images = any(doc[i].get_images() for i in idx)
        fonts = doc[idx[len(idx) // 2]].get_fonts() if idx else []

        return {
            "pages": len(doc),
            "sampled": len(idx),
            "has_text": has_text,
            "needs_ocr": (not has_text) and images,
            "ligatures": st["lig"],
            "pairs": sorted(st["pairs"].items(), key=lambda x: -x[1])[:8],
            "rows": rows,
            "sample": parts[len(parts) // 3][:1500] if parts else "",
            "raw_sample": raw[:1500],
            "fonts": len(fonts),
            "producer": doc.metadata.get("producer", "") if doc.metadata else "",
            "creator": doc.metadata.get("creator", "") if doc.metadata else "",
        }
    finally:
        doc.close()
