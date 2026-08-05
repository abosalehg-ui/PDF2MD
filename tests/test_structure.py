# -*- coding: utf-8 -*-
"""
اختبارات طبقة البنية structure.py والوحدة المشتركة common.py
على ملفات PDF حقيقية تُولَّد بـ fitz أثناء الاختبار.
"""

import threading

import fitz
import pytest

from src import common
from src.structure import ConversionCancelled, Options, convert, diagnose


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


def test_convert_reversed_page_range_falls_back_to_all(tmp_path):
    pdf = make_pdf(tmp_path / "doc.pdf", [BODY, BODY])
    md, st = convert(pdf, Options(check_ink=False, page_from=2, page_to=1))
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
