# -*- coding: utf-8 -*-
"""
اختبارات جسر واجهة الويب (src/web.py).

الجسر يعمل داخل المتصفح فوق Pyodide، لكنه بايثون خالص بلا استيراد من
جافاسكربت — فيُختبر هنا على CPython. ما يحرسه هذا الملف هو **عقد التبادل**:
ما يصل من الواجهة يُترجَم إلى Options كما يُتوقّع، وما يعود إليها JSON
بالمفاتيح التي تقرؤها، ولا يعبر استثناءٌ حدَّ اللغتين.

وحدة الاختبار الأخرى هي بيان زمن التشغيل web/runtime.json: الواجهة
والسكربت يقرآنه معًا، فحقلٌ ناقص فيه يعطّل الصفحة بلا أن يسقط أي اختبار.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

fitz = pytest.importorskip("pymupdf")

from src import web  # noqa: E402
from src.structure import Options  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ═══════════════ بناء الخيارات ═══════════════

def test_defaults_match_engine_defaults():
    """الصفحة الفارغة يجب أن تعطي خيارات محرّك افتراضية بحذافيرها."""
    built = web.build_options({})
    default = Options()
    for field in vars(default):
        assert getattr(built, field) == getattr(default, field), field


def test_accepts_json_text_and_dict():
    payload = {"profile": "saudi_law", "h_top": 1, "check_ink": False}
    assert web.build_options(payload).profile == "saudi_law"
    assert web.build_options(json.dumps(payload)).h_top == 1
    assert web.build_options(json.dumps(payload)).check_ink is False
    assert web.build_options("").profile == "auto"
    assert web.build_options(None).profile == "auto"


def test_unknown_keys_are_ignored():
    """إعدادات محفوظة من إصدار أقدم يجب ألّا تُسقط التحويل."""
    opt = web.build_options({"profile": "plain", "nonsense": 5, "old_flag": True})
    assert opt.profile == "plain"


@pytest.mark.parametrize("payload", [
    {"profile": "unknown"},
    {"footnotes": "maybe"},
    {"h_top": "كبير"},
    {"para_gap": "واسعة"},
])
def test_bad_values_for_known_keys_raise(payload):
    with pytest.raises(ValueError):
        web.build_options(payload)


def test_numbers_are_clamped_not_trusted():
    """الواجهة تُقيّد الحقول، لكن ما يصل من جافاسكربت مُدخَل لا يُوثق به."""
    opt = web.build_options({"h_top": 400, "h_sub": 0, "para_gap": 99})
    assert opt.h_top == 6
    assert opt.h_sub == 1
    assert opt.para_gap == 5.0


def test_reversed_page_range_is_corrected():
    opt = web.build_options({"page_from": 40, "page_to": 10})
    assert (opt.page_from, opt.page_to) == (10, 40)


def test_title_is_trimmed():
    assert web.build_options({"title": "  نظام العمل  "}).title == "نظام العمل"


# ═══════════════ اسم المخرَج ═══════════════

@pytest.mark.parametrize("given, expected", [
    ("نظام العمل.pdf", "نظام العمل.md"),
    ("/pdf2md/work/job-3.pdf", "job-3.md"),
    (r"C:\Users\a\مذكرة.pdf", "مذكرة.md"),
    ("بلا امتداد", "بلا امتداد.md"),
    ("", "pdf2md.md"),
    (None, "pdf2md.md"),
])
def test_md_name_for(given, expected):
    assert web.md_name_for(given) == expected


# ═══════════════ التحويل والفحص ═══════════════

@pytest.fixture
def pdf(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 90), "Chapter One", fontsize=18, fontname="hebo")
    y = 130
    for i in range(6):
        page.insert_text((72, y), f"{i + 1}. Line number {i + 1} of the body.",
                         fontsize=11, fontname="helv")
        y += 20
    path = tmp_path / "sample.pdf"
    doc.save(str(path))
    doc.close()
    return str(path)


def test_convert_file_returns_json_contract(pdf):
    seen = {"ticks": [], "lines": []}
    raw = web.convert_file(
        pdf,
        {"check_ink": False},
        progress=lambda pct, msg: seen["ticks"].append(pct),
        log=seen["lines"].append,
    )
    assert isinstance(raw, str)
    result = json.loads(raw)

    assert result["ok"] is True
    assert result["cancelled"] is False
    assert result["name"] == "sample.md"
    assert "Line number 1" in result["markdown"]
    assert result["preview"] == result["markdown"]
    assert result["truncated"] is False
    assert result["stats"]["chars"] == len(result["markdown"])
    assert "رباطات" in result["summary"]
    assert seen["ticks"] and seen["lines"]


def test_convert_file_uses_display_name_not_work_path(pdf, tmp_path):
    """
    الواجهة تكتب الملف باسم محايد في نظام ملفات المتصفح، فاشتقاق اسم
    المخرَج من المسار كان يسلّم «مذكرة.pdf» باسم «job-2.md».
    """
    staged = tmp_path / "job-2.pdf"
    os.replace(pdf, staged)
    result = json.loads(web.convert_file(str(staged), {"check_ink": False},
                                         name="مذكرة اعتراضية.pdf"))
    assert result["name"] == "مذكرة اعتراضية.md"


def test_preview_is_capped_but_markdown_is_whole(pdf, monkeypatch):
    monkeypatch.setattr(web, "PREVIEW_LIMIT", 40)
    result = json.loads(web.convert_file(pdf, {"check_ink": False}))
    assert result["truncated"] is True
    assert len(result["preview"]) == 40
    assert len(result["markdown"]) > 40


def test_missing_file_returns_error_not_exception():
    result = json.loads(web.convert_file("/pdf2md/work/ghost.pdf"))
    assert result["ok"] is False
    assert result["cancelled"] is False
    assert result["error"]
    assert "Traceback" in result["trace"]


def test_bad_option_returns_error_not_exception(pdf):
    result = json.loads(web.convert_file(pdf, {"profile": "unknown"}))
    assert result["ok"] is False
    assert "unknown" in result["error"]


def test_diagnose_file_adds_a_verdict(pdf):
    result = json.loads(web.diagnose_file(pdf, name="sample.pdf"))
    assert result["ok"] is True
    assert result["name"] == "sample.pdf"
    assert result["pages"] == 1
    assert result["has_text"] is True
    assert len(result["rows"]) == 8
    assert result["healthy"] is True
    assert result["verdict"]
    # pairs تصل قائمةَ tuple من المحرّك، والواجهة تقرؤها بالاسم لا بالموضع
    assert all(set(p) == {"pair", "count"} for p in result["pairs"])


def test_diagnose_missing_file_returns_error():
    result = json.loads(web.diagnose_file("/pdf2md/work/ghost.pdf"))
    assert result["ok"] is False
    assert result["error"]


def test_about_reports_engine_versions():
    card = json.loads(web.about())
    assert card["version"] == web.__version__
    assert card["pymupdf"]
    assert card["python"]


# ═══════════════ بيان زمن التشغيل وأصول الصفحة ═══════════════

def _manifest():
    with open(os.path.join(ROOT, "web", "runtime.json"), encoding="utf-8") as f:
        return json.load(f)


def test_runtime_manifest_is_complete():
    manifest = _manifest()
    assert manifest["pyodide"]
    assert manifest["core"]["url"].endswith(".tar.bz2")
    assert len(manifest["core"]["sha256"]) == 64
    assert {w["name"] for w in manifest["wheels"]} == {"numpy", "pymupdf"}
    for wheel in manifest["wheels"]:
        assert wheel["url"].endswith(wheel["file"])
        assert len(wheel["sha256"]) == 64


def test_manifest_lists_every_engine_source():
    """
    الخيط العامل ينسخ هذه الملفات وحدها إلى المتصفّح. وحدة جديدة في src
    تُستورَد من structure.py ولا تُذكر هنا تُسقط الصفحة بـImportError عند
    الإقلاع — والصفحة لا تُختبر في CI، فهذا الاختبار هو حارسها.
    """
    listed = set(_manifest()["sources"])
    on_disk = {f for f in os.listdir(os.path.join(ROOT, "src"))
               if f.endswith(".py")}
    # gui.py وحده يبقى خارج المتصفّح: PyQt6 لا يعمل على Pyodide
    assert listed == on_disk - {"gui.py", "cli.py"}


def test_page_references_existing_assets():
    with open(os.path.join(ROOT, "index.html"), encoding="utf-8") as f:
        page = f.read()
    for asset in ("web/css/styles.css", "web/js/app.js"):
        assert asset in page
        assert os.path.exists(os.path.join(ROOT, asset))


def test_page_option_ids_cover_every_engine_option():
    """
    كل خيار في Options له عنصر في الصفحة. الخيار الذي يُضاف إلى المحرّك
    ولا يُعرض في الواجهة يبقى على قيمته الافتراضية أبدًا بلا أن يلاحظ أحد.
    """
    with open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8") as f:
        app = f.read()
    for field in vars(Options()):
        assert f"  {field}: {{ el: " in app, f"الخيار {field} غير معروض"
