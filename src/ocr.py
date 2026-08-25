# -*- coding: utf-8 -*-
"""
ocr.py — رصد طبقة النص المعطوبة والسقوط إلى OCR.

المشكلة التي يعالجها هذا الملف
──────────────────────────────
بقية المحرّك تفترض أن طبقة النص داخل الـPDF صحيحة وأن الخلل فيها *هندسي*
(رباط مقلوب، مسافة وهمية، تشكيل طائر) — وهذه كلها تُصلَح بالإحداثيات.
لكن هناك صنفًا من الملفات لا يُصلَح هندسيًا أبدًا:

  • **خريطة ToUnicode مكسورة كليًا**: الجليف العربي يُصدَّر حرفًا لاتينيًا
    عشوائيًا، فتخرج «المحامي والموثق» بهيئة «.Sg0rlg gpl-r o ll». لا
    إحداثيات تنقذ هذا — المعلومة الأصلية غير موجودة في المجرى.
  • **صفحة ممسوحة ضوئيًا**: صورة تغطي الصفحة وفوقها ختم أو توقيع فقط،
    فالنص المستخرج صفر بينما الصفحة مليئة بالكلام.
  • **خريطة ToUnicode مكسورة جزئيًا**: الحروف عربية لكن بعضها مُبدَّل
    (لام وسطية تخرج ياءً)، ويُرصد بأثر جانبي يتركه هذا الصنف من المولِّدات:
    ياء مرسومة كـ«مسافة بعرض حقيقي + تنوين ضم بعرض صفر».

في هذه الأحوال الحلّ الوحيد هو تجاهل طبقة النص وقراءة الصفحة من بكسلاتها
عبر Tesseract. نشغّل Tesseract مباشرةً بمخرَج TSV — كلمة في كل سطر ومعها صندوقها وثقتها
— لا عبر غلاف PyMuPDF. السبب أن الغلاف يبني الحروف بتقسيم صندوق الكلمة
بالتساوي ثم يعيد ترتيبها، فيقلب بعض الأسطر العربية رأسًا على عقب
(«نهاية العقد» تخرج «دقعلا ةياهن»). مخرَج TSV يعطي الكلمة سليمة بصندوقها
الحقيقي، فنبني منه الأسطر مباشرةً ونتجاوز إعادةَ التركيب من الحروف —
وهي أصلًا إصلاح لعلل مجرى النص، ولا مجرى نص هنا.

السياسة الافتراضية `auto`: لا يُشغَّل OCR إلا على الصفحة التي يثبت عطب
طبقتها. الصفحة السليمة تبقى على نصها الأصلي — فهو أدقّ من أي OCR.
"""

import os
import re
import shutil
import subprocess

from . import core

try:
    import pymupdf as fitz
except ImportError:                     # PyMuPDF < 1.24.3
    import fitz

# ═══════════════ ثوابت المعايرة ═══════════════

OCR_DPI = 300           # أقل من ٣٠٠ يُتلف تمييز النقاط العربية (ب/ت/ث)
OCR_LANG = "ara+eng"    # المستندات المرصودة تخلط العربية بالإنجليزية
PSM = 6                 # «كتلة نص موحّدة» — أنسب أنماط التقطيع لصفحة مذكرة
MIN_CONF = 30           # ثقة الكلمة تحتها تُهمَل: ضوضاء مسح لا حرفًا
OCR_TIMEOUT = 120       # ثوانٍ لكل صفحة — حارس ضد تعليق العملية كلها
# انزياح مركز الكلمة الرأسي (× ارتفاعها الوسيط) الذي يجعلها في صفٍّ آخر
ROW_TOL = 0.60

# أقلّ عدد حروف «ذات معنى» تُعدّ الصفحة تحته فارغة من النص
MIN_CHARS = 40
# نسبة مساحة الصفحة التي تغطيها صورة لتُعدّ الصفحة ممسوحة ضوئيًا
IMG_COVER = 0.50
# الصفحة الخالية من المتن تمامًا يكفيها هذا القدر من الصورة — لا نص يُخسر
# بمحاولة قراءتها، والمرفق الممسوح قد يُدرَج مقصوصًا فلا يبلغ نصف الصفحة.
IMG_COVER_EMPTY = 0.10
# أقل عدد كلمات لاتينية يُعتمد عليه في حكم «الحروف عشوائية»
MIN_LATIN_TOKENS = 15
# نسبة الكلمات اللاتينية المعقولة (فيها حرف علة) تحتها تُعدّ الطبقة عشوائية
LATIN_PLAUSIBLE = 0.70
# فوق هذه النسبة من الحروف عربية = الطبقة عربية فعلًا، فلا يُطبَّق فحص اللاتيني
ARABIC_SHARE = 0.15
# عدد شواهد «ياء مكسورة» التي تكفي للحكم بعطب خريطة الخط
BROKEN_YEH_HITS = 3

_AR = re.compile(r"[؀-ۿ]")
_LATIN_TOKEN = re.compile(r"[A-Za-z]{2,}")
_VOWEL = re.compile(r"[aeiouyAEIOUY]")


# ═══════════════ توفّر Tesseract ═══════════════

def tessdata_dir():
    """
    مجلد بيانات Tesseract أو None. PyMuPDF يقرأ TESSDATA_PREFIX، ونجرّب
    المسارات المعتادة حين لا يكون المتغيّر مضبوطًا (تثبيت apt أو brew).
    """
    env = os.environ.get("TESSDATA_PREFIX")
    if env and os.path.isdir(env):
        return env
    for path in ("/usr/share/tesseract-ocr/5/tessdata",
                 "/usr/share/tesseract-ocr/4.00/tessdata",
                 "/usr/share/tessdata",
                 "/opt/homebrew/share/tessdata",
                 "/usr/local/share/tessdata"):
        if os.path.isdir(path):
            return path
    return None


def available():
    """هل يمكن تشغيل OCR فعلًا؟ يحتاج ثنائي tesseract ومجلد بياناته معًا."""
    return bool(shutil.which("tesseract") and tessdata_dir())


def why_unavailable():
    """رسالة عربية تشرح الناقص — تُعرض للمستخدم مرة واحدة لا لكل صفحة."""
    if not shutil.which("tesseract"):
        return ("Tesseract غير مثبَّت — بدونه لا يمكن قراءة الصفحات "
                "الممسوحة ضوئيًا ولا الملفات ذات خريطة الخط المكسورة.\n"
                "  Ubuntu/Debian: sudo apt install tesseract-ocr tesseract-ocr-ara\n"
                "  macOS:         brew install tesseract tesseract-lang\n"
                "  Windows:       https://github.com/UB-Mannheim/tesseract/wiki")
    return ("مجلد بيانات Tesseract غير موجود — اضبط المتغيّر TESSDATA_PREFIX "
            "على مجلد ملفات .traineddata (ويلزم فيه ara.traineddata).")


# ═══════════════ رصد الطبقة المعطوبة ═══════════════

def _image_cover(page):
    """نسبة مساحة الصفحة التي تغطيها الصور المرسومة عليها."""
    area = abs(page.rect.width * page.rect.height)
    if area <= 0:
        return 0.0
    covered = 0.0
    for block in page.get_text("dict")["blocks"]:
        if block["type"] == 1:          # صورة
            x0, y0, x1, y1 = block["bbox"]
            covered += abs((x1 - x0) * (y1 - y0))
    return min(covered / area, 1.0)


def looks_scrambled(text):
    """
    هل النص حروف لاتينية عشوائية؟

    الخط العربي بخريطة ToUnicode مكسورة يُخرج سلاسل مثل «tJJ nr-ll;r.l»:
    لاتينية الشكل، لكن أغلب «كلماتها» بلا حرف علة — وهو ما لا يحدث في
    نص إنجليزي حقيقي. لا نحكم إلا على عيّنة كافية حتى لا يُتهم سطر مثل
    «PDF XML» بأنه عشوائي.
    """
    arabic = len(_AR.findall(text))
    latin = sum(ch.isascii() and ch.isalpha() for ch in text)
    if arabic + latin == 0:
        return False
    if arabic / (arabic + latin) >= ARABIC_SHARE:
        return False                    # فيه عربي معتبر: الطبقة مقروءة
    tokens = _LATIN_TOKEN.findall(text)
    if len(tokens) < MIN_LATIN_TOKENS:
        return False                    # عيّنة أصغر من أن يُحكم عليها
    plausible = sum(1 for w in tokens if _VOWEL.search(w))
    return plausible / len(tokens) < LATIN_PLAUSIBLE


def broken_yeh_hits(page):
    """
    عدد شواهد «الياء المكسورة»: مسافة بعرض حقيقي يليها تنوين ضم بعرض صفر.

    مولِّدات معيّنة ترسم الياء بجليفين — قاعدة مهملة النقط تُصدَّر مسافةً،
    والنقطتان تُصدَّران U+064C بعرض صفر — فتخرج «تفيد» بهيئة «تف ٌد».
    وجود هذا النمط دليل قاطع على أن خريطة الخط مبدَّلة، ومعه تُبدَّل حروف
    أخرى لا أثر هندسي لها (اللام الوسطية تخرج ياءً)، فالطبقة كلها مشبوهة.
    """
    hits = 0
    for block in page.get_text("rawdict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block.get("lines", []):
            for span in line["spans"]:
                chars = span.get("chars") or []
                for i in range(1, len(chars)):
                    if chars[i]["c"] != "ٌ":
                        continue
                    box = chars[i]["bbox"]
                    prev = chars[i - 1]
                    if box[2] - box[0] > 0.05 * span["size"]:
                        continue        # تنوين حقيقي له عرض
                    if not prev["c"].isspace():
                        continue
                    pbox = prev["bbox"]
                    if pbox[2] - pbox[0] > 0.05 * span["size"]:
                        hits += 1
    return hits


def _body_chars(page):
    """
    عدد حروف المتن في الصفحة — بعد استبعاد العلامة المائية.

    لا يصلح العدّ على `get_text()` الخام: صفحة المرفق الممسوحة ضوئيًا تحمل
    ختمًا أو توقيعًا مكرَّرًا بمئتَي حرف، فتبدو «مليئة بالنص» بينما المتن
    المقروء فيها صفر — وهو نفسه ما يحذفه المسار لاحقًا فتخرج الصفحة خاوية.
    """
    blocks = [b for b in page.get_text("rawdict")["blocks"] if b["type"] == 0]
    blocks, _ = core.drop_watermarks(blocks)
    return sum(
        not ch.isspace()
        for blk in blocks
        for line in blk["lines"]
        for span in line["spans"]
        for ch in span.get("text", "")
    )


def page_verdict(page):
    """
    يرجّع (يحتاج OCR؟، سبب مختصر بالعربية).

    السبب يُعرض في سجلّ التحويل ليعرف المستخدم لماذا بطُؤت صفحة بعينها.
    """
    text = page.get_text().strip()

    body = _body_chars(page)
    if body < MIN_CHARS:
        cover = _image_cover(page)
        if cover >= IMG_COVER or (body == 0 and cover >= IMG_COVER_EMPTY):
            return True, "صفحة ممسوحة ضوئيًا بلا طبقة نص"
    if looks_scrambled(text):
        return True, "خريطة الخط مكسورة — الحروف تخرج لاتينية عشوائية"
    if broken_yeh_hits(page) >= BROKEN_YEH_HITS:
        return True, "خريطة الخط مبدَّلة — ياء مرسومة بمسافة وتنوين"
    return False, ""


# ═══════════════ التشغيل ═══════════════

def _tsv(png, language, timeout):
    """يشغّل Tesseract على صورة PNG ويرجّع أسطر TSV، أو None عند الفشل."""
    try:
        proc = subprocess.run(
            ["tesseract", "stdin", "stdout", "-l", language,
             "--psm", str(PSM), "tsv"],
            input=png, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=timeout, check=True,
            env=dict(os.environ, TESSDATA_PREFIX=tessdata_dir() or ""),
        )
    except (OSError, subprocess.SubprocessError):
        # لغة ناقصة، صورة تالفة، أو تجاوز المهلة على صفحة كثيفة. الفشل
        # على صفحة لا يُسقط تحويل المستند — يرجع المستدعي لطبقتها الأصلية.
        return None
    return proc.stdout.decode("utf-8", "replace").splitlines()


def _words(tsv_lines):
    """
    يقرأ TSV ويرجّع {مفتاح السطر: [(x, y, w, h, نص)]}.

    مخرَج Tesseract يحمل صفوفًا وسيطة للكتلة والفقرة والسطر نصّها فارغ،
    فلا يُؤخذ منه إلا الصف الذي فيه كلمة فعلية وثقتها فوق العتبة.
    """
    if not tsv_lines:
        return {}
    head = tsv_lines[0].split("\t")
    try:
        col = {name: head.index(name) for name in
               ("block_num", "par_num", "line_num", "left", "top",
                "width", "height", "conf", "text")}
    except ValueError:
        return {}

    out = {}
    for row in tsv_lines[1:]:
        cell = row.split("\t")
        if len(cell) <= col["text"]:
            continue
        text = cell[col["text"]].strip()
        if not text:
            continue
        try:
            conf = float(cell[col["conf"]])
            box = [int(cell[col[k]]) for k in ("left", "top", "width", "height")]
            key = tuple(int(cell[col[k]])
                        for k in ("block_num", "par_num", "line_num"))
        except ValueError:
            continue
        if conf < MIN_CONF:
            continue
        out.setdefault(key, []).append((box[0], box[1], box[2], box[3], text))
    return out


def _line_of(words, scale):
    """يبني سطرًا واحدًا بالبنية التي يرجّعها core.page_lines، أو None لو خلا."""
    rtl = bool(_AR.search("".join(w[4] for w in words)))
    # الفرز بمركز الكلمة لا بحافّتها: المميِّز يبالغ أحيانًا في عرض صندوق
    # كلمة فيبتلع جارتها، فتتقدّم عليها عند الفرز بالحافة ويختلّ الترتيب
    # («مذكرة تفيد بأحقية» → «مذكرة بأحقية تفيد»). المركز أثبت للانزياح.
    words = sorted(words, key=(lambda w: -(w[0] + w[2] / 2)) if rtl
                   else (lambda w: w[0] + w[2] / 2))
    text = core.tidy(" ".join(w[4] for w in words))
    if not text:
        return None
    heights = sorted(w[3] for w in words)
    return {
        "text": text,
        "x0": min(w[0] for w in words) / scale,
        "x1": max(w[0] + w[2] for w in words) / scale,
        "y0": min(w[1] for w in words) / scale,
        "y1": max(w[1] + w[3] for w in words) / scale,
        # الارتفاع الوسيط لا المتوسط: نقطة أو شَرطة في السطر ارتفاعها
        # بضعة بكسلات فتجرّ المتوسط إلى أسفل وتُخفي العنوان.
        "size": round(heights[len(heights) // 2] / scale, 1),
        "bold": False,
        "row": False,
        "cells": [],
    }


def _split_rows(words):
    """
    يقسّم كلمات «سطر» Tesseract إلى صفوف بصرية حسب مركزها الرأسي.

    نمط التقطيع psm 6 يضمّ أحيانًا صفَّين متجاورين في سطر واحد — عنوان
    من سطرين مثلًا — فيختلط ترتيبهما عند الفرز الأفقي وتخرج «مذكرة تفيد
    بأحقية» بهيئة «مذكرة بأحقية تفيد». الفصل بالمركز الرأسي يعيدهما صفَّين.
    """
    if len(words) < 2:
        return [words]
    heights = sorted(w[3] for w in words)
    tol = ROW_TOL * heights[len(heights) // 2]
    rows = []
    for w in sorted(words, key=lambda w: w[1] + w[3] / 2):
        center = w[1] + w[3] / 2
        if rows and abs(center - rows[-1][0]) <= tol:
            rows[-1][1].append(w)
        else:
            rows.append([center, [w]])
    return [r[1] for r in rows]


def page_lines(page, dpi=OCR_DPI, language=OCR_LANG, timeout=OCR_TIMEOUT):
    """
    يقرأ الصفحة بالـOCR ويرجّع أسطرها بالبنية التي يرجّعها `core.page_lines`
    — أو None عند تعذّر التشغيل.

    ترتيب الكلمات داخل السطر بصريّ: تنازليًا حسب الحافة اليمنى في السطر
    العربي، وتصاعديًا حسب اليسرى في اللاتيني. المميِّز يعطي كل كلمة سليمة
    وصندوقها الحقيقي، فالترتيب بالإحداثيات وحده يكفي ولا حاجة لتخمين.

    `size` مشتقّ من ارتفاع الكلمة الوسيط بعد ردّه إلى نقاط الصفحة، لأن
    بقية المسار تقارن حجم السطر بحجم المتن الغالب لتمييز العناوين.
    """
    if not tessdata_dir():
        return None
    scale = dpi / 72.0
    png = page.get_pixmap(matrix=fitz.Matrix(scale, scale)).tobytes("png")
    grouped = _words(_tsv(png, language, timeout))
    if not grouped:
        return None

    lines = []
    for group in grouped.values():
        for words in _split_rows(group):
            lines.append(_line_of(words, scale))
    lines = [ln for ln in lines if ln]
    lines.sort(key=lambda ln: (ln["y0"], -ln["x1"]))
    return lines
