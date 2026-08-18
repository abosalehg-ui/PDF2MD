# -*- coding: utf-8 -*-
"""
اختبارات طبقة البنية structure.py والوحدة المشتركة common.py
على ملفات PDF حقيقية تُولَّد بـ fitz أثناء الاختبار.
"""

import threading

import pytest

try:
    import pymupdf as fitz
except ImportError:                     # PyMuPDF < 1.24.3
    import fitz

from src import common
from src.structure import (
    ConversionCancelled,
    Options,
    anchor_of,
    body_font_size,
    boiler_key,
    convert,
    diagnose,
    heading_shaped,
)

# ═══════════ توليد ملفات الاختبار ═══════════

def make_pdf(path, pages):
    """pages: قائمة صفحات، كل صفحة قائمة (نص، y، حجم الخط)."""
    doc = fitz.open()
    for spec in pages:
        page = doc.new_page()                      # A4: 595 × 842
        for text, y, size in spec:
            page.insert_text((72, y), text, fontsize=size)
    doc.save(str(path))
    doc.close()
    return str(path)


BODY = [("Lorem ipsum dolor sit amet consectetur.", 200, 11),
        ("Sed do eiusmod tempor incididunt ut labore.", 216, 11),
        ("Ut enim ad minim veniam quis nostrud.", 232, 11)]


# ═══════════ التحويل الأساسي ═══════════

def test_convert_headings_and_paragraphs(tmp_path):
    pdf = make_pdf(tmp_path / "doc.pdf",
                   [[("Chapter One", 100, 20)] + BODY])
    md, st = convert(pdf, Options(check_ink=False))
    assert "## Chapter One" in md
    assert "Lorem ipsum" in md
    assert st["headings"] == 1


def test_reversed_page_range_warns_and_runs_to_end(tmp_path):
    """النطاق المقلوب يُقصّ إلى نهاية الملف — بتحذير صريح لا بصمت."""
    pdf = make_pdf(tmp_path / "doc.pdf", [BODY, BODY, BODY])
    said = []
    md, st = convert(pdf, Options(check_ink=False, page_from=2, page_to=1),
                     log=said.append)
    assert st["pages"] == 2                       # من الصفحة ٢ إلى النهاية
    assert any("أصغر من بدايته" in m for m in said)


def test_page_from_beyond_document_rejected(tmp_path):
    """طلب صفحات خارج المدى كان يسقط بصمت إلى «الملف كله»."""
    pdf = make_pdf(tmp_path / "doc.pdf", [BODY, BODY])
    with pytest.raises(ValueError, match="تتجاوز عدد صفحات"):
        convert(pdf, Options(check_ink=False, page_from=500, page_to=600))


def test_valid_page_range_honoured(tmp_path):
    pdf = make_pdf(tmp_path / "doc.pdf", [BODY, BODY, BODY, BODY])
    _, st = convert(pdf, Options(check_ink=False, page_from=2, page_to=3))
    assert st["pages"] == 2


# ═══════════ الترويسة والتذييل المتكرران ═══════════

def test_repeated_footer_dropped(tmp_path):
    # التذييل النصي المتكرر عبر الصفحات يُحذف — كان يُحذف رقم الصفحة فقط
    footer = ("Labor Law Edition 1442", 810, 9)
    header = ("Ministry Portal", 30, 9)
    pdf = make_pdf(tmp_path / "doc.pdf",
                   [[header] + BODY + [footer] for _ in range(4)])
    md, _ = convert(pdf, Options(check_ink=False))
    assert "Labor Law Edition" not in md
    assert "Ministry Portal" not in md
    assert "Lorem ipsum" in md


def test_keep_headers_option(tmp_path):
    footer = ("Labor Law Edition 1442", 810, 9)
    pdf = make_pdf(tmp_path / "doc.pdf",
                   [BODY + [footer] for _ in range(4)])
    md, _ = convert(pdf, Options(check_ink=False, drop_headers=False))
    assert "Labor Law Edition" in md


# ═══════════ الحالات الحدّية ═══════════

def test_encrypted_pdf_raises_clear_error(tmp_path):
    path = tmp_path / "locked.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "secret")
    doc.save(str(path), encryption=fitz.PDF_ENCRYPT_AES_256,
             user_pw="pw", owner_pw="pw")
    doc.close()
    with pytest.raises(ValueError, match="محمي بكلمة مرور"):
        convert(str(path), Options(check_ink=False))
    with pytest.raises(ValueError, match="محمي بكلمة مرور"):
        diagnose(str(path))


def test_cancel_raises(tmp_path):
    pdf = make_pdf(tmp_path / "doc.pdf", [BODY])
    ev = threading.Event()
    ev.set()
    with pytest.raises(ConversionCancelled):
        convert(pdf, Options(check_ink=False), cancel=ev)


def test_diagnose_clean_file(tmp_path):
    pdf = make_pdf(tmp_path / "doc.pdf", [BODY])
    d = diagnose(pdf)
    assert d["has_text"] and not d["needs_ocr"]
    assert d["ligatures"] == 0
    assert all(r["after_bad"] == 0 for r in d["rows"])


# ═══════════ مراسي الفهرس ═══════════

def test_anchor_is_lowercased():
    """مصيّرات Markdown تصغّر المراسي — «#Chapter-One» رابط ميت."""
    assert anchor_of("Chapter One") == "chapter-one"
    assert anchor_of("الفصل الأول:") == "الفصل-الأول"


def test_anchor_resolves_collisions():
    seen = {}
    assert anchor_of("الفصل الأول", seen) == "الفصل-الأول"
    assert anchor_of("الفصل الأول", seen) == "الفصل-الأول-1"
    assert anchor_of("الفصل الأول", seen) == "الفصل-الأول-2"
    assert anchor_of("الباب الثاني", seen) == "الباب-الثاني"


def test_toc_links_unique_for_repeated_headings(tmp_path):
    pdf = make_pdf(tmp_path / "doc.pdf",
                   [[("Chapter One", 100, 20)] + BODY for _ in range(2)])
    md, _ = convert(pdf, Options(check_ink=False, drop_headers=False))
    links = [ln for ln in md.splitlines() if ln.startswith("- [")]
    assert links == ["- [Chapter One](#chapter-one)",
                     "- [Chapter One](#chapter-one-1)"]


# ═══════════ حجم خط المتن ═══════════

def _page(lines):
    return (0, [{"text": t, "size": s, "y0": 0, "y1": s} for t, s in lines], 842)


def test_long_footnotes_do_not_steal_body_size():
    """
    ثلاثة أسطر حاشية طويلة مقابل عشرة أسطر متن: بلا سقف على مساهمة السطر
    يغلب مجموعُ حروف الحاشية المتنَ، لأن الوزن يقيس الحروف لا الأسطر.
    """
    pages = [_page([("سطر متن بطول معقول في هذه الصفحة هنا.", 11.0)] * 10
                   + [("حاشية مطوّلة جدًّا " * 20, 8.0)] * 3)]
    assert body_font_size(pages) == 11.0


def test_body_size_picks_dominant_when_uniform():
    pages = [_page([("سطر متن عادي.", 11.0) for _ in range(20)]
                   + [("عنوان", 20.0)])]
    assert body_font_size(pages) == 11.0


def test_body_size_empty_document():
    assert body_font_size([]) == 12.0


# ═══════════ شكل العنوان ═══════════

def test_sentence_is_never_a_heading():
    """الجملة المنتهية بنقطة ليست عنوانًا مهما كبر خطها."""
    assert not heading_shaped("نص المتن ينتهي بنقطة.")
    assert not heading_shaped("Main body paragraph one here.")
    assert not heading_shaped("عبارة تنتهي بفاصلة،")
    assert heading_shaped("الباب الأول")
    assert heading_shaped("المادة الأولى:")          # النقطتان مسموحتان
    assert not heading_shaped("ف" * 200)             # أطول من أن يكون عنوانًا


def test_dense_small_text_does_not_promote_body_to_headings(tmp_path):
    """
    الانقلاب المرصود: صفحة فيها سطرا متن 12pt وسبعة صفوف 9pt كانت تُخرج
    المتن عناوين (### …) والجدولَ متنًا.
    """
    body = [("Main body paragraph one here.", 150, 12),
            ("Main body paragraph two here.", 170, 12)]
    rows = [(f"Row {k}  |  Value {k}  |  Note {k}", 500 + k * 16, 9)
            for k in range(7)]
    pdf = make_pdf(tmp_path / "doc.pdf", [body + rows])
    md, _ = convert(pdf, Options(check_ink=False, drop_headers=False))
    assert "Main body paragraph one here." in md
    assert "### Main body paragraph one here." not in md
    assert "## Main body paragraph one here." not in md


# ═══════════ مفتاح الترويسة ═══════════

def test_boiler_key_strips_both_digit_sets():
    assert boiler_key("صفحة 12") == boiler_key("صفحة 45")
    assert boiler_key("صفحة ٣٤") == boiler_key("صفحة ٧")
    assert boiler_key("نظام العمل") != boiler_key("اللائحة التنفيذية")


# ═══════════ common.py ═══════════

def test_verdict_of():
    clean = [{"before_bad": 0, "after_bad": 0}]
    fixed = [{"before_bad": 5, "after_bad": 0}]
    partial = [{"before_bad": 5, "after_bad": 2}]
    assert common.verdict_of(clean)[1] is True
    assert "سليم" in common.verdict_of(clean)[0]
    assert common.verdict_of(fixed)[1] is True
    assert "بالكامل" in common.verdict_of(fixed)[0]
    assert common.verdict_of(partial)[1] is False


def test_out_path_for(tmp_path):
    pdf = str(tmp_path / "كتاب.pdf")
    explicit = str(tmp_path / "خاص.md")
    folder = str(tmp_path / "md")
    assert common.out_path_for(pdf, explicit, many=False) == explicit
    got = common.out_path_for(pdf, folder, many=True)
    assert got.endswith("كتاب.md") and got.startswith(folder)
    beside = common.out_path_for(pdf, None, many=False)
    assert beside == str(tmp_path / "كتاب.md")


def test_out_path_for_has_no_side_effects(tmp_path):
    """كانت تنشئ المجلد بمجرد حساب المسار، قبل موافقة المستخدم."""
    folder = tmp_path / "لم-يُنشأ-بعد"
    common.out_path_for(str(tmp_path / "كتاب.pdf"), str(folder), many=True)
    assert not folder.exists()


def test_ensure_parent_creates_folder(tmp_path):
    target = tmp_path / "عميق" / "أعمق" / "ملف.md"
    common.ensure_parent(str(target))
    assert target.parent.is_dir()


# ═══════════ الحكم عند ازدياد التلف ═══════════

def test_verdict_reports_no_improvement_when_damage_grows():
    """
    «أُصلح أغلب التلف» ادّعاء لا يصحّ إلا إذا نقص العدد. كان الحكم يجزم
    بالإصلاح حتى حين يزيد التلف بعد المعالجة.
    """
    worse = [{"before_bad": 2, "after_bad": 5}]
    text, ok = common.verdict_of(worse)
    assert ok is False
    assert "لم يتحسّن" in text
    assert "أغلب" not in text


def test_verdict_no_improvement_when_damage_unchanged():
    same = [{"before_bad": 3, "after_bad": 3}]
    text, ok = common.verdict_of(same)
    assert ok is False and "لم يتحسّن" in text


# ═══════════ قاعدة -o: الامتداد يحسم لا الوجود ═══════════

def test_out_path_treats_extensionless_path_as_a_folder(tmp_path):
    """
    كان `-o out` مع ملف واحد يُنتج ملفًا بلا امتداد اسمه out، ومع ملفين
    يُنتج مجلدًا بالاسم نفسه — فيتغيّر معنى الخيار بعدد ملفات الدخل.
    """
    pdf = str(tmp_path / "كتاب.pdf")
    folder = str(tmp_path / "مخرجات")            # غير موجود وبلا امتداد
    single = common.out_path_for(pdf, folder, many=False)
    batch = common.out_path_for(pdf, folder, many=True)
    assert single == batch                       # المعنى واحد في الحالتين
    assert single.endswith("كتاب.md")


def test_out_path_named_md_file_is_honoured_for_single_input(tmp_path):
    target = str(tmp_path / "مخرج.md")
    assert common.out_path_for(str(tmp_path / "ك.pdf"), target,
                               many=False) == target


def test_out_path_named_md_becomes_folder_for_a_batch(tmp_path):
    """في الدفعة لا يصلح مسار واحد ملفًا مهما كان امتداده."""
    target = str(tmp_path / "مخرج.md")
    got = common.out_path_for(str(tmp_path / "ك.pdf"), target, many=True)
    assert got.startswith(target) and got.endswith("ك.md")


# ═══════════ تجاوز نهاية النطاق يُقصّ ويُقال ═══════════

def test_page_to_beyond_document_warns(tmp_path):
    """القصّ الصامت كان يترك من طلب 2-999 يظن أنه استلم ٩٩٨ صفحة."""
    pdf = make_pdf(tmp_path / "d.pdf", [BODY, BODY, BODY])
    said = []
    md, st = convert(pdf, Options(page_from=2, page_to=999, check_ink=False),
                     log=said.append)
    assert st["pages"] == 2
    assert any("تتجاوز عدد صفحات الملف" in m for m in said)


def test_page_to_within_document_is_silent(tmp_path):
    pdf = make_pdf(tmp_path / "d.pdf", [BODY, BODY, BODY])
    said = []
    convert(pdf, Options(page_from=1, page_to=3, check_ink=False),
            log=said.append)
    assert not any("تتجاوز" in m for m in said)


# ═══════════ تحذير المستند الضخم ═══════════

def test_big_document_warns_once(tmp_path, monkeypatch):
    """التحذير مبني على عدد صفحات المدى، فيُختبر بخفض العتبة لا ببناء ٢٠٠٠."""
    monkeypatch.setattr("src.structure.BIG_DOC_PAGES", 2)
    pdf = make_pdf(tmp_path / "big.pdf", [BODY, BODY, BODY])
    said = []
    convert(pdf, Options(check_ink=False), log=said.append)
    assert sum("مستند ضخم" in m for m in said) == 1
