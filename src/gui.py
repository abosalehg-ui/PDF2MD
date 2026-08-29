# -*- coding: utf-8 -*-
"""
gui.py — واجهة PyQt6 لأداة PDF2MD.

واجهة عربية كاملة الاتجاه (RTL): قائمة ملفات بالسحب والإفلات، تحويل دُفعي
في طابور، كل خيارات Options معروضة كعناصر تحكم، فحص تشخيصي بجدول قبل/بعد،
وثلاثة تبويبات (معاينة / تشخيص / سجل). التحويل يجري في QThread منفصل.

تشغيل:  python main.py
"""

import os
import sys
import threading
import traceback

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QKeySequence, QShortcut, QTextOption
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
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
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .common import out_path_for, stats_summary
from .core import __version__
from .gui_panels import DiagnosticsView, OptionsPanel
from .gui_theme import (
    APP_NAME,
    ORG_NAME,
    PATH_ROLE,
    PREVIEW_LIMIT,
    QSS,
    TAGLINE,
)
from .gui_workers import ConvertWorker, DiagWorker

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
        # اللوحة تُبنى قبل النافذة لأن _build يركّبها في مكانها
        self.opts = OptionsPanel()
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
        v.addWidget(self.opts)
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

        self.diag = DiagnosticsView()
        self.tabs.addTab(self.diag, "التشخيص")

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setAccessibleName("سجل التنفيذ")
        self.tabs.addTab(self.log, "السجل")
        return self.tabs

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

    # ---------- الإعدادات ----------

    def _load_settings(self):
        """
        يستعيد اختيارات آخر جلسة. الخيارات تحمّلها لوحتها، والنافذة تحمّل
        ما تملكه وحدها: مجلد الحفظ ومقاس النافذة.
        """
        self.opts.load(self._settings)
        self.ed_out.setText(self._settings.value("out_dir", "", type=str))
        geo = self._settings.value("geometry")
        if geo is not None:
            try:
                self.restoreGeometry(geo)
            except TypeError:      # قيمة محفوظة بنوع غير متوقّع — تُتجاهل
                pass

    def _save_settings(self):
        self.opts.save(self._settings)
        self._settings.setValue("out_dir", self.ed_out.text().strip())
        self._settings.setValue("geometry", self.saveGeometry())

    # ---------- الحالة ----------

    def options(self):
        return self.opts.options()


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
        verdict = self.diag.show_result(d)
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
        pf, pt = self.opts.page_range()
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
