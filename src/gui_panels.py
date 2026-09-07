# -*- coding: utf-8 -*-
"""
gui_panels.py — لوحات مستقلة داخل نافذة PDF2MD.

كانت `MainWindow` تحمل ستّ مسؤوليات في ملف واحد قارب الألف سطر: بناء كل
عنصر تحكم، وخريطة الخيارات، ودورة الإعدادات، وعرض التشخيص، وإدارة الطابور،
والحوارات. اللوحتان هنا تأخذان أولى الأربع، فتبقى النافذة للتنسيق وحده.

والمكسب ليس القياس فحسب: `OptionsPanel` لوحة قائمة بذاتها تُبنى وتُختبر بلا
نافذة ولا طابور ولا خيوط — وهي التي تحمل الخريطة بين عناصر التحكم و`Options`،
أي أخطر ما في الواجهة على صحّة الناتج.
"""

import html

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import ocr as ocr_engine
from .common import verdict_of
from .gui_theme import BAD, OK
from .structure import LIMITS, Options

PROFILES = [
    ("تلقائي — كشف العناوين بحجم الخط", "auto"),
    ("نظام/لائحة سعودية — الباب والفصل والمادة", "saudi_law"),
    ("نص عادي — فقرات بلا عناوين", "plain"),
]
OCR_MODES = [
    ("تلقائي — الصفحة المعطوبة أو الممسوحة وحدها", "auto"),
    ("بلا OCR — طبقة النص الأصلية دائمًا", "never"),
    ("دائمًا — كل الصفحات (بطيء)", "always"),
]
# الخياران الأولان يضعان الحاشية في الموضع نفسه — نهاية القسم — ويفترقان
# في علامة الاقتباس وحدها. وكان الثاني يُسمّى «ضمن النص» فيوهم بإدراجها في
# موضع إشارتها من الفقرة، وهو ما لا يفعله المحرّك في أي وضع.
FOOTNOTES = [
    ("في نهاية القسم — اقتباس  >", "quote"),
    ("في نهاية القسم — بلا اقتباس", "inline"),
    ("حذف", "drop"),
]


class OptionsPanel(QGroupBox):
    """
    كل خيارات التحويل معروضةً، مع خريطتها إلى `Options` ودورة حفظها.

    اللوحة لا تعرف شيئًا عن الملفات ولا الخيوط ولا النافذة، فتُبنى في اختبار
    بسطر واحد ويُقارَن `options()` بحالة عناصرها.
    """

    def __init__(self, parent=None):
        super().__init__("الخيارات", parent)
        self._build()

    # ---------- البناء ----------

    def _build(self):
        gl = QGridLayout(self)
        gl.setVerticalSpacing(8)
        r = 0

        # setBuddy يربط اللصيقة بحقلها برمجيًا لا بصريًا فقط — بدونه يعلن
        # قارئ الشاشة «صندوق تحرير» بلا اسم، لأن الشبكة تجاور ولا تربط.
        def labelled(text, widget, row):
            lab = QLabel(text)
            lab.setBuddy(widget)
            widget.setAccessibleName(text)
            gl.addWidget(lab, row, 0)
            return lab

        self.cb_profile = QComboBox()
        self.cb_profile.addItems([lbl for lbl, _ in PROFILES])
        labelled("نمط المستند", self.cb_profile, r)
        gl.addWidget(self.cb_profile, r, 1)
        r += 1

        self.ed_title = QLineEdit()
        self.ed_title.setPlaceholderText("اتركه فارغًا لبلا عنوان")
        labelled("العنوان الرئيسي", self.ed_title, r)
        gl.addWidget(self.ed_title, r, 1)
        r += 1

        self.cb_foot = QComboBox()
        self.cb_foot.addItems([lbl for lbl, _ in FOOTNOTES])
        labelled("الحواشي", self.cb_foot, r)
        gl.addWidget(self.cb_foot, r, 1)
        r += 1

        gl.addWidget(QLabel("مستوى العناوين"), r, 0)
        hr = QHBoxLayout()
        self.sp_top = QSpinBox()
        self.sp_top.setRange(*LIMITS["h_top"])
        self.sp_top.setValue(2)
        self.sp_top.setAccessibleName("مستوى العنوان الرئيسي")
        self.sp_sub = QSpinBox()
        self.sp_sub.setRange(*LIMITS["h_sub"])
        self.sp_sub.setValue(3)
        self.sp_sub.setAccessibleName("مستوى العنوان الفرعي")
        lab_top, lab_sub = QLabel("رئيسي"), QLabel("فرعي")
        lab_top.setBuddy(self.sp_top)
        lab_sub.setBuddy(self.sp_sub)
        hr.addWidget(lab_top)
        hr.addWidget(self.sp_top)
        hr.addWidget(lab_sub)
        hr.addWidget(self.sp_sub)
        hr.addStretch()
        gl.addLayout(hr, r, 1)
        r += 1

        gl.addWidget(QLabel("نطاق الصفحات"), r, 0)
        hr2 = QHBoxLayout()
        self.sp_from = QSpinBox()
        self.sp_from.setRange(*LIMITS["page_from"])
        self.sp_from.setAccessibleName("أول صفحة")
        self.sp_to = QSpinBox()
        self.sp_to.setRange(*LIMITS["page_to"])
        self.sp_to.setAccessibleName("آخر صفحة")
        lab_from, lab_to = QLabel("من"), QLabel("إلى")
        lab_from.setBuddy(self.sp_from)
        lab_to.setBuddy(self.sp_to)
        hr2.addWidget(lab_from)
        hr2.addWidget(self.sp_from)
        hr2.addWidget(lab_to)
        hr2.addWidget(self.sp_to)
        # الرقم بالصيغة نفسها التي يعرضها QSpinBox بجانبه — لا هندي مقابل غربي
        hr2.addWidget(QLabel("(0 = الكل)"))
        hr2.addStretch()
        gl.addLayout(hr2, r, 1)
        r += 1

        gl.addWidget(QLabel("فجوة الفقرة"), r, 0)
        hr3 = QHBoxLayout()
        self.sp_gap = QDoubleSpinBox()
        self.sp_gap.setRange(*LIMITS["para_gap"])
        self.sp_gap.setSingleStep(0.05)
        self.sp_gap.setDecimals(2)
        self.sp_gap.setValue(0.75)
        self.sp_gap.setToolTip(
            "فجوة رأسية أكبر من (القيمة × ارتفاع السطر) تبدأ فقرة جديدة")
        self.sp_gap.setAccessibleName("فجوة الفقرة")
        hr3.addWidget(self.sp_gap)
        hr3.addWidget(QLabel("× ارتفاع السطر"))
        hr3.addStretch()
        gl.addLayout(hr3, r, 1)
        r += 1

        self.cb_ocr = QComboBox()
        self.cb_ocr.addItems([name for name, _ in OCR_MODES])
        gl.addWidget(QLabel("قراءة ضوئية (OCR)"), r, 0)
        gl.addWidget(self.cb_ocr, r, 1)
        r += 1
        if not ocr_engine.available():
            self.cb_ocr.setEnabled(False)
            note = QLabel("Tesseract غير مثبَّت — الصفحات الممسوحة ضوئيًا "
                          "والملفات ذات خريطة الخط المكسورة ستخرج ناقصة.")
            note.setWordWrap(True)
            gl.addWidget(note, r, 0, 1, 2)
            r += 1

        self.ck_lig = QCheckBox("إصلاح الرباطات المقلوبة")
        self.ck_ink = QCheckBox("فحص الحبر — أدق، أبطأ ٣×")
        self.ck_dig = QCheckBox("توحيد الأرقام الهندية ← عربية")
        self.ck_hdr = QCheckBox("حذف الترويسة والتذييل المتكررة")
        self.ck_wmk = QCheckBox("حذف العلامة المائية — نص مائل أو باهت")
        self.ck_toc = QCheckBox("تخطّي صفحات الفهرس الأصلية")
        self.ck_gen = QCheckBox("توليد فهرس تلقائي بروابط داخلية")
        self.ck_tbl = QCheckBox("بناء جداول Markdown من صفوف الجداول")
        for c in (self.ck_lig, self.ck_ink, self.ck_dig, self.ck_hdr,
                  self.ck_wmk, self.ck_toc, self.ck_gen, self.ck_tbl):
            c.setChecked(True)
            gl.addWidget(c, r, 0, 1, 2)
            r += 1

    # ---------- الخريطة إلى Options ----------

    def checkboxes(self):
        """اسم الحقل في Options ← مربّع الاختيار المقابل له."""
        return {"fix_ligatures": self.ck_lig, "check_ink": self.ck_ink,
                "unify_digits": self.ck_dig, "drop_headers": self.ck_hdr,
                "drop_watermark": self.ck_wmk, "drop_toc": self.ck_toc,
                "build_toc": self.ck_gen, "tables": self.ck_tbl}

    def page_range(self):
        """(من، إلى) كما ضبطهما المستخدم — تفحصهما النافذة قبل بدء الدفعة."""
        return self.sp_from.value(), self.sp_to.value()

    def options(self):
        return Options(
            profile=PROFILES[self.cb_profile.currentIndex()][1],
            fix_ligatures=self.ck_lig.isChecked(),
            check_ink=self.ck_ink.isChecked(),
            unify_digits=self.ck_dig.isChecked(),
            drop_headers=self.ck_hdr.isChecked(),
            drop_watermark=self.ck_wmk.isChecked(),
            drop_toc=self.ck_toc.isChecked(),
            footnotes=FOOTNOTES[self.cb_foot.currentIndex()][1],
            build_toc=self.ck_gen.isChecked(),
            tables=self.ck_tbl.isChecked(),
            title=self.ed_title.text().strip(),
            page_from=self.sp_from.value(),
            page_to=self.sp_to.value(),
            h_top=self.sp_top.value(),
            h_sub=self.sp_sub.value(),
            para_gap=self.sp_gap.value(),
            # القائمة معطَّلة حين لا يوجد Tesseract، فتبقى على "تلقائي"
            # ويتكفّل المحرّك بالتحذير مرة واحدة في سجلّ التحويل.
            ocr=OCR_MODES[self.cb_ocr.currentIndex()][1],
        )

    # ---------- الإعدادات ----------

    @staticmethod
    def _num(settings, key, default, cast=int):
        """
        يقرأ قيمة رقمية من الإعدادات، ويسقط إلى الافتراضي عند أي تلف.

        `int(s.value(...))` المكشوف كان يرمي ValueError داخل __init__ عند
        قيمة غير رقمية (تحرير يدوي لملف الإعدادات، أو ترقية، أو تلف)،
        فلا يُقلع التطبيق أصلًا ولا يعرف المستخدم سببًا ولا مخرجًا.
        """
        try:
            return cast(settings.value(key, default))
        except (TypeError, ValueError):
            return default

    def load(self, settings):
        """يستعيد اختيارات آخر جلسة — بدونها يُعاد ضبط كل شيء كل تشغيل."""
        self.cb_profile.setCurrentIndex(self._num(settings, "profile", 0))
        self.cb_foot.setCurrentIndex(self._num(settings, "footnotes", 0))
        self.cb_ocr.setCurrentIndex(self._num(settings, "ocr", 0))
        self.sp_top.setValue(self._num(settings, "h_top", 2))
        self.sp_sub.setValue(self._num(settings, "h_sub", 3))
        self.sp_gap.setValue(self._num(settings, "para_gap", 0.75, float))
        for key, box in self.checkboxes().items():
            box.setChecked(settings.value(key, True, type=bool))

    def save(self, settings):
        settings.setValue("profile", self.cb_profile.currentIndex())
        settings.setValue("footnotes", self.cb_foot.currentIndex())
        settings.setValue("ocr", self.cb_ocr.currentIndex())
        settings.setValue("h_top", self.sp_top.value())
        settings.setValue("h_sub", self.sp_sub.value())
        settings.setValue("para_gap", self.sp_gap.value())
        for key, box in self.checkboxes().items():
            settings.setValue(key, box.isChecked())


class DiagnosticsView(QWidget):
    """تبويب التشخيص: بطاقة الملف، وجدول قبل/بعد، وعيّنة من النص المُصلَح."""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)

        self.info = QLabel("شغّل «فحص تشخيصي» لمعرفة حالة الملف قبل التحويل.")
        self.info.setWordWrap(True)
        self.info.setTextFormat(Qt.TextFormat.RichText)
        v.addWidget(self.info)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["الكلمة", "سليمة قبل", "تالفة قبل", "سليمة بعد", "تالفة بعد"])
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setMaximumHeight(260)
        v.addWidget(self.table)

        v.addWidget(QLabel("عيّنة من النص بعد الإصلاح:"))
        self.sample = QPlainTextEdit()
        self.sample.setReadOnly(True)
        self.sample.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        v.addWidget(self.sample, 1)

    def show_result(self, d):
        """يعرض مخرَج `structure.diagnose` ويرجّع نصّ الحكم للسجلّ."""
        if not d["has_text"]:
            verdict = ("الملف مصوّر بلا طبقة نص — يحتاج OCR قبل التحويل."
                       if d["needs_ocr"] else "لا توجد طبقة نص في هذا الملف.")
            color = BAD
        else:
            verdict, ok = verdict_of(d["rows"])
            color = OK if ok else BAD

        # بيانات PDF الوصفية والأزواج نص خارجي غير موثوق داخل RichText
        pairs = html.escape(
            "، ".join(f"{k}×{v}" for k, v in d["pairs"]) or "—")
        self.info.setText(
            f"<b>الصفحات:</b> {d['pages']} &nbsp;|&nbsp; "
            f"<b>العيّنة:</b> {d['sampled']} صفحة &nbsp;|&nbsp; "
            f"<b>الخطوط:</b> {d['fonts']} &nbsp;|&nbsp; "
            f"<b>طبقة نص:</b> {'نعم' if d['has_text'] else 'لا — يحتاج OCR'}<br>"
            f"<b>المنتج:</b> {html.escape(d['producer'] or '—')} &nbsp;|&nbsp; "
            f"<b>المُنشئ:</b> {html.escape(d['creator'] or '—')}<br>"
            f"<b>رباطات مُصلَحة في العيّنة:</b> {d['ligatures']:,} ({pairs})<br>"
            f"<b style='color:{color}'>{verdict}</b>"
        )

        self.table.setRowCount(len(d["rows"]))
        for i, r in enumerate(d["rows"]):
            # عمودا النتيجة يحملان رمزًا مع اللون — لا نعتمد على اللون وحده
            values = [r["word"], r["before_ok"],
                      f"✗ {r['before_bad']}" if r["before_bad"] else r["before_bad"],
                      r["after_ok"],
                      f"✓ {r['after_bad']}" if not r["after_bad"]
                      else f"✗ {r['after_bad']}"]
            for j, v in enumerate(values):
                item = QTableWidgetItem(str(v))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                # ألوان اللوحة نفسها لا ألوان Qt المدمجة — وإلا اجتمع أحمر
                # Qt الفاقع وأحمر اللوحة الهادئ في الشاشة نفسها
                if j == 2 and r["before_bad"]:
                    item.setForeground(QColor(BAD))
                if j == 4:
                    item.setForeground(QColor(OK) if not r["after_bad"]
                                       else QColor(BAD))
                self.table.setItem(i, j, item)

        self.sample.setPlainText(d["sample"])
        return verdict
