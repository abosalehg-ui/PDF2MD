# -*- coding: utf-8 -*-
"""
اختبارات حذف العلامة المائية.

العلامة تُرصد بالشفافية أو بالميل، وكلاهما موجود في rawdict وحده — فتُبنى
هنا كتل rawdict مصطنعة بدل ملف PDF حقيقي، لأن حقن نص مائل شفاف في ملف
يتطلب content stream يدويًا، والقاعدة المُختبَرة هي قراءة القاموس.
"""

from src import core
from tests.test_core import ch


class FakePage:
    def __init__(self, blocks):
        self._blocks = blocks

    def get_text(self, kind):
        assert kind == "rawdict"
        return {"blocks": self._blocks}


def span(text, x0=100.0, alpha=255, size=12.0):
    """جزء أفقي: حروفه متلاصقة تنازليًا (RTL) فتخرج كلمة واحدة."""
    chars = [ch(c, x0 - 4 * k, x1=x0 - 4 * (k - 1)) for k, c in enumerate(text)]
    return {"chars": chars, "size": size, "font": "Test", "flags": 0,
            "alpha": alpha}


def line(spans, dir_=(1.0, 0.0)):
    return {"dir": dir_, "spans": spans}


def page(lines):
    return FakePage([{"type": 0, "lines": lines}])


def text_of(page_, **kw):
    return "\n".join(l["text"] for l in core.build_lines(core.page_units(page_, **kw)))


# ═══════════ الرصد ═══════════

def test_faint_span_dropped():
    """نص باهت = طبقة زخرفية خلف المتن، لا محتوى."""
    p = page([line([span("متن")]), line([span("ختم", alpha=26)])])
    assert text_of(p) == "متن"


def test_tilted_line_dropped():
    """توقيع مائل يعبر أسطر المتن — يُحذف قبل ضمّ الأسطر لا بعده."""
    p = page([line([span("متن")]),
              line([span("توقيع")], dir_=(0.866, -0.5))])
    assert text_of(p) == "متن"


def test_opaque_horizontal_text_kept():
    p = page([line([span("متن")]), line([span("وغيره")])])
    assert "وغيره" in text_of(p)


# ═══════════ الحارس ═══════════

def test_all_tilted_page_keeps_everything():
    """
    صفحة كل أسطرها مائلة = صفحة مائلة نفسها (مسح ضوئي مائل أو صفحة عرضية
    بلا /Rotate)، لا علامة مائية — فلا يُحذف شيء.
    """
    tilt = (0.866, -0.5)
    p = page([line([span("متن")], dir_=tilt),
              line([span("وغيره")], dir_=tilt)])
    out = text_of(p)
    assert "متن" in out and "وغيره" in out


def test_flipped_horizontal_line_is_not_tilted():
    """اتجاه (-1, 0) نص أفقي مقلوب لا مائل — يبقى."""
    p = page([line([span("متن")]), line([span("وغيره")], dir_=(-1.0, 0.0))])
    assert "وغيره" in text_of(p)


# ═══════════ الخيار والإحصاء ═══════════

def test_keep_watermark_option():
    p = page([line([span("متن")]), line([span("ختم", alpha=26)])])
    assert "ختم" in text_of(p, drop_watermark=False)


def test_dropped_parts_counted():
    p = page([line([span("متن")]),
              line([span("ختم", alpha=26)], dir_=(0.866, -0.5))])
    stats = {}
    text_of(p, stats=stats)
    assert stats["watermark"] == 1


def test_no_watermark_leaves_stats_untouched():
    stats = {}
    text_of(page([line([span("متن")])]), stats=stats)
    assert "watermark" not in stats
