# -*- coding: utf-8 -*-
"""
اختبارات فحص الحبر — القاعدة الأغلى في المشروع (تبطئ التحويل ٣×) وكانت
بلا حارس واحد، لأن كل اختبارات البنية تمرّر check_ink=False.

خريطة الحبر مصفوفة numpy ثنائية تُبنى هنا يدويًا بدل رسم صفحة حقيقية،
فالقاعدة المُختبَرة هي قراءة المصفوفة لا دقّة المُصيِّر.
"""

import numpy as np

from src import core
from src.core import Unit


def unit(text, x0, x1, y0=0.0, y1=10.0):
    return Unit(text, (x0, y0, x1, y1), 12.0, "Test", 0)


def blank_ink(w=200, h=20):
    return np.zeros((h, w), dtype=bool)


# ═══════════ الفجوة النظيفة ═══════════

def test_clean_gap_is_not_inked():
    """مسافة حقيقية: لا حبر بين الحرفين — فتبقى مسافة."""
    right, left = unit("ي", 100, 110), unit("ب", 80, 90)
    assert not core._inked(right, left, blank_ink(), 1.0, 0, 10)


def test_filled_gap_is_inked():
    """مسافة وهمية: الحرف المجاور مرسوم فوق موضعها — فتُحذف."""
    ink = blank_ink()
    ink[0:8, 88:102] = True                 # حبر يملأ الفجوة 90..100
    right, left = unit("ي", 100, 110), unit("ب", 80, 90)
    assert core._inked(right, left, ink, 1.0, 0, 10)


def test_faint_ink_below_threshold_keeps_space():
    """كثافة تحت INK_MAX = ٦٪ لا تكفي — القياس الفعلي: الحقيقية ≤ ٢٪."""
    ink = blank_ink()
    ink[0:1, 94:95] = True                  # نقطة واحدة داخل نطاق واسع
    right, left = unit("ي", 100, 110), unit("ب", 80, 90)
    assert not core._inked(right, left, ink, 1.0, 0, 10)


# ═══════════ حدود التطبيق ═══════════

def test_latin_gap_never_probed():
    """الفحص للعربي فقط — الفجوات اللاتينية ليس فيها هذا العيب."""
    ink = blank_ink()
    ink[0:10, 85:105] = True
    right, left = unit("a", 100, 110), unit("b", 80, 90)
    assert not core._inked(right, left, ink, 1.0, 0, 10)


def test_no_ink_map_disables_probe():
    right, left = unit("ي", 100, 110), unit("ب", 80, 90)
    assert not core._inked(right, left, None, 1.0, 0, 10)


def test_touching_glyphs_count_as_same_word():
    """فجوة أضيق من ٠٫٣ نقطة = لا فجوة أصلًا، بلا حاجة لقراءة البكسلات."""
    right, left = unit("ي", 90.1, 100), unit("ب", 80, 90)
    assert core._inked(right, left, blank_ink(), 1.0, 0, 10)


def test_operands_swapped_when_order_reversed():
    """الدالة تضمن أن right هو الأيمن فعلًا مهما كان ترتيب التمرير."""
    ink = blank_ink()
    ink[0:8, 88:102] = True
    right, left = unit("ي", 100, 110), unit("ب", 80, 90)
    assert core._inked(left, right, ink, 1.0, 0, 10) is core._inked(
        right, left, ink, 1.0, 0, 10)


# ═══════════ التكامل مع بناء السطر ═══════════

def test_phantom_space_removed_end_to_end():
    """
    «يقتض ي»: مسافة في المجرى يغطّيها حبر الحرف المجاور — تُحذف فتعود
    الكلمة «يقتضي». الإحداثيات تنازلية (RTL).
    """
    chars = [
        {"c": "ض", "bbox": (96.0, 0, 100.0, 10)},
        {"c": " ", "bbox": (92.0, 0, 96.0, 10)},
        {"c": "ي", "bbox": (88.0, 0, 92.0, 10)},
    ]
    page = type("P", (), {"get_text": lambda self, kind: {"blocks": [{
        "type": 0,
        "lines": [{"spans": [{"chars": chars, "size": 12.0,
                              "font": "Test", "flags": 0}]}],
    }]}})()

    ink = blank_ink()
    ink[0:8, 90:98] = True                  # حبر يغطّي موضع المسافة
    inked = core.build_lines(core.page_units(page), ink, 1.0)
    assert inked[0]["text"] == "ضي"

    clean = core.build_lines(core.page_units(page), blank_ink(), 1.0)
    assert clean[0]["text"] == "ض ي"
