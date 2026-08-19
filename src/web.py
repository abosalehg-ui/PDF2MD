# -*- coding: utf-8 -*-
"""
web.py — جسر واجهة الويب في PDF2MD.

الواجهة الثالثة بعد cli.py و gui.py. تعمل داخل المتصفح فوق Pyodide، حيث
يُشغَّل هذا الملف نفسه — وكل ما تحته من محرّك — بلا أي تعديل. الملف يبقى
بايثون خالصًا بلا استيراد من جافاسكربت، فيُختبر على CPython مثل بقيته
(انظر tests/test_web.py) وتُحرَس الواجهة الثالثة بالاختبار كما تُحرَس
الأولى والثانية.

عقد التبادل مع جافاسكربت: كل دالّة عامة هنا ترجّع **نصًّا** بصيغة JSON.
سبب ذلك أن Pyodide يغلّف dict البايثوني في وسيط (proxy) يجب تحريره يدويًا
وإلا تسرّبت الذاكرة، ويترجم مفاتيحه ترجمة غير حرفية. النص لا وسيط له.
"""

import json
import os
import traceback

from .common import stats_summary, verdict_of
from .core import __version__
from .structure import ConversionCancelled, Options, convert, diagnose

# مجلد العمل داخل نظام ملفات المتصفح (MEMFS). جافاسكربت يكتب ملف PDF فيه
# ثم يمرّر مساره — أرخص من تمرير البايتات عبر حدود اللغتين مرتين.
WORK_DIR = "/pdf2md"

PROFILES = ("auto", "saudi_law", "plain")
FOOTNOTES = ("quote", "inline", "drop")

# حدود القيم العددية. الواجهة تُقيّدها في عناصر HTML أصلًا، لكن ما يصل من
# جافاسكربت مُدخَل لا يُوثق به: عنصر HTML مُعدَّل من أدوات المطوّر أو
# إعدادات محفوظة من إصدار أقدم تصل إلى هنا كما هي. `--h-top 400` كان
# يُنتج عنوانًا بأربعمئة #، والحدّ هنا يمنعه في الويب كما يمنعه argparse
# في سطر الأوامر.
LIMITS = {
    "h_top": (1, 6),
    "h_sub": (1, 6),
    "page_from": (0, 1_000_000),
    "page_to": (0, 1_000_000),
}
PARA_GAP = (0.1, 5.0)

BOOL_FIELDS = (
    "fix_ligatures", "check_ink", "unify_digits", "drop_headers",
    "drop_watermark", "drop_toc", "build_toc", "tables",
)

# سقف طول المعاينة المُعادة إلى الواجهة. مطابق لسقف واجهة سطح المكتب
# (PREVIEW_LIMIT في gui.py) وللسبب نفسه: كتاب من ٩٠٠ صفحة يُنتج ملفًا
# بملايين الحروف، ورسمه في عنصر HTML واحد يجمّد اللسان. التنزيل يأخذ
# الناتج كاملًا — المقصوص هو المعروض وحده.
PREVIEW_LIMIT = 200_000


def _int(value, key):
    lo, hi = LIMITS[key]
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"قيمة غير عددية للحقل {key}: {value!r}") from None
    return max(lo, min(hi, n))


def _float(value):
    try:
        x = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"قيمة غير عددية لفجوة الفقرة: {value!r}") from None
    lo, hi = PARA_GAP
    return max(lo, min(hi, x))


def _choice(value, allowed, key, default):
    if value is None:
        return default
    text = str(value)
    if text not in allowed:
        raise ValueError(f"قيمة غير معروفة للحقل {key}: {text!r}")
    return text


def build_options(raw=None):
    """
    يبني Options من dict أو نص JSON قادم من الواجهة.

    المفاتيح المجهولة تُتجاهَل بصمت — إعدادات محفوظة في متصفّح المستخدم من
    إصدار أقدم يجب ألّا تُسقط التحويل. أما القيم الفاسدة لمفتاح **معروف**
    فتُرفع خطأً: تجاهلها يعني تحويلًا بإعدادات غير التي طلبها المستخدم وهو
    لا يدري.
    """
    if isinstance(raw, str):
        raw = json.loads(raw) if raw.strip() else {}
    data = dict(raw or {})

    opt = Options()
    opt.profile = _choice(data.get("profile"), PROFILES, "profile", opt.profile)
    opt.footnotes = _choice(data.get("footnotes"), FOOTNOTES, "footnotes",
                            opt.footnotes)
    for field in BOOL_FIELDS:
        if field in data:
            setattr(opt, field, bool(data[field]))
    for field in ("h_top", "h_sub", "page_from", "page_to"):
        if field in data:
            setattr(opt, field, _int(data[field], field))
    if "para_gap" in data:
        opt.para_gap = _float(data["para_gap"])
    if "title" in data:
        opt.title = str(data["title"] or "").strip()

    # الترتيب المقلوب يُصحَّح هنا لا في المحرّك: `_page_range` يقبله ويحوّل
    # حتى نهاية الملف بعد تحذير، وهو سلوك سطر الأوامر. لكن الواجهة تعرض
    # حقلي «من» و«إلى» جنبًا إلى جنب، ومن يقلبهما يقصد المدى بينهما.
    if opt.page_from and opt.page_to and opt.page_to < opt.page_from:
        opt.page_from, opt.page_to = opt.page_to, opt.page_from
    return opt


def md_name_for(pdf_name):
    """اسم ملف الناتج من اسم ملف الدخل — بلا أي مسار."""
    base = os.path.basename(str(pdf_name or "").replace("\\", "/"))
    stem = os.path.splitext(base)[0].strip() or "pdf2md"
    return stem + ".md"


def _fail(exc):
    return json.dumps({
        "ok": False,
        "cancelled": False,
        "error": str(exc) or exc.__class__.__name__,
        "trace": traceback.format_exc(),
    }, ensure_ascii=False)


def _cancelled(exc):
    return json.dumps({"ok": False, "cancelled": True, "error": str(exc)},
                      ensure_ascii=False)


def convert_file(path, options=None, progress=None, log=None, name=None):
    """
    يحوّل ملفًا واحدًا ويرجّع نص JSON.

    عند النجاح: {ok, markdown, preview, truncated, stats, summary, name}
    عند الفشل : {ok:false, cancelled, error, trace}

    `name` اسم الملف كما يعرفه المستخدم، و`path` موضعه في نظام ملفات
    المتصفح. الاثنان مختلفان عمدًا: الواجهة تكتب الملف باسم محايد لأن
    أسماء المستخدمين تحمل حروفًا ومسارات لا يقبلها ذلك النظام. اشتقاق اسم
    المخرَج من `path` كان يسلّم «مذكرة.pdf» باسم «job-2.md».

    الاستثناء لا يعبر حدّ اللغتين: Pyodide يترجمه إلى خطأ جافاسكربت يحمل
    أثر بايثون خامًا في نصّه، فيصل المستخدم العربي traceback بالإنجليزية
    بدل رسالة مفهومة. نمسكه هنا ونعيده بيانات.
    """
    try:
        opt = build_options(options)
        markdown, stats = convert(path, opt, progress=progress, log=log)
    except ConversionCancelled as exc:
        return _cancelled(exc)
    except Exception as exc:  # noqa: BLE001 — الحدّ مع جافاسكربت
        return _fail(exc)

    return json.dumps({
        "ok": True,
        "cancelled": False,
        "name": md_name_for(name or path),
        "markdown": markdown,
        "preview": markdown[:PREVIEW_LIMIT],
        "truncated": len(markdown) > PREVIEW_LIMIT,
        "stats": stats,
        "summary": stats_summary(stats),
    }, ensure_ascii=False)


def diagnose_file(path, progress=None, name=None):
    """
    فحص تشخيصي على عيّنة صفحات — يرجّع نص JSON.

    يُضاف إلى مخرَج diagnose حكمٌ جاهز للعرض (verdict/healthy) محسوبٌ بدالّة
    common.verdict_of نفسها التي تستعملها الواجهتان الأخريان، فلا يختلف
    الحكم على الملف باختلاف الواجهة التي فُحص منها.
    """
    try:
        data = diagnose(path, progress=progress)
    except ConversionCancelled as exc:
        return _cancelled(exc)
    except Exception as exc:  # noqa: BLE001 — الحدّ مع جافاسكربت
        return _fail(exc)

    verdict, healthy = verdict_of(data["rows"])
    if not data["has_text"]:
        verdict = ("الملف مصوّر بلا طبقة نص — يحتاج OCR قبل التحويل."
                   if data["needs_ocr"] else "لا توجد طبقة نص في هذا الملف.")
        healthy = False

    # pairs يصل من diagnose قائمةَ tuple، وJSON يحوّلها قوائم من عنصرين.
    # نجعلها dict صريحة لأن الواجهة تقرؤها بالاسم لا بالموضع.
    data["pairs"] = [{"pair": k, "count": v} for k, v in data["pairs"]]
    data["verdict"] = verdict
    data["healthy"] = healthy
    data["ok"] = True
    data["cancelled"] = False
    data["name"] = os.path.basename(str(name or path))
    return json.dumps(data, ensure_ascii=False)


def about():
    """بطاقة تعريف تُعرض في الواجهة بعد اكتمال الإقلاع."""
    import platform
    import sys

    try:
        import pymupdf
    except ImportError:                     # PyMuPDF < 1.24.3
        import fitz as pymupdf

    return json.dumps({
        "version": __version__,
        "python": platform.python_version(),
        "pymupdf": getattr(pymupdf, "VersionBind", "?"),
        "platform": sys.platform,
    }, ensure_ascii=False)
