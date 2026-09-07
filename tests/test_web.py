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
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

fitz = pytest.importorskip("pymupdf")

from src import web  # noqa: E402
from src.structure import LIMITS, Options  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ═══════════════ بناء الخيارات ═══════════════

def test_defaults_match_engine_defaults():
    """الصفحة الفارغة يجب أن تعطي خيارات محرّك افتراضية بحذافيرها."""
    built = web.build_options({})
    default = Options()
    # `ocr` وحده يخالف عمدًا: لا Tesseract في Pyodide، فالمتصفّح يعطّله
    # صراحةً بدل حساب حكمٍ لا يُنفَّذ — انظر test_browser_never_asks_for_ocr.
    for field in vars(default):
        if field == "ocr":
            continue
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


def test_every_boolean_option_is_accepted_by_the_bridge():
    """
    نظير `test_every_boolean_option_has_a_checkbox` في الواجهة الرسومية.

    بناء Options مكرر في ثلاث واجهات، وكان الحارس موجودًا للثانية وغائبًا
    عن الثالثة — فخيار منطقي جديد يصل إلى سطر الأوامر وسطح المكتب ويغيب
    عن المتصفّح بصمت، بلا شيء يمسك النسيان.
    """
    boolean_fields = {name for name, field in Options.__dataclass_fields__.items()
                      if field.type in ("bool", bool)}
    assert boolean_fields, "لم يُقرأ أي حقل منطقي — تغيّر شكل dataclass"
    assert boolean_fields == set(web.BOOL_FIELDS)


def test_every_bridge_field_maps_to_a_real_option():
    """والعكس: حقل لا يقابله شيء في Options يعني إعدادًا يُرسَل ويُهمَل."""
    for field in web.BOOL_FIELDS:
        assert field in Options.__dataclass_fields__


def test_browser_never_asks_for_ocr():
    """
    لا Tesseract داخل Pyodide، فحكم الـOCR في المتصفّح حسابٌ لا يُنفَّذ
    قراره: كان يفحص كل صفحة ثلاثة فحوص ثم يحذّر بما لا حيلة للمستخدم فيه.
    """
    assert web.build_options({}).ocr == "never"
    assert web.build_options({"ocr": "always"}).ocr == "never"


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
    # وحدات `gui*` تبقى خارج المتصفّح: PyQt6 لا يعمل على Pyodide. و`cli.py`
    # كذلك: لا سطر أوامر في لسان متصفّح. وما عداهما يُنسَخ كما هو.
    desktop_only = {f for f in on_disk if f.startswith("gui")} | {"cli.py"}
    assert listed == on_disk - desktop_only


def test_page_references_existing_assets():
    with open(os.path.join(ROOT, "index.html"), encoding="utf-8") as f:
        page = f.read()
    for asset in ("web/css/styles.css", "web/js/app.js"):
        assert asset in page
        assert os.path.exists(os.path.join(ROOT, asset))


def test_vercel_config_matches_the_build_script():
    """
    Vercel يقرأ vercel.json وحده. وهو ملف صامت العطب: مجلد مخرَج خاطئ
    يُنتج نشرًا «ناجحًا» لموقع فارغ، ومفتاح مجهول واحد يُسقط البناء بلا
    سجلّات أصلًا (schema فيه additionalProperties: false). فيُربط هنا
    بمصدره الحقيقي: tools/build_site.py.

    و framework يجب أن يبقى null: بدونه يرى Vercel ملفَّ main.py في الجذر
    فيظنّ المشروع تطبيق بايثون ويبحث فيه عن متغيّر app.
    """
    with open(os.path.join(ROOT, "vercel.json"), encoding="utf-8") as f:
        cfg = json.load(f)

    assert cfg["framework"] is None
    assert cfg["outputDirectory"] == "_site"

    script = os.path.join("tools", "build_site.py")
    assert script.replace(os.sep, "/") in cfg["buildCommand"]
    assert os.path.isfile(os.path.join(ROOT, script))

    # مجلد المخرَج في السكربت هو مصدر الحقيقة — لا نسخة ثانية في JSON
    with open(os.path.join(ROOT, script), encoding="utf-8") as f:
        build = f.read()
    assert f'"{cfg["outputDirectory"]}"' in build

    # مفتاح واحد مجهول يُسقط البناء بلا سجلّ — فلا يُقبل إلا المعروف
    allowed = {"$schema", "framework", "installCommand", "buildCommand",
               "outputDirectory", "headers"}
    assert set(cfg) <= allowed, f"مفاتيح غير متوقّعة: {set(cfg) - allowed}"


def test_vercel_sends_the_headers_the_meta_tag_cannot():
    """
    `frame-ancestors` تتجاهلها المواصفة حين تُسلَّم بوسم meta، فالصفحة
    قابلة للتأطير رغم سياسة أمن المحتوى في رأسها — وهي صفحة تُفلَت فيها
    وثائق قد تكون سرّية. وVercel المنصّة الوحيدة من المنصّتين التي تستطيع
    إرسال ترويسات حقيقية، فما يمكن إصلاحه فيها يُصلَح.
    """
    with open(os.path.join(ROOT, "vercel.json"), encoding="utf-8") as f:
        cfg = json.load(f)

    rules = cfg.get("headers") or []
    assert rules, "لا ترويسات في vercel.json"
    sent = {h["key"]: h["value"] for rule in rules for h in rule["headers"]}

    assert "frame-ancestors 'none'" in sent.get("Content-Security-Policy", "")
    assert sent.get("X-Content-Type-Options") == "nosniff"
    assert sent.get("Referrer-Policy") == "no-referrer"
    # COOP/COEP تفتحان باب SharedArrayBuffer، أي إيقافًا يقاطع بايثون بدل
    # قتل الخيط وإعادة إقلاعه — وهو القيد الذي يشرحه worker.js
    assert sent.get("Cross-Origin-Opener-Policy") == "same-origin"
    assert sent.get("Cross-Origin-Embedder-Policy") == "require-corp"


def test_page_option_ids_cover_every_engine_option():
    """
    كل خيار في Options له عنصر في الصفحة. الخيار الذي يُضاف إلى المحرّك
    ولا يُعرض في الواجهة يبقى على قيمته الافتراضية أبدًا بلا أن يلاحظ أحد.

    خيارات الـOCR وحدها مستثناة: تشغيلها يحتاج ثنائي Tesseract، ولا وجود
    له داخل Pyodide. عرضها في المتصفّح يعد بما لا يُنفَّذ، فتبقى خارج
    الصفحة كما بقيت gui.py وcli.py خارج بيان المصادر.
    """
    with open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8") as f:
        app = f.read()
    for field in vars(Options()):
        if field.startswith("ocr"):
            continue
        assert f"  {field}: {{ el: " in app, f"الخيار {field} غير معروض"


# ═══════════════ حدود القيم: مصدر واحد للواجهات الثلاث ═══════════════

def _page_html():
    with open(os.path.join(ROOT, "index.html"), encoding="utf-8") as f:
        return f.read()


def _input_attrs(html, element_id):
    """سمات عنصر <input> واحد من الصفحة، بمفاتيحها كما هي."""
    start = html.index(f'id="{element_id}"')
    chunk = html[html.rindex("<input", 0, start):html.index(">", start) + 1]
    return dict(re.findall(r'(\w+)="([^"]*)"', chunk))


@pytest.mark.parametrize("element_id, key", [
    ("optHTop", "h_top"),
    ("optHSub", "h_sub"),
    ("optGap", "para_gap"),
])
def test_page_inputs_match_the_shared_limits(element_id, key):
    """
    الانحدار: كل واجهة كانت تحمل حدودها. مستوى العنوان الرئيسي كان ١..٥
    في الواجهة الرسومية و١..٦ هنا وفي سطر الأوامر، وفجوة الفقرة
    ٠٫٢٠..٣٫٠٠ هناك و٠٫١..٥٫٠ هنا وبلا حدّ في سطر الأوامر — فالقيمة
    المقبولة في واجهة تُرفض في أخرى بلا سبب مفهوم للمستخدم.
    """
    lo, hi = LIMITS[key]
    attrs = _input_attrs(_page_html(), element_id)
    assert float(attrs["min"]) == pytest.approx(lo)
    assert float(attrs["max"]) == pytest.approx(hi)


def test_web_reads_para_gap_bounds_from_the_engine():
    """`web.PARA_GAP` مشتقّ لا منسوخ."""
    assert web.PARA_GAP == LIMITS["para_gap"]


# ═══════════════ سقف المعاينة يُعلَن للواجهة ═══════════════

def test_convert_file_reports_the_preview_limit(pdf):
    """
    الانحدار: نصّ «أول ٢٠٠ ألف حرف» كان محفورًا في app.js، فتغيير السقف
    هنا يجعل الرسالة تكذب على المستخدم بلا أن يُخطئ شيء.
    """
    data = json.loads(web.convert_file(pdf))
    assert data["preview_limit"] == web.PREVIEW_LIMIT


def test_page_message_builds_the_limit_from_the_engine():
    """الواجهة تبني الرقم من الحقل المُعاد لا من ثابت مكتوب فيها."""
    with open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8") as f:
        app = f.read()
    assert "result.preview_limit" in app
    assert "٢٠٠ ألف" not in app


# ═══════════════ سياسة أمن المحتوى ═══════════════

def test_worker_source_is_not_widened_to_blob():
    """
    `worker-src 'self' blob:` كان يسمح بخيط من عنوان blob بلا حاجة: الخيط
    يُحمَّل من web/js/worker.js نفسه. جُرّب الإقلاع كاملًا في Chromium بعد
    التضييق — Pyodide و numpy و PyMuPDF تُحمَّل والواجهة تظهر بلا مخالفة.
    """
    policy = re.search(r'http-equiv="Content-Security-Policy"\s+content="([^"]+)"',
                       _page_html())
    assert policy, "وسم سياسة أمن المحتوى غير موجود"
    assert "worker-src 'self';" in policy.group(1)
    assert "blob:" not in policy.group(1)
