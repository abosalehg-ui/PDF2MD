# -*- coding: utf-8 -*-
"""
اختبارات محرّك الاستخراج core.py.

تلف الرباطات يُحاكى بـ rawdict مصطنع (صفحة وهمية) بدل ملف PDF حقيقي،
لأن إنتاج ملف يحمل خلل ToUnicode نفسه يتطلب حقن content stream يدويًا.
القواعد المُختبرة هي نفسها التي تعمل على الملفات الحقيقية.
"""

import re

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
    return "\n".join(line["text"] for line in lines)


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


def test_three_char_ligature_restored():
    # «الله» جليف واحد يبتلع (ه ل ل) بعرض صفر ثم الألف بالصندوق كاملًا.
    # المبادلة الثنائية وحدها كانت تنتج «لهال».
    chars = [
        ch("ه", 96, x1=96.0),
        ch("ل", 96, x1=96.0),
        ch("ل", 96, x1=96.0),
        ch("ا", 82, x1=96),
    ]
    stats = {}
    assert text_of(page_of(chars), stats=stats) == "الله"
    assert stats["lig"] == 1
    assert stats["pairs"] == {"الله": 1}


def test_zero_width_run_at_span_end_kept_as_is():
    # تتابع بعرض صفر بلا حرف حامل بعده: يُترك كما هو بلا مبادلة ولا فقد
    chars = [ch("ا", 92, x1=96), ch("ه", 92, x1=92.0), ch("ل", 92, x1=92.0)]
    out = text_of(page_of(chars))
    assert set(out) == set("اهل")


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


# ═══════════ ٦. كشيدة الضبط ═══════════
# محاذي Pages/Quartz يحشو تطويلات هزيلة بين الحروف المتصلة لضبط السطر.
# كانت التطويلة تُعامل تشكيلًا فتُلصَق بأقرب حرف — وتخرج أحيانًا في آخر
# الكلمة («رقمـ») بعيدًا عن موضعها.

def lines_of(page, stats=None, **kw):
    return core.build_lines(core.page_units(page, stats, **kw), stats=stats)


def test_kashida_between_letters_dropped():
    chars = [
        ch("ا", 96, x1=100),
        ch("ت", 92, x1=96),
        ch("ـ", 91.5, x1=92),       # كشيدة هزيلة بين التاء والقاف
        ch("ق", 86, x1=91.5),
        ch("د", 82, x1=86),
        ch("م", 78, x1=82),
    ]
    stats = {}
    assert lines_of(page_of(chars), stats)[0]["text"] == "اتقدم"
    assert stats["kashida"] == 1


def test_kashida_run_dropped_together():
    chars = [
        ch("ر", 96, x1=100),
        ch("ـ", 93, x1=96),
        ch("ـ", 90, x1=93),
        ch("ق", 86, x1=90),
    ]
    assert lines_of(page_of(chars))[0]["text"] == "رق"


def test_kashida_before_space_kept():
    # «١٤٤٨هـ ضد»: التطويلة جزء من اختصار الهجري، ويليها فراغ لا حرف
    chars = [
        ch("ه", 96, x1=100),
        ch("ـ", 93, x1=96),
        ch(" ", 89, x1=93),
        ch("ض", 85, x1=89),
        ch("د", 81, x1=85),
    ]
    stats = {}
    assert lines_of(page_of(chars), stats)[0]["text"] == "هـ ضد"
    assert "kashida" not in stats


def test_kashida_at_line_edges_kept():
    chars = [ch("ـ", 96, x1=100), ch("ب", 92, x1=96), ch("ـ", 88, x1=92)]
    assert lines_of(page_of(chars))[0]["text"] == "ـبـ"


def test_kashida_never_hosts_a_diacritic():
    # التنوين فوق الألف يبقى على الألف وإن كانت الكشيدة أقرب مركزًا،
    # وتُحذف الكشيدة رغم أن الحرف التالي يحمل تشكيلًا.
    chars = [
        ch("ر", 96, x1=100),
        ch("ـ", 95.5, x1=96),
        ch("ا", 92, x1=95.5),
        ch("ً", 95.4, x1=95.6),     # يلامس الكشيدة والألف معًا
    ]
    assert lines_of(page_of(chars))[0]["text"] == "راً"


def test_zero_width_kashida_is_not_a_ligature_half():
    chars = [ch("ب", 96, x1=100), ch("ـ", 96, x1=96.01), ch("ت", 92, x1=96)]
    stats = {}
    assert lines_of(page_of(chars), stats)[0]["text"] == "بت"
    assert "lig" not in stats


# ═══════════ ٧. الأقواس المخزَّنة بشكلها البصري ═══════════
# Quartz يكتب في المجرى جليف القوس المرسوم لا حرفه المنطقي، فبعد الترتيب
# البصري يخرج «)مرفق1(». Word يكتب الحرف المنطقي فيخرج سليمًا. القرار
# للصفحة كلها من سياق الأقواس (فراغ قبل الفاتح، ترقيم أو فراغ بعد الغالق).

def rtl_line(text, y0=0.0, y1=10.0, x_right=400.0):
    """
    أحرف نص عربي بترتيب القراءة تُرصف من اليمين إلى اليسار، ٤ نقاط لكل
    حرف. تسلسل الأرقام يُرصف داخله من اليسار إلى اليمين كما يُرسم فعلًا.
    """
    out, x = [], x_right
    for run in re.findall(r"\d+|\D", text):
        for c in reversed(run):
            out.append(ch(c, x - 4, y0=y0, x1=x, y1=y1))
            x -= 4
    return out


def test_visual_brackets_mirrored():
    chars = rtl_line("شهراً )مرفق1(، وكانت")
    stats = {}
    assert lines_of(page_of(chars), stats)[0]["text"] == "شهراً (مرفق1)، وكانت"
    assert stats["mirror"] == 2


def test_logical_brackets_untouched():
    chars = rtl_line("المادة (12): نص")
    stats = {}
    assert lines_of(page_of(chars), stats)[0]["text"] == "المادة (12): نص"
    assert "mirror" not in stats


def test_space_after_mirrored_closer_survives_tidy():
    # قبل الإصلاح كان tidy يحذف الفراغ بعد «(» فيخرج «(مرفق3(أي» ملتحمًا
    chars = rtl_line("- )مرفق3( أي قبل")
    assert lines_of(page_of(chars))[0]["text"] == "- (مرفق3) أي قبل"


def test_bracket_decision_is_page_wide():
    # قوس يُفتح في سطر ويُغلق في التالي: كل سطر وحده يحمل قوسًا واحدًا،
    # والصفحة كلها تحسم أن المخزون بصري.
    page = FakePage([{
        "type": 0,
        "lines": [
            {"spans": [{"chars": rtl_line("نص على أنه )يتجدد", 0, 10),
                        "size": 12.0, "font": "Test", "flags": 0}]},
            {"spans": [{"chars": rtl_line("انتهاء العقد(، مما", 20, 30),
                        "size": 12.0, "font": "Test", "flags": 0}]},
        ],
    }])
    texts = [line["text"] for line in lines_of(page)]
    assert texts == ["نص على أنه (يتجدد", "انتهاء العقد)، مما"]


def test_bracket_votes():
    assert core.bracket_votes("شهراً )مرفق1(، و") == (2, 0)
    assert core.bracket_votes("المادة (12):") == (0, 2)
    assert core.bracket_votes("أ ( ) ب") == (0, 0)          # ملتبس: لا صوت
    assert core.bracket_votes("بلا أقواس") == (0, 0)


def test_latin_lines_never_mirrored():
    chars = [ch(c, 10 + 4 * k, x1=14 + 4 * k) for k, c in enumerate("f(x) = 1")]
    assert lines_of(page_of(chars))[0]["text"] == "f(x) = 1"
