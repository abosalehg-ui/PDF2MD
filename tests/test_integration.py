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

from src import core
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
