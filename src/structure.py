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
    drop_toc: bool = True          # تخطّي صفحات الفهرس الأصلية
    footnotes: str = "quote"       # quote | inline | drop
    build_toc: bool = True         # توليد فهرس بروابط داخلية
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


# ═══════════════════════ التصنيف ═══════════════════════

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

    # auto — الحكم بحجم الخط مقارنًا بحجم المتن الغالب
    if size >= body_size + 3.5 and len(t) < 120:
        return "top"
    if (size >= body_size + 1.2 or (bold and size >= body_size + 0.5)) and len(t) < 120:
        return "sub"
    if RE_ITEM.match(t) or RE_BULLET.match(t):
        return "item"
    return "para"


def is_toc_page(lines, body_size):
    """صفحة فهرس أصلية: أغلب أسطرها أصغر من المتن وتنتهي برقم صفحة."""
    cand = [l for l in lines if l["size"] < body_size - 1]
    if len(cand) < 6:
        return False
    hits = sum(1 for l in cand if RE_TOCLINE.match(l["text"]))
    return hits >= max(6, 0.6 * len(cand))


def body_font_size(pages):
    """
    حجم خط المتن الغالب: الأكثر تكرارًا موزونًا بعدد الحروف لا بعدد الأسطر،
    حتى لا يطغى عشرون عنوانًا قصيرًا على مئة سطر متن.
    """
    weight = Counter()
    for _, lines, _ in pages:
        for l in lines:
            weight[round(l["size"] * 2) / 2] += len(l["text"])
    return weight.most_common(1)[0][0] if weight else 12.0


def repeated_headers(pages, total):
    """
    الترويسة والتذييل تُرصدان بتكرارهما عبر الصفحات لا بموضعهما وحده:
    السطر الواقع في منطقة الترويسة أو التذييل ويتكرر (بعد تجريد
    الأرقام) في ٥٪ من الصفحات على الأقل.
    """
    counter = Counter()
    for _, lines, height in pages:
        counter.update({
            re.sub(r"\d+", "#", l["text"]) for l in lines
            if (l["y0"] / height < HEADER_ZONE
                or l["y0"] / height > FOOTER_ZONE) and len(l["text"]) > 4
        })
    return {k for k, v in counter.items() if v >= max(3, 0.05 * total)}


def anchor_of(text):
    """مرساة عنوان صالحة للروابط الداخلية في Markdown."""
    return re.sub(r"[^\w\s؀-ۿ-]", "", text).strip().replace(" ", "-")


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
        lo = max(0, (opt.page_from or 1) - 1)
        hi = min(n - 1, (opt.page_to or n) - 1)
        if hi < lo:
            lo, hi = 0, n - 1
        total = hi - lo + 1
        st = {"lig": 0, "pairs": {}, "pages": total, "toc_skipped": 0,
              "headings": 0, "notes": 0, "chars": 0}

        # ── ١) الاستخراج ──
        pages = []
        for k, i in enumerate(range(lo, hi + 1)):
            if cancel is not None and cancel.is_set():
                raise ConversionCancelled("أُلغي التحويل.")
            page = doc[i]
            lines = core.page_lines(page, st,
                                    unify_digits=opt.unify_digits,
                                    check_ink=opt.check_ink,
                                    fix_ligatures=opt.fix_ligatures)
            pages.append((i, lines, page.rect.height))
            if k % 5 == 0 or k == total - 1:
                tick(int(70 * (k + 1) / total), f"استخراج ص {i + 1} / {hi + 1}")
        say(f"استُخرجت {total} صفحة — أُصلح {st['lig']:,} رباطًا مقلوبًا.")

        # ── ٢) قياسات المستند ──
        body_size = body_font_size(pages)
        say(f"حجم خط المتن الغالب: {body_size}")

        boiler = set()
        if opt.drop_headers:
            boiler = repeated_headers(pages, total)
            say(f"أسطر ترويسة متكررة سيتم حذفها: {len(boiler)}")

        # ── ٣) البناء ──
        B = Builder(opt)
        prev = None
        in_laiha = False

        for k, (i, lines, height) in enumerate(pages):
            if cancel is not None and cancel.is_set():
                raise ConversionCancelled("أُلغي التحويل.")
            if opt.drop_toc and is_toc_page(lines, body_size):
                st["toc_skipped"] += 1
                continue

            has_body = any(l["size"] >= body_size - 0.5 for l in lines)
            body, notes = [], []

            for l in lines:
                t, rel = l["text"], l["y0"] / height
                # الترويسة: المتكررة أو أي سطر صغير في منطقتها.
                # التذييل: المتكرر (بعد تجريد الأرقام) — الحاشية نص فريد فلا تُمس.
                if opt.drop_headers and (
                        (rel < HEADER_ZONE and (re.sub(r"\d+", "#", t) in boiler
                                                or l["size"] < body_size - 2))
                        or (rel > FOOTER_ZONE
                            and re.sub(r"\d+", "#", t) in boiler)):
                    continue
                if rel > FOOTER_ZONE and RE_PAGENO.match(t):
                    continue
                # الحاشية: أصغر خط في النصف السفلي — تُؤجَّل لنهاية القسم
                if has_body and l["size"] <= body_size - NOTE_SMALLER and rel > NOTE_ZONE:
                    notes.append(t)
                    continue
                body.append(l)

            for idx, l in enumerate(body):
                kind = classify(l, opt, body_size)
                t = l["text"]

                # فقرة جديدة إذا اتسعت الفجوة الرأسية عن ارتفاع السطر × para_gap
                gap_big = False
                if prev is not None and idx > 0:
                    lh = max(l["y1"] - l["y0"], 1.0)
                    gap_big = (l["y0"] - prev["y1"]) > lh * opt.para_gap

                if kind == "top":
                    B.head(opt.h_top, t)
                    in_laiha = False
                elif kind == "laiha":
                    # عنوان «اللائحة التنفيذية» يقف وحده: نعلّم ما بعده فقط
                    B.flush()
                    in_laiha = True
                elif kind == "sub":
                    title = re.sub(r"\s*:\s*$", "", t)
                    if in_laiha and RE_MADDA_N.match(t):
                        title = "اللائحة التنفيذية: " + title
                        in_laiha = False
                    B.head(opt.h_sub, title)
                elif kind == "item":
                    # البند يُحفظ بترقيمه الأصلي كما هو، بلا إعادة ترقيم
                    B.para(t, True)
                elif kind == "definition":
                    m = RE_DEF.match(t)
                    B.para(f"**{m.group(1).strip()}:** {m.group(2).strip()}", True)
                else:
                    new_para = gap_big or (
                        prev is not None and idx > 0
                        and prev["text"].endswith(END_PUNCT)
                        and l["x1"] < prev["x1"] - INDENT_TOL
                    )
                    B.para(t, new_para or not B.buf)
                prev = l

            # سطر الحاشية الذي لا يبدأ برقم إشارة = تكملة للحاشية السابقة
            for note in notes:
                if RE_FOOT.match(note) or not B.notes:
                    B.notes.append(note)
                    st["notes"] += 1
                else:
                    B.notes[-1] += " " + note

            tick(70 + int(25 * (k + 1) / len(pages)), f"بناء ص {i + 1}")

        B.dump_notes()
        st["headings"] = len(B.toc)

        # ── ٤) التجميع ──
        head = []
        if opt.title:
            head += [f"# {opt.title}", ""]
        if opt.build_toc and B.toc:
            head += [f"{'#' * max(2, opt.h_top)} الفهرس", ""]
            base = min(lvl for lvl, _ in B.toc)
            for lvl, text in B.toc:
                head.append("  " * (lvl - base) + f"- [{text}](#{anchor_of(text)})")
            head += ["", "---", ""]

        md = "\n".join(head + B.out)
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


def diagnose(pdf_path, sample_every=7, progress=None):
    """
    فحص سريع لحالة الملف قبل التحويل — على عيّنة صفحات لا على الملف كله.

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
            parts.append("\n".join(l["text"] for l in core.page_lines(doc[i], st)))
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
