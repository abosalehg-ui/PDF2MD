# -*- coding: utf-8 -*-
"""
gui.py — واجهة PyQt6 لأداة PDF2MD.

واجهة عربية كاملة الاتجاه (RTL): قائمة ملفات بالسحب والإفلات، تحويل دُفعي
في طابور، كل خيارات Options معروضة كعناصر تحكم، فحص تشخيصي بجدول قبل/بعد،
وثلاثة تبويبات (معاينة / تشخيص / سجل). التحويل يجري في QThread منفصل.

تشغيل:  python main.py
"""

import html
import os
import sys
import threading
import traceback

from PyQt6.QtCore import QSettings, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QKeySequence, QShortcut, QTextOption
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .common import ensure_parent, out_path_for, stats_summary, verdict_of
from .core import __version__
from .structure import ConversionCancelled, Options, convert, diagnose

APP_NAME = "PDF2MD"
ORG_NAME = "PDF2MD"

# حدّ عرض المعاينة — يحمي QPlainTextEdit من التجمّد على الكتب الكبيرة
PREVIEW_LIMIT = 200_000
TAGLINE = "استخراج نص عربي سليم من PDF المعطوب الرباطات، وتحويله إلى Markdown منظَّم"

# المسار الكامل يُخزَّن في بيانات عنصر القائمة، ويُعرض اسم الملف وحده
PATH_ROLE = Qt.ItemDataRole.UserRole

# ── لوحة الألوان ──
# النِّسَب أدناه محسوبة بمعادلة WCAG على الخلفيتين CREAM و PANEL.
BROWN = "#6B4423"
GOLD = "#C9A227"
CREAM = "#FAF6EE"
INK = "#2E2418"
LINE = "#E0D6C2"        # إطار زخرفي للمجموعات — 1.4:1، لا يحمل معنى
OK = "#2E7D52"
BAD = "#B3261E"
PANEL = "#FFFDF8"

# حدّ عناصر الإدخال. الحقل أبيض على خلفية كريمية (تباين 1.08:1)، فالحدّ هو
# وسيلة تمييزه الوحيدة — وWCAG 2.2 SC 1.4.11 يطلب 3:1 لحدود عناصر التحكم.
# كان LINE (1.44:1 على الأبيض) فلم تكن الحقول تُرى أصلًا. هذا 3.36:1.
FIELD_LINE = "#9C8A66"

# مؤشّر التركيز. GOLD يعطي 2.24:1 على CREAM — دون حدّ SC 1.4.11 نفسه، أي أن
# قاعدة :focus كانت موجودة وغير مرئية عمليًا. هذا 3.52:1 على CREAM
# و3.73:1 على PANEL. ويبقى GOLD لشريط التقدّم والتبويب: عنصران زخرفيان.
GOLD_FOCUS = "#A07F15"

# Amiri للعناوين و Cairo للمتن، مع بدائل مضمونة على كل نظام
SERIF = '"Amiri", "Scheherazade New", "Traditional Arabic", serif'
SANS = '"Cairo", "Segoe UI", "Tahoma", "Noto Sans Arabic", sans-serif'

QSS = f"""
* {{ font-family: {SANS}; font-size: 13px; color: {INK}; }}
QMainWindow, QWidget {{ background: {CREAM}; }}
QLabel#title {{ font-family: {SERIF}; font-size: 30px; font-weight: 700;
                color: {BROWN}; }}
QLabel#tagline {{ color: #7A6A55; }}
QLabel#section {{ font-family: {SERIF}; font-size: 15px; color: {BROWN};
                  font-weight: 700; }}
QGroupBox {{
    border: 1px solid {LINE}; border-radius: 10px; background: {PANEL};
    margin-top: 14px; padding: 12px 10px 10px 10px;
}}
QGroupBox::title {{
    subcontrol-origin: margin; right: 14px; padding: 2px 8px;
    font-family: {SERIF}; font-size: 15px; color: {BROWN}; font-weight: 700;
}}
QPushButton {{
    background: {BROWN}; color: #FFF9EC; border: none;
    border-radius: 8px; padding: 9px 18px; font-weight: 700;
}}
QPushButton:hover {{ background: #7D5230; }}
/* نص الحالة المعطَّلة كان #F2ECE0 على #C4B8A6 — تباين 1.66:1 يكاد يختفي
   أثناء التحويل. #6F6355 يرفعه إلى ~3.1:1 ويبقى واضحًا أنه معطَّل. */
QPushButton:disabled {{ background: #C4B8A6; color: #6F6355; }}
QPushButton#ghost {{ background: transparent; color: {BROWN};
                     border: 1px solid {BROWN}; }}
QPushButton#ghost:hover {{ background: #F0E7D6; }}
QPushButton#gold {{ background: {GOLD}; color: #3A2C08; }}
QPushButton#gold:hover {{ background: #D9B23B; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QListWidget,
QPlainTextEdit, QTableWidget {{
    background: #FFFFFF; border: 1px solid {FIELD_LINE};
    border-radius: 8px; padding: 6px; selection-background-color: {GOLD};
    selection-color: {INK};
}}
/* المعاينة والسجل نصّ عربي يُقرأ لا كود يُحاذى عموديًا — والخط الأحادي
   اللاتيني كان يخرجه مفكّك الوصل لانعدام تغطيته العربية. */
QPlainTextEdit {{ font-family: {SANS}; font-size: 13px; }}
QProgressBar {{
    border: 1px solid {LINE}; border-radius: 8px; height: 20px;
    text-align: center; background: #FFFFFF;
}}
QProgressBar::chunk {{ background: {GOLD}; border-radius: 7px; }}
QTabBar::tab {{
    background: transparent; padding: 8px 18px;
    border-bottom: 3px solid transparent; font-weight: 600;
}}
QTabBar::tab:selected {{ color: {BROWN}; border-bottom: 3px solid {GOLD}; }}
QTabWidget::pane {{ border: 1px solid {LINE}; border-radius: 10px;
                    background: {PANEL}; }}
QHeaderView::section {{
    background: #F3EADA; padding: 6px; border: none;
    border-bottom: 1px solid {LINE}; font-weight: 700; color: {BROWN};
}}
QCheckBox::indicator {{ width: 17px; height: 17px; }}
/* مؤشّر تركيز ظاهر: بدونه يفقد المتنقّل بلوحة المفاتيح موضعه بين ثمانية
   مربّعات اختيار متتالية فوق خلفية كريمية مسطّحة. اللون GOLD_FOCUS لا GOLD
   لأن الأخير 2.24:1 على الخلفية — دون 3:1 التي يفرضها WCAG 2.2 SC 1.4.11
   للمؤشّرات غير النصية، أي أن القاعدة كانت تُطبَّق ولا تُرى. */
QPushButton:focus, QCheckBox:focus, QComboBox:focus, QLineEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QListWidget:focus,
QPlainTextEdit:focus, QTableWidget:focus {{
    border: 2px solid {GOLD_FOCUS};
}}
QTabBar::tab:focus {{ border-bottom: 3px solid {GOLD_FOCUS}; }}
QStatusBar {{ background: #F3EADA; color: {BROWN}; }}
QScrollArea {{ border: none; background: transparent; }}
QSplitter::handle {{ background: transparent; }}
"""

PROFILES = [
    ("تلقائي — كشف العناوين بحجم الخط", "auto"),
    ("نظام/لائحة سعودية — الباب والفصل والمادة", "saudi_law"),
    ("نص عادي — فقرات بلا عناوين", "plain"),
]
FOOTNOTES = [
    ("اقتباس منفصل  >", "quote"),
    ("ضمن النص", "inline"),
    ("حذف", "drop"),
]


# ═══════════════════ خيوط العمل ═══════════════════

class ConvertWorker(QThread):
    """يحوّل ملفًا واحدًا خارج خيط الواجهة حتى لا تتجمّد."""

    progress = pyqtSignal(int, str)
    logline = pyqtSignal(str)
    done = pyqtSignal(str, dict, str)      # md, stats, out_path
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, pdf, opt, out_path, cancel):
        super().__init__()
        self.pdf, self.opt, self.out_path = pdf, opt, out_path
        self.cancel = cancel

    def run(self):
        try:
            md, st = convert(
                self.pdf, self.opt,
                progress=lambda p, m: self.progress.emit(p, m),
                log=lambda m: self.logline.emit(m),
                cancel=self.cancel,
            )
            if self.out_path:
                ensure_parent(self.out_path)
                with open(self.out_path, "w", encoding="utf-8") as f:
                    f.write(md)
            self.done.emit(md, st, self.out_path or "")
        except ConversionCancelled:
            self.cancelled.emit()
        except Exception:
            self.failed.emit(traceback.format_exc())


class DiagWorker(QThread):
    """فحص تشخيصي على عيّنة صفحات."""

    progress = pyqtSignal(int, str)
    done = pyqtSignal(dict)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, pdf, cancel):
        super().__init__()
        self.pdf = pdf
        self.cancel = cancel

    def run(self):
        try:
            self.done.emit(diagnose(
                self.pdf,
                progress=lambda p, m: self.progress.emit(p, m),
                cancel=self.cancel))
        except ConversionCancelled:
            self.cancelled.emit()
        except Exception:
            self.failed.emit(traceback.format_exc())


# ═══════════════════ النافذة ═══════════════════

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} — محوّل PDF العربي إلى Markdown  v{__version__}")
        self.resize(1200, 800)
        # الارتفاع الأدنى منزَّل ليعمل التطبيق على شاشة ١٣٦٦×٧٦٨ الشائعة
        # بعد خصم أشرطة النظام — والأزرار مثبَّتة فلا يخفيها المقاس الصغير.
        self.setMinimumSize(940, 560)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setAcceptDrops(True)
        self.queue = []
        self.results = []
        self.failures = []
        # الخيوط تبقى مرجَّعة حتى تنتهي فعلًا. لو استُبدل المرجع بخيط جديد
        # قبل أن ينتهي القديم، أُتلف كائن QThread وهو يعمل — وهذا انهيار.
        self._workers = []
        self._cancel = threading.Event()
        self._current = ""
        self._batch_total = 0
        self._batch_done = 0
        self._settings = QSettings(ORG_NAME, APP_NAME)
        self._build()
        self._load_settings()

    # ---------- البناء ----------

    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(14, 12, 14, 10)
        lay.setSpacing(10)

        # الحجم والخط من QSS وحده — ضبطهما هنا أيضًا كان يتنازع معه.
        # المحاذاة صريحة للاثنتين: بلا ضبطها يحسمها Qt من اتجاه نصّ كلٍّ
        # منهما، فيذهب الاسم اللاتيني يسارًا والوصف العربي يمينًا وتخرج
        # الترويسة مشقوقة على جهتين متقابلتين.
        head_align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        title = QLabel(APP_NAME)
        title.setObjectName("title")
        title.setAlignment(head_align)
        tagline = QLabel(TAGLINE)
        tagline.setObjectName("tagline")
        tagline.setAlignment(head_align)
        head = QVBoxLayout()
        head.setSpacing(0)
        head.addWidget(title)
        head.addWidget(tagline)
        lay.addLayout(head)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self._left_panel())
        split.addWidget(self._right_panel())
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([440, 760])
        lay.addWidget(split, 1)

        self.bar = QProgressBar()
        self.bar.setValue(0)
        self.bar.setAccessibleName("تقدّم التحويل")
        lay.addWidget(self.bar)

        self.setStatusBar(QStatusBar())
        self.say_status("جاهز — اسحب ملفات PDF إلى القائمة أو اضغط «إضافة ملفات»")

    def _left_panel(self):
        """
        اللوحة اليسرى: خيارات قابلة للتمرير، وصفّ أزرار **مثبَّت** أسفلها.

        كان صفّ الأزرار داخل منطقة التمرير، فكان ارتفاع محتواها (929px)
        يتجاوز نافذة العرض عند المقاس الافتراضي (649px) وعند الأدنى — أي
        أن زر «تحويل»، وهو الفعل الأساسي في التطبيق، لا يُرى إطلاقًا حتى
        يمرّر المستخدم أو يكبّر النافذة إلى ما يقارب ١٤٠٠×١٠٠٠. تثبيته
        خارج المنطقة المُمرَّرة يجعله ظاهرًا على كل مقاس مدعوم.
        """
        inner = QWidget()
        v = QVBoxLayout(inner)
        v.setContentsMargins(0, 0, 6, 0)
        v.addWidget(self._files_box())
        v.addWidget(self._options_box())
        v.addWidget(self._output_box())
        v.addStretch()

        row = QHBoxLayout()
        self.btn_diag = QPushButton("فحص تشخيصي")
        self.btn_diag.setObjectName("gold")
        self.btn_diag.setToolTip("يفحص عيّنة من الملف ويعرض جدول قبل/بعد (Ctrl+D)")
        self.btn_diag.setShortcut("Ctrl+D")
        self.btn_diag.clicked.connect(self.run_diag)
        self.btn_go = QPushButton("تحويل")
        self.btn_go.setToolTip("يحوّل كل الملفات في القائمة واحدًا تلو الآخر (Ctrl+Return)")
        self.btn_go.setShortcut("Ctrl+Return")
        self.btn_go.clicked.connect(self.run_convert)
        self.btn_stop = QPushButton("إيقاف")
        self.btn_stop.setObjectName("ghost")
        self.btn_stop.setToolTip("يوقف التحويل الجاري بأمان (Esc)")
        self.btn_stop.setShortcut("Esc")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_convert)
        row.addWidget(self.btn_diag)
        row.addWidget(self.btn_go, 1)
        row.addWidget(self.btn_stop)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)

        panel = QWidget()
        col = QVBoxLayout(panel)
        col.setContentsMargins(0, 0, 0, 0)
        col.addWidget(scroll, 1)      # الخيارات وحدها هي التي تُمرَّر
        col.addLayout(row)            # الأزرار مثبَّتة أسفل اللوحة دائمًا
        panel.setMinimumWidth(400)
        return panel

    def _files_box(self):
        box = QGroupBox("الملفات")
        g = QVBoxLayout(box)
        self.files = QListWidget()
        self.files.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.files.setMinimumHeight(120)
        self.files.setToolTip("اسحب ملفات PDF وأفلتها هنا")
        self.files.setAccessibleName("قائمة ملفات PDF المراد تحويلها")
        self.files.currentRowChanged.connect(self.refresh_diag_label)
        g.addWidget(self.files)

        row = QHBoxLayout()
        b_add = QPushButton("إضافة ملفات")
        b_add.setToolTip("اختيار ملفات PDF (Ctrl+O)")
        b_add.setShortcut("Ctrl+O")
        b_add.clicked.connect(self.pick_files)
        b_del = QPushButton("حذف المحدد")
        b_del.setObjectName("ghost")
        b_del.setToolTip("حذف الملفات المحددة من القائمة (Delete)")
        b_del.clicked.connect(self.remove_selected)
        # مفتاح Delete على القائمة نفسها: إدارة القائمة كانت بالفأرة وحدها،
        # فالمتنقّل بلوحة المفاتيح يصل إلى القائمة ولا يستطيع الحذف منها.
        del_key = QShortcut(QKeySequence.StandardKey.Delete, self.files)
        del_key.setContext(Qt.ShortcutContext.WidgetShortcut)
        del_key.activated.connect(self.remove_selected)
        b_clr = QPushButton("تفريغ")
        b_clr.setObjectName("ghost")
        b_clr.clicked.connect(self.clear_files)
        row.addWidget(b_add)
        row.addWidget(b_del)
        row.addWidget(b_clr)
        g.addLayout(row)
        return box

    def _options_box(self):
        box = QGroupBox("الخيارات")
        gl = QGridLayout(box)
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
        self.sp_top.setRange(1, 5)
        self.sp_top.setValue(2)
        self.sp_top.setAccessibleName("مستوى العنوان الرئيسي")
        self.sp_sub = QSpinBox()
        self.sp_sub.setRange(1, 6)
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
        self.sp_from.setRange(0, 99999)
        self.sp_from.setAccessibleName("أول صفحة")
        self.sp_to = QSpinBox()
        self.sp_to.setRange(0, 99999)
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
        self.sp_gap.setRange(0.20, 3.00)
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
        return box

    def _output_box(self):
        box = QGroupBox("المخرَج")
        g = QHBoxLayout(box)
        self.ed_out = QLineEdit()
        self.ed_out.setPlaceholderText("مجلد الحفظ — الافتراضي: بجانب ملف PDF")
        self.ed_out.setAccessibleName("مجلد حفظ الملفات الناتجة")
        b = QPushButton("اختيار…")
        b.setObjectName("ghost")
        b.clicked.connect(self.pick_out)
        g.addWidget(self.ed_out)
        g.addWidget(b)
        return box

    def _right_panel(self):
        self.tabs = QTabWidget()

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.preview.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.preview.setPlaceholderText("الناتج يظهر هنا بعد التحويل.")
        self.preview.setAccessibleName("معاينة الناتج")
        self.tabs.addTab(self.preview, "معاينة الناتج")

        self.tabs.addTab(self._diag_tab(), "التشخيص")

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setAccessibleName("سجل التنفيذ")
        self.tabs.addTab(self.log, "السجل")
        return self.tabs

    def _diag_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)

        self.diag_info = QLabel("شغّل «فحص تشخيصي» لمعرفة حالة الملف قبل التحويل.")
        self.diag_info.setWordWrap(True)
        self.diag_info.setTextFormat(Qt.TextFormat.RichText)
        v.addWidget(self.diag_info)

        self.tbl = QTableWidget(0, 5)
        self.tbl.setHorizontalHeaderLabels(
            ["الكلمة", "سليمة قبل", "تالفة قبل", "سليمة بعد", "تالفة بعد"])
        self.tbl.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setMaximumHeight(260)
        v.addWidget(self.tbl)

        v.addWidget(QLabel("عيّنة من النص بعد الإصلاح:"))
        self.diag_sample = QPlainTextEdit()
        self.diag_sample.setReadOnly(True)
        self.diag_sample.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        v.addWidget(self.diag_sample, 1)
        return w

    # ---------- السحب والإفلات ----------

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls()]
        self.add_files([p for p in paths if p.lower().endswith(".pdf")])

    # ---------- أدوات الملفات ----------

    def all_files(self):
        """المسارات الكاملة بترتيب القائمة."""
        return [self.files.item(i).data(PATH_ROLE)
                for i in range(self.files.count())]

    def add_files(self, paths):
        # يُعرض اسم الملف فقط (المسار الكامل يطول ويُقصّ)، ويُخزَّن كاملًا
        # في بيانات العنصر ويظهر في التلميح.
        have = set(self.all_files())
        for p in paths:
            if p and p not in have:
                have.add(p)          # يمنع التكرار داخل الدفعة الواحدة أيضًا
                item = QListWidgetItem(os.path.basename(p))
                item.setData(PATH_ROLE, p)
                item.setToolTip(p)
                self.files.addItem(item)
        if self.files.count() and not self.files.currentItem():
            self.files.setCurrentRow(0)

    def pick_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "اختر ملفات PDF", "", "ملفات PDF (*.pdf)")
        self.add_files(paths)

    def remove_selected(self):
        for item in self.files.selectedItems():
            self.files.takeItem(self.files.row(item))
        self.refresh_diag_label()

    def clear_files(self):
        """التفريغ لا رجعة فيه — نسأل قبل مسح قائمة جُمّعت بالسحب."""
        if self.files.count() > 3 and self.ask(
                "تفريغ القائمة",
                f"سيُمسح {self.files.count()} ملف من القائمة. متابعة؟") is False:
            return
        self.files.clear()
        self.refresh_diag_label()

    def pick_out(self):
        folder = QFileDialog.getExistingDirectory(self, "مجلد الحفظ")
        if folder:
            self.ed_out.setText(folder)

    def current_pdf(self):
        item = self.files.currentItem() or (
            self.files.item(0) if self.files.count() else None)
        return item.data(PATH_ROLE) if item else None

    def refresh_diag_label(self):
        """الزر يسمّي الملف الذي سيفحصه — «فحص تشخيصي» وحدها لا تقول أيّها."""
        pdf = self.current_pdf()
        self.btn_diag.setText(f"فحص: {os.path.basename(pdf)}" if pdf
                              else "فحص تشخيصي")

    # ---------- الحوارات ----------

    def _box(self, icon, title, text):
        """
        QMessageBox بصيغة نص صرف — الافتراضي AutoText يكتشف HTML ويصيّره،
        فاسم ملف فيه <b> أو <img src=…> يُصيَّر بدل أن يُعرض كما هو.
        """
        box = QMessageBox(self)
        box.setIcon(icon)
        box.setWindowTitle(title)
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(text)
        return box

    def note(self, title, text):
        self._box(QMessageBox.Icon.Information, title, text).exec()

    def warn(self, title, text):
        self._box(QMessageBox.Icon.Warning, title, text).exec()

    def fail(self, title, text):
        self._box(QMessageBox.Icon.Critical, title, text).exec()

    def ask(self, title, text):
        box = self._box(QMessageBox.Icon.Question, title, text)
        box.setStandardButtons(QMessageBox.StandardButton.Yes
                               | QMessageBox.StandardButton.No)
        return box.exec() == QMessageBox.StandardButton.Yes

    # ---------- الإعدادات ----------

    def _num(self, key, default, cast=int):
        """
        يقرأ قيمة رقمية من الإعدادات، ويسقط إلى الافتراضي عند أي تلف.

        `int(s.value(...))` المكشوف كان يرمي ValueError داخل __init__ عند
        قيمة غير رقمية (تحرير يدوي لملف الإعدادات، أو ترقية، أو تلف)،
        فلا يُقلع التطبيق أصلًا ولا يعرف المستخدم سببًا ولا مخرجًا.
        """
        try:
            return cast(self._settings.value(key, default))
        except (TypeError, ValueError):
            return default

    def _load_settings(self):
        """يستعيد اختيارات آخر جلسة — بدونها يُعاد ضبط كل شيء كل تشغيل."""
        s = self._settings
        self.cb_profile.setCurrentIndex(self._num("profile", 0))
        self.cb_foot.setCurrentIndex(self._num("footnotes", 0))
        self.ed_out.setText(s.value("out_dir", "", type=str))
        self.sp_top.setValue(self._num("h_top", 2))
        self.sp_sub.setValue(self._num("h_sub", 3))
        self.sp_gap.setValue(self._num("para_gap", 0.75, float))
        for key, box in self._checkboxes().items():
            box.setChecked(s.value(key, True, type=bool))
        geo = s.value("geometry")
        if geo is not None:
            try:
                self.restoreGeometry(geo)
            except TypeError:      # قيمة محفوظة بنوع غير متوقّع — تُتجاهل
                pass

    def _save_settings(self):
        s = self._settings
        s.setValue("profile", self.cb_profile.currentIndex())
        s.setValue("footnotes", self.cb_foot.currentIndex())
        s.setValue("out_dir", self.ed_out.text().strip())
        s.setValue("h_top", self.sp_top.value())
        s.setValue("h_sub", self.sp_sub.value())
        s.setValue("para_gap", self.sp_gap.value())
        for key, box in self._checkboxes().items():
            s.setValue(key, box.isChecked())
        s.setValue("geometry", self.saveGeometry())

    def _checkboxes(self):
        return {"fix_ligatures": self.ck_lig, "check_ink": self.ck_ink,
                "unify_digits": self.ck_dig, "drop_headers": self.ck_hdr,
                "drop_watermark": self.ck_wmk, "drop_toc": self.ck_toc,
                "build_toc": self.ck_gen, "tables": self.ck_tbl}

    # ---------- الحالة ----------

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
        )

    def start_worker(self, worker):
        """يشغّل خيطًا ويحتفظ بمرجعه حتى ينتهي."""
        self._workers.append(worker)
        worker.finished.connect(lambda: self._retire(worker))
        worker.start()

    def _retire(self, worker):
        if worker in self._workers:
            self._workers.remove(worker)
        worker.deleteLater()

    def busy(self, on, stoppable=False):
        self.btn_go.setEnabled(not on)
        self.btn_diag.setEnabled(not on)
        self.btn_stop.setEnabled(on and stoppable)

    def say(self, msg):
        self.log.appendPlainText(msg)

    def say_status(self, msg):
        self.statusBar().showMessage(msg)

    def on_progress(self, pct, msg):
        """التقدّم للدفعة كلها لا للملف وحده — وإلا عاد الشريط ٠→١٠٠ لكل ملف."""
        if self._batch_total > 1:
            overall = int((self._batch_done * 100 + pct) / self._batch_total)
            self.bar.setValue(overall)
            self.say_status(f"[{self._batch_done + 1}/{self._batch_total}] {msg}")
        else:
            self.bar.setValue(pct)
            self.say_status(msg)

    def on_fail(self, tb):
        """فشل فحص تشخيصي — لا طابور هنا، يكفي التنبيه."""
        self.busy(False)
        self.say(tb)
        self.tabs.setCurrentIndex(2)
        self.fail("خطأ", "فشل التنفيذ — راجع تبويب السجل.")

    def on_diag_cancelled(self):
        self.busy(False)
        self.say("— أُوقف الفحص بطلب المستخدم.")
        self.say_status("أُوقف الفحص")

    def on_convert_fail(self, tb):
        """فشل ملف واحد في الدفعة: يُسجَّل ويُتخطّى وتكمل بقية الملفات."""
        name = os.path.basename(self._current)
        self.failures.append(name)
        self.say(f"✗ فشل تحويل {name}:\n{tb}")
        self.say_status(f"فشل {name} — متابعة بقية الملفات")
        self._batch_done += 1
        self.next_job()

    def on_cancelled(self):
        self.queue = []
        self.busy(False)
        self.say("— أُوقف التحويل بطلب المستخدم.")
        self.say_status("أُوقف التحويل")

    def stop_convert(self):
        self._cancel.set()
        self.btn_stop.setEnabled(False)
        self.say_status("جارٍ الإيقاف…")

    def closeEvent(self, e):
        """لا نُتلف QThread وهو يعمل — نسأل، نلغي، وننتظر الخيوط."""
        if self._workers:
            if not self.ask("خروج", "ثمّة عملية جارية — إيقافها والخروج؟"):
                e.ignore()
                return
            self._cancel.set()
            for w in list(self._workers):
                w.wait(10000)
        self._save_settings()
        e.accept()

    # ---------- التشخيص ----------

    def run_diag(self):
        pdf = self.current_pdf()
        if not pdf:
            self.note("تنبيه", "أضف ملف PDF أولًا.")
            return
        self._batch_total = 1
        self._batch_done = 0
        self._cancel = threading.Event()
        self.busy(True, stoppable=True)      # الفحص صار قابلًا للإيقاف
        self.tabs.setCurrentIndex(1)
        self.say(f"\n— فحص: {os.path.basename(pdf)}")
        worker = DiagWorker(pdf, self._cancel)
        worker.progress.connect(self.on_progress)
        worker.done.connect(self.show_diag)
        worker.failed.connect(self.on_fail)
        worker.cancelled.connect(self.on_diag_cancelled)
        self.start_worker(worker)

    def show_diag(self, d):
        self.busy(False)

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
        self.diag_info.setText(
            f"<b>الصفحات:</b> {d['pages']} &nbsp;|&nbsp; "
            f"<b>العيّنة:</b> {d['sampled']} صفحة &nbsp;|&nbsp; "
            f"<b>الخطوط:</b> {d['fonts']} &nbsp;|&nbsp; "
            f"<b>طبقة نص:</b> {'نعم' if d['has_text'] else 'لا — يحتاج OCR'}<br>"
            f"<b>المنتج:</b> {html.escape(d['producer'] or '—')} &nbsp;|&nbsp; "
            f"<b>المُنشئ:</b> {html.escape(d['creator'] or '—')}<br>"
            f"<b>رباطات مُصلَحة في العيّنة:</b> {d['ligatures']:,} ({pairs})<br>"
            f"<b style='color:{color}'>{verdict}</b>"
        )

        self.tbl.setRowCount(len(d["rows"]))
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
                self.tbl.setItem(i, j, item)

        self.diag_sample.setPlainText(d["sample"])
        self.say(f"  رباطات في العيّنة: {d['ligatures']:,} | {verdict}")
        self.say_status("انتهى الفحص")

    # ---------- التحويل ----------

    def out_for(self, pdf):
        return out_path_for(pdf, self.ed_out.text().strip() or None, True)

    def run_convert(self):
        # أي استثناء غير مُمسك هنا يقع داخل slot، وPyQt6 يعامله بـqFatal
        # فينتهي التطبيق فورًا بلا رسالة وتضيع القائمة والإعدادات.
        try:
            self._run_convert()
        except Exception:
            self.say(traceback.format_exc())
            self.busy(False)
            self.tabs.setCurrentIndex(2)
            self.fail("خطأ", "تعذّر بدء التحويل — راجع تبويب السجل.")

    def _run_convert(self):
        count = self.files.count()
        if not count:
            self.note("تنبيه", "أضف ملف PDF أولًا.")
            return
        # CLI يرفض النطاق المقلوب — الواجهة كذلك، بدل تجاهله بصمت
        pf, pt = self.sp_from.value(), self.sp_to.value()
        if pf and pt and pt < pf:
            self.warn("نطاق الصفحات",
                      f"نهاية النطاق ({pt}) أصغر من بدايته ({pf}).")
            return
        # الكتابة فوق ملفات موجودة تحتاج موافقة صريحة — مرة واحدة للدفعة
        existing = [o for o in map(self.out_for, self.all_files())
                    if os.path.exists(o)]
        if existing:
            if not self.ask(
                    "ملفات موجودة",
                    f"{len(existing)} ملف مخرَج موجود مسبقًا وسيُكتب فوقه:\n"
                    + "\n".join(os.path.basename(o) for o in existing[:8])
                    + ("\n…" if len(existing) > 8 else "") + "\n\nمتابعة؟"):
                return
        self.queue = self.all_files()
        self.results = []
        self.failures = []
        self._batch_total = count
        self._batch_done = 0
        self._cancel = threading.Event()
        self.busy(True, stoppable=True)
        self.tabs.setCurrentIndex(0)
        self.say(f"\n═══ بدء تحويل {count} ملف")
        self.next_job()

    def next_job(self):
        if not self.queue:
            self.busy(False)
            self.bar.setValue(100 if self.results else 0)
            self.say_status("اكتمل التحويل")
            if self.results or self.failures:
                msg = ""
                if self.results:
                    msg += "تم إنشاء الملفات:\n" + "\n".join(self.results)
                if self.failures:
                    msg += (("\n\n" if msg else "")
                            + f"فشل {len(self.failures)} ملف (راجع السجل):\n"
                            + "\n".join(self.failures))
                (self.warn if self.failures else self.note)("تم", msg)
            return

        pdf = self.queue.pop(0)
        self._current = pdf
        out = self.out_for(pdf)
        self.say(f"\n— تحويل: {os.path.basename(pdf)}")
        worker = ConvertWorker(pdf, self.options(), out, self._cancel)
        worker.progress.connect(self.on_progress)
        worker.logline.connect(self.say)
        worker.done.connect(self.on_done)
        worker.failed.connect(self.on_convert_fail)
        worker.cancelled.connect(self.on_cancelled)
        self.start_worker(worker)

    def on_done(self, md, st, out):
        # رأس يسمّي صاحب المعاينة — كانت تُستبدَل بصمت فلا يُعرف أي ملف تعرض
        head = f"— معاينة: {os.path.basename(self._current)} —\n\n"
        body = md[:PREVIEW_LIMIT]
        if len(md) > PREVIEW_LIMIT:
            body += (f"\n\n… [المعاينة مقطوعة عند {PREVIEW_LIMIT:,} حرف — "
                     f"الملف المحفوظ كامل ({len(md):,} حرفًا)]")
        self.preview.setPlainText(head + body)
        self.say(f"  الصفحات {st['pages']} | {stats_summary(st)}")
        self.say(f"  حُفظ في: {out}")
        self.results.append(out)
        self._batch_done += 1
        self.next_job()


def run():
    """يشغّل الواجهة — تُستدعى من main.py."""
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    app.setStyleSheet(QSS)
    window = MainWindow()
    window.show()
    return app.exec()
