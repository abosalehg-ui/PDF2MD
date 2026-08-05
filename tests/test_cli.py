# -*- coding: utf-8 -*-
"""اختبارات سطر الأوامر: صمود الدفعة، الكتابة فوق الملفات، النطاقات."""

import os

import fitz
import pytest

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


def test_diag_runs(tmp_path, capsys):
    pdf = make_pdf(tmp_path / "doc.pdf")
    rc = cli.main([pdf, "--diag"])
    assert rc == 0
    assert "الصفحات" in capsys.readouterr().out
