# -*- coding: utf-8 -*-
"""
اختبارات الجداول — العلم `row` و`CELL_GAP` كانا يُحسبان لكل سطر ثم يُرميان،
فتخرج الجداول مسطّحة في فقرة واحدة. الآن يُستهلكان لبناء جدول Markdown.
"""

from src import core, structure
from src.structure import Options, convert

# ═══════════ استخراج الخلايا في core ═══════════

class FakePage:
    def __init__(self, blocks):
        self._blocks = blocks

    def get_text(self, kind):
        assert kind == "rawdict"
        return {"blocks": self._blocks}


def row_page(cells, y=0.0):
    """صف جدول: كل خلية جزء rawdict مستقل تفصله فجوة أوسع من CELL_GAP."""
    lines = []
    for text, x in cells:
        chars = [{"c": c, "bbox": (x + i * 4, y, x + i * 4 + 4, y + 10)}
                 for i, c in enumerate(text)]
        lines.append({"spans": [{"chars": chars, "size": 10.0,
                                 "font": "Test", "flags": 0}]})
    return FakePage([{"type": 0, "lines": lines}])


def test_row_flag_and_cells_extracted():
    # أربع خلايا تفصلها فجوات ٢٠ نقطة — أوسع من CELL_GAP = 6
    page = row_page([("A", 10), ("B", 40), ("C", 70), ("D", 100)])
    lines = core.build_lines(core.page_units(page))
    assert lines[0]["row"] is True
    assert lines[0]["cells"] == ["A", "B", "C", "D"]     # لاتيني: يسار→يمين


def test_arabic_row_cells_ordered_right_to_left():
    """صف عربي يُقرأ من اليمين، فالخلية الأولى هي أقصى اليمين."""
    page = row_page([("ا", 10), ("ب", 40), ("ج", 70), ("د", 100)])
    lines = core.build_lines(core.page_units(page))
    assert lines[0]["row"] is True
    assert lines[0]["cells"] == ["د", "ج", "ب", "ا"]


def test_three_segments_are_not_a_row():
    """الحدّ أربعة أجزاء فأكثر — ثلاثة قد تكون سطرًا عاديًا متقطّعًا."""
    page = row_page([("A", 10), ("B", 40), ("C", 70)])
    lines = core.build_lines(core.page_units(page))
    assert lines[0]["row"] is False
    assert lines[0]["cells"] == []


def test_narrow_gaps_are_not_a_row():
    """فجوات أضيق من CELL_GAP = سطر واحد لا صف جدول."""
    page = row_page([("A", 10), ("B", 16), ("C", 22), ("D", 28)])
    lines = core.build_lines(core.page_units(page))
    assert lines[0]["row"] is False


# ═══════════ بناء الجدول في structure ═══════════

def build(monkeypatch, tmp_path, rows, **opts):
    """يمرّر أسطرًا مصطنعة عبر convert ويرجّع الناتج."""
    placed = []
    for k, cells in enumerate(rows):
        is_row = isinstance(cells, list)
        placed.append({
            "text": " ".join(cells) if is_row else cells,
            "cells": cells if is_row else [],
            "row": is_row,
            "size": 10.0, "bold": False,
            "x0": 0, "x1": 400, "y0": 100 + k * 20, "y1": 110 + k * 20,
        })
    monkeypatch.setattr(core, "page_lines", lambda page, st=None, **kw: placed)
    monkeypatch.setattr(structure, "body_font_size", lambda pages: 10.0)

    import pymupdf
    doc = pymupdf.open()
    doc.new_page()
    path = str(tmp_path / "t.pdf")
    doc.save(path)
    doc.close()
    return convert(path, Options(check_ink=False, build_toc=False, **opts))


def test_consecutive_rows_become_markdown_table(tmp_path, monkeypatch):
    md, st = build(monkeypatch, tmp_path, [
        ["الاسم", "المدة", "البدل"],
        ["أحمد", "5", "1200"],
        ["سارة", "3", "900"],
    ])
    assert "| الاسم | المدة | البدل |" in md
    assert "|---|---|---|" in md
    assert "| أحمد | 5 | 1200 |" in md
    assert st["tables"] == 1


def test_single_row_stays_a_paragraph(tmp_path, monkeypatch):
    """صف واحد معزول ليس جدولًا — الكشف قد يخطئ على سطر متقطّع."""
    md, st = build(monkeypatch, tmp_path, [["أ", "ب", "ج"], "فقرة عادية"])
    assert "|---|" not in md
    assert st["tables"] == 0
    assert "أ ب ج" in md


def test_ragged_rows_padded_to_widest(tmp_path, monkeypatch):
    """Markdown يتطلب عدد أعمدة ثابتًا — الخلايا الناقصة تُملأ فراغًا."""
    md, _ = build(monkeypatch, tmp_path, [["أ", "ب", "ج"], ["د", "هـ"]])
    assert "| د | هـ |  |" in md


def test_pipe_in_cell_escaped(tmp_path, monkeypatch):
    md, _ = build(monkeypatch, tmp_path, [["a|b", "c"], ["d", "e"]])
    assert r"| a\|b | c |" in md


def test_tables_can_be_disabled(tmp_path, monkeypatch):
    md, st = build(monkeypatch, tmp_path,
                   [["أ", "ب", "ج"], ["د", "هـ", "و"]], tables=False)
    assert "|---|" not in md
    assert st["tables"] == 0


def test_table_closed_by_following_paragraph(tmp_path, monkeypatch):
    md, st = build(monkeypatch, tmp_path, [
        ["أ", "ب"], ["ج", "د"], "فقرة بعد الجدول", ["هـ", "و"], ["ز", "ح"],
    ])
    assert st["tables"] == 2
    assert "فقرة بعد الجدول" in md


# ═══════════ تكامل على ملف PDF حقيقي ═══════════

def test_real_pdf_table_end_to_end(tmp_path):
    """
    جدول حقيقي: كل خلية عملية رسم مستقلة — وهكذا تُصدَّر الجداول فعلًا.
    بلا mock، من الملف إلى Markdown.
    """
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 120), "Quarterly Report", fontsize=18)
    rows = [("Name", "Days", "Rate", "Total"),
            ("Ahmed", "5", "240", "1200"),
            ("Sara", "3", "300", "900")]
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            page.insert_text((72 + c * 110, 200 + r * 20), cell, fontsize=10)
    page.insert_text((72, 300), "Notes follow the table below.", fontsize=11)
    path = str(tmp_path / "tbl.pdf")
    doc.save(path)
    doc.close()

    md, st = convert(path, Options(check_ink=False, build_toc=False))
    assert st["tables"] == 1
    assert "| Name | Days | Rate | Total |" in md
    assert "| Ahmed | 5 | 240 | 1200 |" in md
    assert "Notes follow the table below." in md      # الفقرة تغلق الجدول


# ═══════════ الجدول مقابل قاعدة الحاشية ═══════════

def placed_page(monkeypatch, tmp_path, lines, **opts):
    """يمرّر أسطرًا مصطنعة كاملة الإحداثيات عبر convert بلا مساس بـbody_size."""
    monkeypatch.setattr(core, "page_lines", lambda page, st=None, **kw: lines)
    monkeypatch.setattr(structure, "body_font_size", lambda pages: 11.0)

    import pymupdf
    doc = pymupdf.open()
    doc.new_page()                                   # A4 — ارتفاع 842
    path = str(tmp_path / "notes.pdf")
    doc.save(path)
    doc.close()
    return convert(path, Options(check_ink=False, build_toc=False, **opts))


def body_line(text, y, size=11.0):
    return {"text": text, "cells": [], "row": False, "size": size,
            "bold": False, "x0": 72, "x1": 400, "y0": y, "y1": y + 12}


def table_line(cells, y, size=8.0):
    return {"text": " ".join(cells), "cells": cells, "row": True, "size": size,
            "bold": False, "x0": 72, "x1": 500, "y0": y, "y1": y + 10}


def test_small_table_in_lower_half_is_not_swallowed_as_a_footnote(
        tmp_path, monkeypatch):
    """
    الانحدار: الجدول يُصفّ بخط أصغر من المتن ويقع غالبًا أسفل الصفحة، فيحقق
    شرطي الحاشية معًا. وبلا استثنائه كانت صفوفه تُبتلع ثم تضمّها قاعدة
    تكملة الحاشية في سطر اقتباس واحد — فقدان تام للبنية بلا تحذير.
    """
    lines = [body_line("Body sentence one here.", 100),
             body_line("Body sentence two here.", 116),
             table_line(["A", "B", "C", "D"], 520),
             table_line(["1", "2", "3", "4"], 534),
             table_line(["5", "6", "7", "8"], 548)]
    md, st = placed_page(monkeypatch, tmp_path, lines)

    assert st["tables"] == 1
    assert st["notes"] == 0
    assert "| A | B | C | D |" in md
    assert "> A B C D" not in md              # لم يخرج اقتباسًا ملتحمًا


def test_real_footnote_in_lower_half_still_captured(tmp_path, monkeypatch):
    """الاستثناء للجداول وحدها — الحاشية الحقيقية ما زالت تُلتقط وتُؤجَّل."""
    lines = [body_line("Body sentence one here.", 100),
             body_line("(1) A genuine footnote.", 560, size=8.0)]
    md, st = placed_page(monkeypatch, tmp_path, lines)

    assert st["notes"] == 1
    assert "> (1) A genuine footnote." in md


def test_table_rows_become_footnotes_when_tables_disabled(
        tmp_path, monkeypatch):
    """مع --no-tables لا يوجد جدول يُحمى، فالصف الصغير يعود حاشيةً."""
    lines = [body_line("Body sentence one here.", 100),
             table_line(["A", "B", "C", "D"], 520),
             table_line(["1", "2", "3", "4"], 534)]
    md, st = placed_page(monkeypatch, tmp_path, lines, tables=False)

    assert st["tables"] == 0
    assert "|" not in md
