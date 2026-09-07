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


# ═══════════ نطاق الصفحات: الصفحة الواحدة ═══════════

def opts_for(pages):
    args = cli.build_parser().parse_args(["x.pdf", "--pages", pages])
    return cli.options_from(args)


def test_single_page_accepted_without_a_range():
    """كان `--pages 12` مرفوضًا، فأشيع استعمال يتطلب كتابة `12-12`."""
    opt = opts_for("12")
    assert (opt.page_from, opt.page_to) == (12, 12)


def test_single_page_tolerates_surrounding_space():
    opt = opts_for("  7  ")
    assert (opt.page_from, opt.page_to) == (7, 7)


def test_range_still_parsed():
    opt = opts_for("10-40")
    assert (opt.page_from, opt.page_to) == (10, 40)


def test_malformed_range_still_rejected():
    """قبول الصفحة الواحدة وسّع الصيغة، ولم يفتح الباب لصيغ ناقصة."""
    for bad in ("abc", "10-", "-40", "10-20-30", "1.5"):
        with pytest.raises(SystemExit):
            opts_for(bad)


def test_empty_pages_value_means_no_range():
    """`--pages ""` قيمة فارغة = لا نطاق، فيُحوَّل الملف كله (سلوك قائم)."""
    opt = opts_for("")
    assert (opt.page_from, opt.page_to) == (0, 0)


def test_reversed_range_still_rejected_after_single_page_support():
    with pytest.raises(SystemExit):
        opts_for("40-10")


# ═══════════ قاعدة -o من طرف سطر الأوامر ═══════════

def test_extensionless_out_is_a_folder(tmp_path):
    """`-o مجلد` يُنشئ مجلدًا فيه ملف باسم PDF، لا ملفًا بلا امتداد."""
    pdf = make_pdf(tmp_path / "src.pdf")
    target = tmp_path / "مخرجات"
    assert cli.main([pdf, "-o", str(target), "-q"]) == 0
    assert target.is_dir()
    assert (target / "src.md").is_file()


def test_md_out_is_a_file(tmp_path):
    pdf = make_pdf(tmp_path / "src.pdf")
    target = tmp_path / "ناتج.md"
    assert cli.main([pdf, "-o", str(target), "-q"]) == 0
    assert target.is_file()


# ═══════════ ‎-o ملفًا مع دفعة: تناقض يُرفض لا يُبتلع ═══════════

def test_md_out_with_many_inputs_is_refused(tmp_path):
    """
    الانحدار: `-o ناتج.md` مع عدة ملفات كان يمضي بصمت فيُنشئ **مجلدًا**
    اسمه «ناتج.md» يضع فيه ملفًا لكل PDF — مخرَج لا أحد يقصده، ويخالف
    القاعدة الموثَّقة في README: المنتهي بـ.md ملفٌ لا مجلد. ولا يُكتشف
    إلا بعد أن تنتهي الدفعة كلها.
    """
    a = make_pdf(tmp_path / "a.pdf")
    b = make_pdf(tmp_path / "b.pdf")
    target = tmp_path / "ناتج.md"

    with pytest.raises(SystemExit) as exit_info:
        cli.main([a, b, "-o", str(target), "-q"])

    assert "مجلدًا" in str(exit_info.value)
    assert not target.exists()          # ولا حتى مجلدًا بهذا الاسم


def test_md_out_with_one_input_still_works(tmp_path):
    """الرفض يخصّ الدفعة وحدها — الملف الواحد يبقى على قاعدته."""
    pdf = make_pdf(tmp_path / "src.pdf")
    target = tmp_path / "ناتج.md"
    assert cli.main([pdf, "-o", str(target), "-q"]) == 0
    assert target.is_file()


def test_folder_out_with_many_inputs_still_works(tmp_path):
    """والمجلد مع الدفعة هو الاستعمال الصحيح، فلا يُمَسّ."""
    a = make_pdf(tmp_path / "a.pdf")
    b = make_pdf(tmp_path / "b.pdf")
    out = tmp_path / "مخرجات"
    assert cli.main([a, b, "-o", str(out), "-q"]) == 0
    assert (out / "a.md").is_file() and (out / "b.md").is_file()


# ═══════════ حدود القيم: مصدر واحد للواجهات الثلاث ═══════════

@pytest.mark.parametrize("args, needle", [
    (["--ocr-dpi", "10"], "أقل من 200"),
    (["--ocr-dpi", "100000"], "أعلى من 600"),
    (["--para-gap", "99"], "فجوة الفقرة خارج المدى"),
    (["--para-gap", "0"], "فجوة الفقرة خارج المدى"),
])
def test_out_of_range_values_are_refused(args, needle):
    """
    الانحدار: `--ocr-dpi` كان مسقوفًا من الأسفل وحده، و`--para-gap` بلا
    حدّ إطلاقًا — بينما الواجهتان الأخريان تقيّدانهما.
    """
    parsed = cli.build_parser().parse_args(["x.pdf", *args])
    with pytest.raises(SystemExit) as exit_info:
        cli.options_from(parsed)
    assert needle in str(exit_info.value)


def test_cli_heading_levels_follow_the_shared_limits():
    """مستويات العناوين من `structure.LIMITS` لا مكتوبة في سطر الأوامر."""
    from src.structure import LIMITS

    parser = cli.build_parser()
    for flag, key in (("--h-top", "h_top"), ("--h-sub", "h_sub")):
        action = next(a for a in parser._actions if flag in a.option_strings)
        lo, hi = LIMITS[key]
        assert list(action.choices) == list(range(lo, hi + 1))
