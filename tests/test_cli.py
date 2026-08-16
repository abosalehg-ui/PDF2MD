# -*- coding: utf-8 -*-
"""اختبارات سطر الأوامر: صمود الدفعة، الكتابة فوق الملفات، النطاقات."""

import os

import pytest

try:
    import pymupdf as fitz
except ImportError:                     # PyMuPDF < 1.24.3
    import fitz

from src import cli


def make_pdf(path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Hello world content line.", fontsize=11)
    doc.save(str(path))
    doc.close()
    return str(path)


def test_batch_survives_bad_file(tmp_path, capsys):
    """ملف تالف وسط الدفعة لا يوقفها — يُتخطّى ويظهر في exit code."""
    good = make_pdf(tmp_path / "good.pdf")
    bad = tmp_path / "bad.pdf"
    bad.write_text("this is not a pdf")
    out = tmp_path / "md"

    rc = cli.main([str(bad), good, "-o", str(out), "--no-ink", "-q"])

    assert rc == 1                                   # فشل جزئي
    assert (out / "good.md").exists()                # الملف السليم تحوّل
    assert "فشل تحويل bad.pdf" in capsys.readouterr().err


def test_existing_output_skipped_without_force(tmp_path, capsys):
    pdf = make_pdf(tmp_path / "doc.pdf")
    out_md = tmp_path / "doc.md"
    out_md.write_text("قديم", encoding="utf-8")

    rc = cli.main([pdf, "--no-ink", "-q"])
    assert rc == 0
    assert out_md.read_text(encoding="utf-8") == "قديم"     # لم يُلمس
    assert "موجود مسبقًا" in capsys.readouterr().out

    rc = cli.main([pdf, "--no-ink", "-q", "--force"])
    assert rc == 0
    assert out_md.read_text(encoding="utf-8") != "قديم"     # كُتب فوقه


def test_missing_file_exits(tmp_path):
    with pytest.raises(SystemExit):
        cli.main([str(tmp_path / "ghost.pdf")])


def test_reversed_page_range_rejected(tmp_path):
    pdf = make_pdf(tmp_path / "doc.pdf")
    with pytest.raises(SystemExit):
        cli.main([pdf, "--pages", "40-10"])


def test_missing_output_dir_is_created(tmp_path):
    """مجلد مخرَج غير موجود كان يُنهي الدفعة بـFileNotFoundError خام."""
    pdf = make_pdf(tmp_path / "doc.pdf")
    out = tmp_path / "لم" / "يُنشأ" / "بعد.md"
    rc = cli.main([pdf, "-o", str(out), "--no-ink", "-q"])
    assert rc == 0
    assert out.exists()


def test_unwritable_output_reported_not_crashed(tmp_path, capsys):
    """
    فشل الكتابة يُسجَّل ويُتخطّى كفشل التحويل تمامًا — كان يخرج traceback خامًا
    بعد إتمام التحويل، فيسقط الدفعة كلها ويضيع الناتج.
    """
    good = make_pdf(tmp_path / "good.pdf")
    blocked = tmp_path / "مانع"
    blocked.write_text("ليس مجلدًا")        # مسار الأب ملف لا مجلد
    out = blocked / "خرج.md"

    rc = cli.main([good, "-o", str(out), "--no-ink", "-q"])

    assert rc == 1
    assert "فشل تحويل good.pdf" in capsys.readouterr().err


def test_batch_continues_after_write_failure(tmp_path, capsys):
    """فشل كتابة ملف لا يمنع بقية الدفعة."""
    a = make_pdf(tmp_path / "a.pdf")
    b = make_pdf(tmp_path / "b.pdf")
    blocked = tmp_path / "out"
    blocked.mkdir()
    (blocked / "a.md").mkdir()             # مجلد مكان الملف => الكتابة تفشل

    rc = cli.main([a, b, "-o", str(blocked), "--no-ink", "-q", "--force"])

    assert rc == 1
    assert (blocked / "b.md").is_file()    # الثاني تحوّل رغم فشل الأول
    assert "فشل تحويل a.pdf" in capsys.readouterr().err


def test_page_range_beyond_document_reported(tmp_path, capsys):
    pdf = make_pdf(tmp_path / "doc.pdf")
    rc = cli.main([pdf, "--pages", "500-600", "--no-ink", "-q"])
    assert rc == 1
    assert "تتجاوز عدد صفحات" in capsys.readouterr().err


@pytest.mark.parametrize("level", ["0", "7", "400"])
def test_heading_level_out_of_range_rejected(tmp_path, level):
    pdf = make_pdf(tmp_path / "doc.pdf")
    with pytest.raises(SystemExit):
        cli.main([pdf, "--h-top", level])


def test_diag_runs(tmp_path, capsys):
    pdf = make_pdf(tmp_path / "doc.pdf")
    rc = cli.main([pdf, "--diag"])
    assert rc == 0
    assert "الصفحات" in capsys.readouterr().out
