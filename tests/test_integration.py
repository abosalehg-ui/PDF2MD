# -*- coding: utf-8 -*-
"""
اختبارات تكامل على ملفات PDF **حقيقية** تُولَّد بـfitz أثناء الاختبار.

بقية الاختبارات تحاكي rawdict بقواميس مبنية يدويًا — وهو قرار صحيح لأن
حقن خلل ToUnicode في ملف حقيقي متعذّر. لكنه يترك ثغرة: أي تغيّر في مفاتيح
PyMuPDF (alpha / dir / color) يمرّ من CI أخضر ثم يكسر الأداة على أول ملف
حقيقي. هذا الملف يحرس **العقد مع المكتبة** لا المنطق.
"""

import pytest

try:
    import pymupdf as fitz
except ImportError:                     # PyMuPDF < 1.24.3
    import fitz

from src import core, ocr
from src.structure import Options, convert

# ═══════════ العقد مع rawdict ═══════════

RAW_KEYS = ("alpha", "color", "chars", "size", "font", "flags")


def test_rawdict_still_carries_the_keys_we_depend_on(tmp_path):
    """
    المفاتيح التي يقرأها core موجودة فعلًا في مخرَج PyMuPDF المثبَّت.

    غياب أيٍّ منها لا يرمي استثناءً في الأداة — الشيفرة تستعمل .get مع
    افتراضي — بل يعطّل الرصد **بصمت**: العلامة المائية تبقى في الناتج
    ولا شيء يشير إلى العطل.
    """
    path = str(tmp_path / "keys.pdf")
    doc = fitz.open()
    doc.new_page().insert_text((72, 200), "probe", fontsize=11)
    doc.save(path)
    doc.close()

    doc = fitz.open(path)
    try:
        blocks = [b for b in doc[0].get_text("rawdict")["blocks"] if b["type"] == 0]
        line = blocks[0]["lines"][0]
        assert "dir" in line, "مفتاح dir مفقود — رصد الميل يتعطّل بصمت"
        for key in RAW_KEYS:
            assert key in line["spans"][0], f"مفتاح {key} مفقود من الجزء"
    finally:
        doc.close()


# ═══════════ العلامة المائية على ملف حقيقي ═══════════

def watermarked_pdf(path):
    """متن أسود + نص شفاف + سطر مائل + ختم رمادي معتم."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 200), "Normal body text", fontsize=11)
    page.insert_text((72, 300), "FAINT", fontsize=30, fill_opacity=0.3)
    page.insert_text((72, 400), "TILTED", fontsize=30,
                     morph=(fitz.Point(72, 400), fitz.Matrix(45)))
    page.insert_text((72, 500), "GRAY STAMP COPY", fontsize=30,
                     color=(0.80, 0.80, 0.80))
    doc.save(str(path))
    doc.close()
    return str(path)


def test_three_watermark_signals_fire_on_a_real_file(tmp_path):
    """الإشارات الثلاث تعمل على ملف حقيقي لا على قاموس مصطنع."""
    pdf = watermarked_pdf(tmp_path / "wm.pdf")
    md, st = convert(pdf, Options(check_ink=False, build_toc=False))

    assert st["watermark"] == 3          # الشفاف والمائل والرمادي
    assert "Normal body text" in md
    for ghost in ("FAINT", "TILTED", "GRAY STAMP"):
        assert ghost not in md


def test_gray_stamp_does_not_become_a_heading(tmp_path):
    """
    الانحدار الذي وُلد منه فحص اللون: الختم الرمادي كان ينجو، وكِبَر خطه
    يجعل classify يرقّيه عنوانًا فيدخل الفهرس المولَّد ويلوّث بنية المستند.
    """
    pdf = watermarked_pdf(tmp_path / "wm2.pdf")
    md, _ = convert(pdf, Options(check_ink=False, build_toc=True))
    assert "## GRAY STAMP COPY" not in md
    assert "#" not in md                 # لا عنوان ولا فهرس أصلًا


def test_keep_watermark_restores_everything(tmp_path):
    """الخيار يعطّل الإشارات الثلاث معًا، لا الشفافية وحدها."""
    pdf = watermarked_pdf(tmp_path / "wm3.pdf")
    md, st = convert(pdf, Options(check_ink=False, build_toc=False,
                                  drop_watermark=False))
    assert st["watermark"] == 0
    assert "GRAY STAMP COPY" in md


# ═══════════ سقف بكسلات فحص الحبر ═══════════

def test_oversized_page_is_rasterised_under_the_ceiling(tmp_path):
    """
    صفحة ١٤٤٠٠×١٤٤٠٠ نقطة مشروعة في مواصفة PDF، وهي عند ١٥٠ نقطة/بوصة
    تطلب ٩٠٠ مليون بكسل — قِيس فعليًا ٢٫٦ غيغابايت من ملف حجمه ٨٠٠ بايت.
    السقف ينزّل الدقة بدل أن تموت العملية.
    """
    path = str(tmp_path / "huge.pdf")
    doc = fitz.open()
    doc.new_page(width=14400, height=14400).insert_text(
        (100, 100), "hello", fontsize=40)
    doc.save(path)
    doc.close()

    doc = fitz.open(path)
    try:
        ink, z = core.ink_map(doc[0])
        # هامش ١٪ لأن get_pixmap يقرّب الأبعاد لأعلى إلى بكسلات صحيحة.
        # بلا السقف كان الناتج ٩٠٠ مليون بكسل — أي ٢٢ ضعفًا لا ١٪.
        assert ink.size <= core.INK_MAX_PIXELS * 1.01
        assert 0 < z < core.INK_DPI / 72.0        # نزلت الدقة فعلًا
    finally:
        doc.close()


def test_normal_page_keeps_full_dpi(tmp_path):
    """صفحة A4 دون السقف بمراحل — الدقة تبقى كما هي بلا تنزيل."""
    path = str(tmp_path / "a4.pdf")
    doc = fitz.open()
    doc.new_page().insert_text((72, 200), "hello", fontsize=11)
    doc.save(path)
    doc.close()

    doc = fitz.open(path)
    try:
        _, z = core.ink_map(doc[0])
        assert z == pytest.approx(core.INK_DPI / 72.0)
    finally:
        doc.close()


# ═══════════ حكم الـOCR على صفحات حقيقية ═══════════
#
# هذا القسم يسدّ الثغرة التي مرّ منها أخطر عيب في المشروع: كل اختبارات
# `ocr` كانت تبني قواميس rawdict يدويًا، فلم تمرّ **صفحة PyMuPDF حقيقية
# واحدة** على `page_verdict`. وكانت `_body_chars` تقرأ `span["text"]` وهو
# مفتاح لا وجود له في rawdict، فترجع صفرًا دائمًا وتُحكَم كل صفحة تحمل
# شعارًا بأنها ممسوحة ضوئيًا — ومرّ ذلك من CI أخضر.

def _text_page(doc, lines=35, size=11):
    """صفحة متن عربي كثيف — ما يجب ألّا يُحكم عليه بالعطب أبدًا."""
    page = doc.new_page()
    y = 60
    for i in range(lines):
        page.insert_text((60, y), f"سطر متن عربي حقيقي رقم {i} في هذه الصفحة",
                         fontsize=size)
        y += 20
    return page


def _gray_image(page, rect):
    """صورة رمادية معتمة — شعار جهة أو ختم، لا علامة مائية نصية."""
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 300, 250))
    pix.set_rect(pix.irect, (200, 200, 200))
    page.insert_image(rect, pixmap=pix)


def test_rawdict_spans_carry_chars_and_never_text():
    """
    العقد المقلوب: `text` مفتاح `dict` وحده، و`rawdict` يعطي `chars`.

    قراءة `span.get("text", "")` على rawdict لا ترمي استثناءً — ترجّع
    فراغًا، فيصير كل عدّ مبني عليها صفرًا **بصمت**. هذا الاختبار يثبّت
    الفرق بين الوضعين حتى لا يعود الخلط.
    """
    doc = fitz.open()
    try:
        _text_page(doc, lines=3)
        raw_span = doc[0].get_text("rawdict")["blocks"][0]["lines"][0]["spans"][0]
        dict_span = doc[0].get_text("dict")["blocks"][0]["lines"][0]["spans"][0]
        assert "chars" in raw_span
        assert "text" not in raw_span, "rawdict صار يحمل text — راجع _body_chars"
        assert "text" in dict_span
    finally:
        doc.close()


def test_body_chars_counts_a_real_text_layer():
    """صفحة فيها ألف حرف يجب ألّا تُعدّ خاوية."""
    doc = fitz.open()
    try:
        page = _text_page(doc)
        assert ocr._body_chars(page) > 500
    finally:
        doc.close()


def test_healthy_page_with_a_logo_is_not_called_scanned():
    """
    الانحدار الحرج: صفحة متن غزير + شعار يغطي ~١٣٪ من مساحتها.

    كانت `_body_chars` ترجّع صفرًا فينهار حدّ الصفحة الممسوحة من
    IMG_COVER إلى IMG_COVER_EMPTY، فتُحكَم الصفحة «ممسوحة بلا طبقة نص»
    وتُرمى طبقة نصها السليمة في OCR أدنى منها. وترويسة الجهة أو الختم
    هما الشكل الغالب للمستندات التي بُنيت الأداة لها.
    """
    doc = fitz.open()
    try:
        page = _text_page(doc)
        _gray_image(page, fitz.Rect(280, 560, 560, 830))
        cover = ocr._image_cover(page)
        assert cover >= ocr.IMG_COVER_EMPTY, "الشعار أصغر من أن يختبر الانحدار"
        assert cover < ocr.IMG_COVER, "الشعار أكبر من أن يميّز العتبتين"
        assert ocr.page_verdict(page) == (False, "")
    finally:
        doc.close()


def test_truly_scanned_page_is_still_detected():
    """والوجه الآخر: صفحة صورة بلا نص تبقى مرصودة — الإصلاح لم يعطّل الرصد."""
    doc = fitz.open()
    try:
        page = doc.new_page()
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 600, 850))
        pix.set_rect(pix.irect, (180, 180, 180))
        page.insert_image(page.rect, pixmap=pix)
        want, why = ocr.page_verdict(page)
        assert want and "ممسوحة" in why
    finally:
        doc.close()


def test_shared_rawdict_gives_the_same_verdict_as_reparsing():
    """تمرير rawdict محلَّلًا مسبقًا لا يغيّر الحكم — التسريع بلا أثر."""
    doc = fitz.open()
    try:
        page = _text_page(doc)
        _gray_image(page, fitz.Rect(280, 560, 560, 830))
        raw = page.get_text("rawdict")
        assert ocr.page_verdict(page, raw) == ocr.page_verdict(page)
        assert ocr._body_chars(page, raw) == ocr._body_chars(page)
        assert ocr.broken_yeh_hits(page, raw) == ocr.broken_yeh_hits(page)
    finally:
        doc.close()


def test_shared_rawdict_gives_the_same_lines_as_reparsing(tmp_path):
    """والمحرّك كذلك: الأسطر المبنية من rawdict ممرَّر = المبنية من صفحة."""
    path = str(tmp_path / "shared.pdf")
    doc = fitz.open()
    _text_page(doc)
    doc.save(path)
    doc.close()

    doc = fitz.open(path)
    try:
        page = doc[0]
        passed = core.page_lines(page, check_ink=False,
                                 raw=page.get_text("rawdict"))
        fresh = core.page_lines(page, check_ink=False)
        assert [ln["text"] for ln in passed] == [ln["text"] for ln in fresh]
        assert passed and any(ln["text"] for ln in passed)
    finally:
        doc.close()
