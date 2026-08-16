# -*- coding: utf-8 -*-
"""
اختبارات نمط الأنظمة السعودية — النمط الرئيسي المعلَن في README وفي أمثلة
سطر الأوامر، وكان بلا اختبار واحد رغم أنه خمسة تعابير نمطية متشابكة وحالة
`in_laiha` تعبر بين الأسطر.

التصنيف يُختبَر مباشرةً عبر classify() بأسطر مصطنعة. أما البناء الكامل
(الالتحام بين «اللائحة التنفيذية» والمادة التي تليها) فيُختبَر عبر convert()
مع استبدال core.page_lines بأسطر مصطنعة: الخطوط المتاحة في بيئة الاختبار
بلا محارف عربية، فالنص العربي يسقط من أي ملف PDF يُولَّد هنا.
"""

import pytest

from src import core, structure
from src.structure import Options, classify, convert

LAW = Options(profile="saudi_law")
BODY = 12.0


def line(text, size=BODY, bold=False):
    return {"text": text, "size": size, "bold": bold,
            "x0": 0, "x1": 400, "y0": 0, "y1": size, "row": False, "cells": []}


# ═══════════ الباب والفصل ═══════════

def test_bab_is_top_heading():
    assert classify(line("الباب الأول", BODY + 4), LAW, BODY) == "top"


def test_fasl_is_top_heading():
    assert classify(line("الفصل الثاني", BODY + 2), LAW, BODY) == "top"


def test_bab_at_body_size_is_not_heading():
    """الحجم شرط: «الباب» داخل جملة متن لا يصير عنوانًا."""
    assert classify(line("الباب الأول", BODY), LAW, BODY) == "para"


# ═══════════ المادة ═══════════

def test_madda_numbered_is_sub_heading():
    assert classify(line("المادة (12)", bold=True), LAW, BODY) == "sub"


def test_madda_spelled_out_is_sub_heading():
    got = classify(line("المادة الثانية والعشرون (22):", bold=True), LAW, BODY)
    assert got == "sub"


def test_madda_requires_bold():
    """غير الغامق يبقى متنًا — وإلا صارت كل إحالة إلى مادة عنوانًا."""
    assert classify(line("المادة (12)", bold=False), LAW, BODY) != "sub"


def test_madda_accepts_ha_spelling():
    assert classify(line("الماده (5)", bold=True), LAW, BODY) == "sub"


# ═══════════ اللائحة التنفيذية ═══════════

@pytest.mark.parametrize("text", ["اللائحة التنفيذية:",
                                  "اللائحة التنفيذية",
                                  "اللائحه التنفيذيه :"])
def test_laiha_detected(text):
    assert classify(line(text), LAW, BODY) == "laiha"


def test_laiha_with_trailing_content_is_not_laiha():
    got = classify(line("اللائحة التنفيذية للمادة الخامسة تنص على"), LAW, BODY)
    assert got != "laiha"


# ═══════════ البنود والتعريفات ═══════════

@pytest.mark.parametrize("text", ["1- البند الأول", "3/1- البند الفرعي",
                                  "2. بند مرقّم", "• بند منقوط"])
def test_items_detected(text):
    assert classify(line(text), LAW, BODY) == "item"


def test_definition_detected():
    got = classify(line("الوزارة: وزارة الموارد البشرية", bold=True), LAW, BODY)
    assert got == "definition"


def test_definition_requires_bold():
    assert classify(line("الوزارة: وزارة الموارد البشرية"), LAW, BODY) == "para"


def test_plain_paragraph_stays_para():
    got = classify(line("يجوز لصاحب العمل إنهاء العقد وفق الشروط."), LAW, BODY)
    assert got == "para"


# ═══════════ الترتيب بين القواعد ═══════════

def test_item_wins_over_definition():
    """السطر «1- الوزارة: كذا» بند مرقّم لا تعريفًا."""
    assert classify(line("1- الوزارة: وزارة العمل", bold=True), LAW, BODY) == "item"


def test_profile_plain_ignores_law_patterns():
    plain = Options(profile="plain")
    assert classify(line("الباب الأول", BODY + 4), plain, BODY) == "para"
    assert classify(line("1- بند", BODY), plain, BODY) == "item"


# ═══════════ البناء الكامل عبر convert ═══════════

def fake_pages(monkeypatch, lines):
    """يستبدل استخراج الصفحة بأسطر مصطنعة، ويجعل المستند صفحة واحدة."""
    placed = []
    for k, spec in enumerate(lines):
        item = line(*spec) if isinstance(spec, tuple) else line(spec)
        item["y0"] = 100 + k * 20
        item["y1"] = item["y0"] + item["size"]
        placed.append(item)
    monkeypatch.setattr(core, "page_lines",
                        lambda page, st=None, **kw: placed)
    monkeypatch.setattr(structure, "body_font_size", lambda pages: BODY)


def blank_pdf(tmp_path):
    import pymupdf
    doc = pymupdf.open()
    doc.new_page()
    path = str(tmp_path / "blank.pdf")
    doc.save(path)
    doc.close()
    return path


def test_laiha_prefixes_following_madda(tmp_path, monkeypatch):
    """«اللائحة التنفيذية» عنوان يقف وحده — يوسم المادة التي تليه فقط."""
    fake_pages(monkeypatch, [
        ("المادة (1)", BODY, True),
        "نص المادة الأولى هنا",
        ("اللائحة التنفيذية:", BODY, False),
        ("المادة (2)", BODY, True),
        "نص لائحة المادة الثانية",
        ("المادة (3)", BODY, True),
    ])
    md, st = convert(blank_pdf(tmp_path), Options(profile="saudi_law",
                                                  check_ink=False))
    assert "### المادة (1)" in md
    assert "### اللائحة التنفيذية: المادة (2)" in md
    assert "### المادة (3)" in md          # الوسم لا يتعدّى المادة التالية
    assert st["headings"] == 3


def test_laiha_line_itself_not_emitted_as_heading(tmp_path, monkeypatch):
    fake_pages(monkeypatch, [
        ("اللائحة التنفيذية:", BODY, False),
        ("المادة (7)", BODY, True),
    ])
    md, _ = convert(blank_pdf(tmp_path), Options(profile="saudi_law",
                                                 check_ink=False))
    heads = [ln for ln in md.splitlines() if ln.startswith("###")]
    assert heads == ["### اللائحة التنفيذية: المادة (7)"]


def test_bab_resets_laiha_state(tmp_path, monkeypatch):
    """الباب يقطع حالة اللائحة — وإلا وسمت مادة في باب لاحق."""
    fake_pages(monkeypatch, [
        ("اللائحة التنفيذية:", BODY, False),
        ("الباب الثاني", BODY + 4, False),
        ("المادة (9)", BODY, True),
    ])
    md, _ = convert(blank_pdf(tmp_path), Options(profile="saudi_law",
                                                 check_ink=False))
    assert "## الباب الثاني" in md
    assert "### المادة (9)" in md
    assert "اللائحة التنفيذية: المادة (9)" not in md
