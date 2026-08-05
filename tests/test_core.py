# -*- coding: utf-8 -*-
"""
اختبارات محرّك الاستخراج core.py.

تلف الرباطات يُحاكى بـ rawdict مصطنع (صفحة وهمية) بدل ملف PDF حقيقي،
لأن إنتاج ملف يحمل خلل ToUnicode نفسه يتطلب حقن content stream يدويًا.
القواعد المُختبرة هي نفسها التي تعمل على الملفات الحقيقية.
"""

from src import core


# ═══════════ أدوات بناء rawdict مصطنع ═══════════

class FakePage:
    """صفحة وهمية تكفي page_units — لا تحتاج إلا get_text("rawdict")."""

    def __init__(self, blocks):
        self._blocks = blocks

    def get_text(self, kind):
        assert kind == "rawdict"
        return {"blocks": self._blocks}


def ch(c, x0, y0=0.0, x1=None, y1=10.0):
    return {"c": c, "bbox": (x0, y0, x1 if x1 is not None else x0 + 4.0, y1)}


def page_of(chars, size=12.0, font="Test"):
    return FakePage([{
        "type": 0,
        "lines": [{"spans": [{"chars": chars, "size": size,
                              "font": font, "flags": 0}]}],
    }])


def text_of(page, **kw):
    lines = core.build_lines(core.page_units(page, **kw))
    return "\n".join(l["text"] for l in lines)


# ═══════════ ١. الرباط المقلوب ═══════════

def test_reversed_ligature_swapped():
    # «المادة» المعطوبة: الميم بعرض صفر تسبق اللام في المجرى — القاعدة
    # تبدّلها فيخرج «لم» في موضعه الصحيح. الإحداثيات تنازلية (RTL).
    # صندوق اللام (حامل الجليف) يلاصق الألف قبله كما في الملفات الحقيقية،
    # والميم بعرض صفر عند موضع القلم.
    chars = [
        ch("ا", 96, x1=100),
        ch("م", 96, x1=96.02),      # عرض ~صفر: نصف الرباط
        ch("ل", 92, x1=96),
        ch("ا", 88, x1=92),
        ch("د", 84, x1=88),
        ch("ة", 80, x1=84),
    ]
    stats = {}
    assert text_of(page_of(chars), stats=stats) == "المادة"
    assert stats["lig"] == 1
    assert stats["pairs"] == {"لم": 1}


def test_ligature_fix_can_be_disabled():
    chars = [ch("م", 96, x1=96.02), ch("ل", 92, x1=96)]
    assert text_of(page_of(chars), fix_ligatures=False) == "مل"
    assert text_of(page_of(chars), fix_ligatures=True) == "لم"


def test_zero_width_before_diacritic_not_swapped():
    # نصف رباط يليه تشكيل: لا تبديل مع التشكيل نفسه
    chars = [ch("م", 96, x1=96.02), ch("ً", 95, x1=95.5), ch("ل", 92, x1=96)]
    out = text_of(page_of(chars))
    assert "م" in out and "ل" in out


# ═══════════ ٢. المسافات من الفجوات ═══════════

def test_gap_inserts_space():
    # فجوة 4 نقاط بحجم خط 12 → 0.33 > GAP_RATIO=0.13 → مسافة
    chars = [ch("ب", 100, x1=104), ch("ا", 92, x1=96)]
    assert text_of(page_of(chars)) == "ب ا"


def test_tiny_gap_no_space():
    chars = [ch("ب", 96, x1=100), ch("ا", 92, x1=96)]
    assert text_of(page_of(chars)) == "با"


# ═══════════ ٣. عكس تسلسلات الأرقام ═══════════

def test_date_run_restored():
    # «1436/6/5» مطبوعة LTR داخل سطر عربي: بعد الترتيب البصري RTL تُقرأ
    # معكوسة، وإعادة العكس تسترجع الترتيب المنطقي كاملًا بفواصله.
    logical = "1436/6/5"
    chars = [ch("و", 140, x1=144)]
    for k, c in enumerate(logical):         # مطبوعة يسارًا→يمينًا
        chars.append(ch(c, 100 + k * 4, x1=104 + k * 4))
    out = text_of(page_of(chars))
    assert logical in out


def test_space_inside_number_run_dropped():
    # مسافة محصورة بين رقمين تُسقط حتى لا ينكسر التاريخ
    chars = [
        ch("و", 112, x1=116),
        ch("1", 104, x1=108),
        ch(" ", 100, x1=104),
        ch("2", 96, x1=100),
    ]
    out = text_of(page_of(chars))
    assert "1 2" not in out and "21" in out


# ═══════════ ٤. التشكيل الطائر ═══════════

def test_diacritic_attached_to_containing_letter():
    # الفتحتان فوق الميم إحداثيًا وإن سبقتا في المجرى حرفًا آخر
    chars = [
        ch("ً", 84.5, x1=85.5),     # فوق الميم (84-88)
        ch("ب", 88, x1=92),
        ch("م", 84, x1=88),
    ]
    out = text_of(page_of(chars))
    assert "مً" in out


# ═══════════ ٥. التنظيف النهائي ═══════════

def test_tidy_rules():
    assert core.tidy("كلمة ، أخرى") == "كلمة، أخرى"
    assert core.tidy("( نص )") == "(نص)"
    assert core.tidy("5 / 6") == "5/6"
    assert core.tidy("سنة 1442 هـ.") == "سنة 1442هـ."
    assert core.tidy("نص‏مخفي‎") == "نصمخفي"


def test_tidy_collapses_whitespace():
    assert core.tidy("أ  ب\tج") == "أ ب ج"
