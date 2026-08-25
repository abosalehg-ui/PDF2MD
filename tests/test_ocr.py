# -*- coding: utf-8 -*-
"""
اختبارات ocr.py — رصد طبقة النص المعطوبة، وإصلاح الياء المكسورة في core.

لا تُشغَّل Tesseract هنا: توفّره ليس مضمونًا في CI، والمنطق الذي يُختبر
(الرصد والقراءة والفرز) منفصل عن التشغيل أصلًا.
"""

import pytest

from src import core, ocr

# ═══════════════ رصد الحروف العشوائية ═══════════════

def test_scrambled_latin_is_detected():
    """
    خريطة ToUnicode المكسورة تُخرج لاتينية بلا حروف علة. هذا هو النص الفعلي
    الذي أخرجه ملف مذكرة عربية موقّعة، وهو الحالة التي فُتح لها هذا المسار.
    """
    junk = (",,Li4O .Sg0rlg gpl-r o ll tJJ nr-ll;r.l eg'r or' J'I{ "
            "d+igi[!,:r[t,i,t.,,1- ${JC oLoLu PqEqo4Ja{t, ailt aU; "
            "4*Jl.Jl a^S^^Jt a+],Jl +Jt^Jl ori[Jl ,yi: a&.,2,s a6y: oilt")
    assert ocr.looks_scrambled(junk)


def test_real_english_is_not_scrambled():
    """الإنجليزية السليمة لاتينية أيضًا — الرصد يجب ألّا يلتهمها."""
    prose = ("Permission is hereby granted free of charge to any person "
             "obtaining a copy of this software and associated documentation "
             "files to deal in the Software without restriction including "
             "without limitation the rights to use copy modify merge publish")
    assert not ocr.looks_scrambled(prose)


def test_arabic_text_is_never_scrambled():
    """وجود عربي معتبر يعني أن الطبقة مقروءة مهما خالطها من لاتيني."""
    mixed = "قرار المحكمة العمالية رقم 12303146 على منصة قوى Qiwa platform"
    assert not ocr.looks_scrambled(mixed)


def test_short_latin_sample_is_not_judged():
    """سطر من كلمتين لا يكفي للحكم — الرفض هنا أسلم من OCR بلا داعٍ."""
    assert not ocr.looks_scrambled("PDF XML UTF")


# ═══════════════ فرز الكلمات وبناء الأسطر ═══════════════

def _word(x, y, w, h, text):
    return (x, y, w, h, text)


def test_arabic_line_is_ordered_right_to_left():
    words = [_word(100, 10, 40, 20, "العقد"),
             _word(200, 10, 40, 20, "بنود"),
             _word(300, 10, 40, 20, "مذكرة")]
    line = ocr._line_of(words, scale=1.0)
    assert line["text"] == "مذكرة بنود العقد"


def test_latin_line_is_ordered_left_to_right():
    words = [_word(300, 10, 40, 20, "closed"),
             _word(100, 10, 40, 20, "Case"),
             _word(200, 10, 40, 20, "was")]
    assert ocr._line_of(words, scale=1.0)["text"] == "Case was closed"


def test_overwide_box_does_not_jump_the_queue():
    """
    المميِّز يبالغ أحيانًا في عرض صندوق كلمة فيبتلع جارتها. الفرز بالحافة
    اليمنى كان يقدّمها على من قبلها؛ الفرز بالمركز يبقيها في موضعها.
    """
    words = [_word(1424, 531, 122, 72, "مذكرة"),
             _word(1320, 531, 82, 72, "تفيد"),
             _word(1163, 535, 380, 63, "بأحقية")]     # صندوق متضخّم
    assert ocr._line_of(words, scale=1.0)["text"] == "مذكرة تفيد بأحقية"


def test_two_stacked_rows_are_split():
    """psm 6 يضمّ أحيانًا صفَّين في سطر واحد — الفصل بالمركز الرأسي."""
    rows = ocr._split_rows([_word(300, 10, 40, 20, "أ"),
                            _word(100, 10, 40, 20, "ب"),
                            _word(300, 90, 40, 20, "ج"),
                            _word(100, 90, 40, 20, "د")])
    assert [len(r) for r in rows] == [2, 2]


def test_scale_maps_pixels_back_to_points():
    """الإحداثيات تُردّ إلى نقاط الصفحة، وإلا قِيس حجم السطر بمقياس آخر."""
    line = ocr._line_of([_word(300, 600, 120, 72, "كلمة")], scale=300 / 72.0)
    assert line["x0"] == pytest.approx(72.0)
    assert line["y0"] == pytest.approx(144.0)
    assert line["size"] == pytest.approx(17.3, abs=0.1)


def test_line_shape_matches_core_page_lines():
    """
    ناتج الـOCR يدخل مسار البناء نفسه، فأي مفتاح ناقص يُسقطه بـKeyError
    في منتصف تحويل طويل.
    """
    line = ocr._line_of([_word(100, 10, 40, 20, "كلمة")], scale=1.0)
    assert set(line) == {"text", "x0", "x1", "y0", "y1",
                         "size", "bold", "row", "cells"}


# ═══════════════ الياء المكسورة ═══════════════

def _span(spec, size=16.0, x=0.0):
    """
    spec = [(حرف، عرض)] — جزء rawdict بصناديق متتابعة أفقيًا.

    التنوين بعرض صفر يُوضع عند حافة الحرف السابق اليسرى لا بعده، كما يخرج
    فعلًا من الملفات المرصودة: نقطتا الياء تُرسمان فوق قاعدتها لا بجانبها.
    """
    chars, prev_x0 = [], x
    for ch, w in spec:
        if w == 0 and chars:
            chars.append({"c": ch, "bbox": (prev_x0, 0.0, prev_x0, size)})
            continue
        chars.append({"c": ch, "bbox": (x, 0.0, x + w, size)})
        prev_x0, x = x, x + w
    return {"size": size, "chars": chars}


def _text(spans):
    return "".join(c["c"] for s in spans for c in s["chars"])


def test_broken_yeh_is_mended():
    """«تف ٌد» ← «تفيد»: قاعدة بعرض حقيقي + تنوين بعرض صفر = ياء."""
    span = _span([("ت", 4.3), ("ف", 5.2), (" ", 4.3), ("ٌ", 0.0), ("د", 5.5)])
    stats = {}
    assert _text(core.mend_broken_yeh([span], stats)) == "تفيد"
    assert stats["yeh"] == 1


def test_fatha_tanween_form_is_mended_too():
    """الملف الواحد يستعمل تنوين الضم وتنوين الفتح لنقطتَي الياء معًا."""
    span = _span([("أ", 4.0), ("ن", 3.2), ("ن", 3.2), (" ", 4.3), ("ً", 0.0)])
    assert _text(core.mend_broken_yeh([span])) == "أنني"


def test_pair_split_across_spans_is_mended():
    """
    المولِّد يقطع أحيانًا بين القاعدة ونقطتيها: «الت» ثم جزء فيه المسافة
    وحدها ثم جزء يبدأ بالتنوين. المعالجة داخل الجزء الواحد كانت تفوتها.
    """
    spans = [_span([("ا", 2.6), ("ل", 2.8), ("ت", 3.3)], x=0.0),
             _span([(" ", 7.0)], x=8.7),
             _span([("ً", 0.0), (" ", 3.3), ("ت", 3.3), ("م", 4.3)], x=8.7)]
    # التنوين أول جزئه، فلا حرف قبله فيه — يُوضع فوق القاعدة يدويًا
    spans[2]["chars"][0]["bbox"] = (8.7, 0.0, 8.7, 16.0)
    assert _text(core.mend_broken_yeh(spans)) == "التي تم"


def test_floating_tanween_is_left_alone():
    """
    «تواصلكم وشكرًا» تُصدَّر أيضًا تنوينًا بعرض صفر بعد مسافة، لكنه يخصّ
    ألفًا في الكلمة التالية فيقع عند الحافة المقابلة للمسافة لا فوقها.
    هذا هو التشكيل الطائر، ويعالجه الربط الإحداثي لاحقًا لا هذا المصلح.
    """
    spans = [_span([("ك", 5.0), ("م", 4.3), (" ", 4.0)], x=0.0)]
    spans[0]["chars"].append({"c": "ً", "bbox": (13.3, 0.0, 13.3, 16.0)})
    assert _text(core.mend_broken_yeh(spans)) == "كم ً"


def test_real_tanween_after_a_letter_is_left_alone():
    """التنوين الحقيقي الملتصق بحرفه لا تسبقه قاعدة مرسومة أصلًا."""
    span = _span([("ك", 5.0), ("ت", 4.0), ("ا", 3.0), ("ب", 4.0)])
    span["chars"].append({"c": "ٌ", "bbox": (16.0, 0.0, 16.0, 16.0)})
    assert _text(core.mend_broken_yeh([span])) == "كتابٌ"


def test_zero_width_base_is_left_to_the_ligature_fixer():
    """المسافة بعرض صفر جزء رباط لا قاعدة ياء."""
    span = _span([("ل", 4.0), (" ", 0.0), ("ٌ", 0.0), ("د", 5.0)])
    assert _text(core.mend_broken_yeh([span])) == "ل ٌد"


def test_mended_yeh_keeps_the_drawn_box():
    """
    الصندوق المأخوذ هو صندوق القاعدة — المرسومة فعلًا — فتبقى قاعدة الفجوة
    وفحص الحبر بعدها يقيسان على إحداثيات حقيقية.
    """
    span = _span([("ف", 5.0), (" ", 4.0), ("ٌ", 0.0)])
    out = core.mend_broken_yeh([span])[0]["chars"]
    assert out[-1]["c"] == "ي"
    assert out[-1]["bbox"] == (5.0, 0.0, 9.0, 16.0)


def test_two_yehs_in_one_line_are_both_counted():
    span = _span([("ت", 4.3), (" ", 4.3), ("ٌ", 0.0), ("ف", 5.2),
                  ("د", 5.5), (" ", 4.3), ("ٌ", 0.0), ("ة", 5.5)])
    stats = {}
    assert _text(core.mend_broken_yeh([span], stats)) == "تيفدية"
    assert stats["yeh"] == 2
