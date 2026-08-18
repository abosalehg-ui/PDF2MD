# -*- coding: utf-8 -*-
"""
اختبارات الواجهة الرسومية — بلا شاشة.

`gui.py` كان ٩٠٠+ سطر بتغطية صفر، وأخطر عيوبه (زر أساسي خارج الشاشة،
إعدادات تالفة تمنع الإقلاع) لا تظهر إلا بإقلاع النافذة فعلًا. القناة
`offscreen` في Qt تُقلع نافذة كاملة بلا خادم عرض، فتُقاس منها الإحداثيات
وتُشغَّل الـslots — وهذا يكفي لحراسة ما لا تكشفه قراءة الكود.

يُتخطّى الملف كله إن غاب PyQt6، لأن سطر الأوامر يعمل بدونه ووظيفة الاختبارات
الأساسية في CI لا تثبّته عمدًا لتُثبت ذلك. الوظيفة `gui` في CI تثبّته وتشغّل
هذا الملف — فلو تُخطّي هنا أيضًا لما حرس شيئًا.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6.QtWidgets", reason="PyQt6 غير مثبّت — الواجهة اختيارية")

from PyQt6.QtCore import QSettings, Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from src import gui  # noqa: E402
from src.structure import Options  # noqa: E402


@pytest.fixture(scope="session")
def app():
    """QApplication واحد للجلسة — Qt لا يسمح بأكثر من واحد في العملية."""
    instance = QApplication.instance() or QApplication([])
    instance.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    instance.setStyleSheet(gui.QSS)
    return instance


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    """نافذة بإعدادات معزولة — حتى لا تلمس الاختبارات إعدادات المستخدم."""
    monkeypatch.setattr(
        gui, "QSettings",
        lambda org, name: QSettings(str(tmp_path / "s.ini"),
                                    QSettings.Format.IniFormat))
    win = gui.MainWindow()
    win.show()
    app.processEvents()
    yield win
    win.close()


# ═══════════ الأزرار مرئية على كل مقاس مدعوم ═══════════

@pytest.mark.parametrize("size", [(940, 560), (1200, 800), (1400, 1000)])
def test_action_buttons_visible_at_every_supported_size(window, app, size):
    """
    الانحدار: صفّ الأزرار كان داخل QScrollArea، فارتفاع محتواها يتجاوز
    نافذة العرض عند المقاس الافتراضي — أي أن زر «تحويل»، وهو الفعل
    الأساسي في التطبيق، لا يُرى إطلاقًا حتى يمرّر المستخدم أو يكبّر النافذة.
    """
    window.resize(*size)
    app.processEvents()
    for button in (window.btn_go, window.btn_diag, window.btn_stop):
        top = button.mapTo(window, button.rect().topLeft()).y()
        assert top >= 0
        assert top + button.height() <= window.height(), (
            f"{button.text()} خارج النافذة عند {size}")


def test_minimum_size_fits_a_1366x768_screen(window):
    """الحدّ الأدنى يجب أن يعمل على أشيع شاشة لابتوب بعد أشرطة النظام."""
    assert window.minimumHeight() <= 620
    assert window.minimumWidth() <= 1366


# ═══════════ الإعدادات: دورة حفظ واستعادة، وصمود أمام التلف ═══════════

def test_settings_round_trip(window, app, tmp_path, monkeypatch):
    """ما يُحفظ عند الخروج يُستعاد عند التشغيل التالي — كل حقل منه."""
    window.cb_profile.setCurrentIndex(1)
    window.cb_foot.setCurrentIndex(2)
    window.sp_top.setValue(3)
    window.sp_sub.setValue(4)
    window.sp_gap.setValue(1.25)
    window.ck_ink.setChecked(False)
    window.ed_out.setText(str(tmp_path / "out"))
    window._save_settings()

    fresh = gui.MainWindow()
    try:
        assert fresh.cb_profile.currentIndex() == 1
        assert fresh.cb_foot.currentIndex() == 2
        assert fresh.sp_top.value() == 3
        assert fresh.sp_sub.value() == 4
        assert fresh.sp_gap.value() == pytest.approx(1.25)
        assert fresh.ck_ink.isChecked() is False
        assert fresh.ed_out.text() == str(tmp_path / "out")
    finally:
        fresh.close()


def test_corrupt_settings_do_not_block_startup(app, tmp_path, monkeypatch):
    """
    الانحدار: `int(s.value("h_top", 2))` المكشوف كان يرمي ValueError داخل
    __init__ عند قيمة غير رقمية، فلا يُقلع التطبيق أصلًا ولا يعرف المستخدم
    سببًا ولا مخرجًا.
    """
    path = str(tmp_path / "corrupt.ini")
    store = QSettings(path, QSettings.Format.IniFormat)
    for key, junk in (("h_top", "غير رقمي"), ("h_sub", ""),
                      ("para_gap", "abc"), ("profile", "x"),
                      ("footnotes", "?"), ("geometry", "ليست QByteArray")):
        store.setValue(key, junk)
    store.sync()
    monkeypatch.setattr(gui, "QSettings",
                        lambda org, name: QSettings(path,
                                                    QSettings.Format.IniFormat))

    win = gui.MainWindow()          # كان ينفجر هنا
    try:
        assert win.sp_top.value() == 2          # سقط إلى الافتراضي
        assert win.sp_sub.value() == 3
        assert win.sp_gap.value() == pytest.approx(0.75)
    finally:
        win.close()


# ═══════════ الخيارات: الواجهة تبني Options مطابقًا لحالتها ═══════════

def test_options_reflect_widget_state(window):
    window.cb_profile.setCurrentIndex(1)            # saudi_law
    window.cb_foot.setCurrentIndex(2)               # drop
    window.ed_title.setText("  نظام العمل  ")
    window.sp_from.setValue(5)
    window.sp_to.setValue(9)
    window.ck_tbl.setChecked(False)

    opt = window.options()
    assert opt.profile == "saudi_law"
    assert opt.footnotes == "drop"
    assert opt.title == "نظام العمل"                # مقصوص الأطراف
    assert (opt.page_from, opt.page_to) == (5, 9)
    assert opt.tables is False


def test_every_boolean_option_has_a_checkbox(window):
    """
    بناء Options مكرر بين cli.options_from و gui.options، فخيار جديد يتطلب
    تعديل أربعة مواضع. بلا هذا الحارس يوجد الخيار في سطر الأوامر ويغيب عن
    الواجهة بصمت. `title` مستثنى: حقل نص لا مربّع اختيار.
    """
    boolean_fields = {name for name, field in Options.__dataclass_fields__.items()
                      if field.type in ("bool", bool)}
    assert boolean_fields, "لم يُقرأ أي حقل منطقي — تغيّر شكل dataclass"
    assert boolean_fields == set(window._checkboxes())


def test_every_checkbox_maps_to_a_real_option(window):
    """والعكس: مربّع لا يقابله حقل في Options يعني إعدادًا يُحفظ ولا يُستعمل."""
    for key in window._checkboxes():
        assert key in Options.__dataclass_fields__


# ═══════════ الحراسة قبل بدء الدفعة ═══════════

def test_reversed_page_range_blocks_the_batch(window, tmp_path, monkeypatch):
    """الواجهة ترفض النطاق المقلوب مثل سطر الأوامر، بدل تجاهله بصمت."""
    window.add_files([str(tmp_path / "أي.pdf")])
    window.sp_from.setValue(9)
    window.sp_to.setValue(3)

    warned = []
    monkeypatch.setattr(window, "warn", lambda t, m: warned.append(m))
    monkeypatch.setattr(window, "next_job",
                        lambda: pytest.fail("بدأت الدفعة رغم النطاق المقلوب"))
    window.run_convert()

    assert warned and "أصغر من بدايته" in warned[0]


def test_empty_queue_is_reported_not_started(window, monkeypatch):
    noted = []
    monkeypatch.setattr(window, "note", lambda t, m: noted.append(m))
    monkeypatch.setattr(window, "next_job",
                        lambda: pytest.fail("بدأت الدفعة بلا ملفات"))
    window.run_convert()
    assert noted


# ═══════════ إدارة قائمة الملفات ═══════════

def test_add_files_deduplicates_and_keeps_full_path(window, tmp_path):
    first, second = str(tmp_path / "a.pdf"), str(tmp_path / "b.pdf")
    window.add_files([first, second, first])
    assert window.all_files() == [first, second]
    assert window.files.item(0).text() == "a.pdf"       # يُعرض الاسم وحده


def test_remove_selected_drops_only_the_selection(window, tmp_path):
    paths = [str(tmp_path / f"{n}.pdf") for n in "abc"]
    window.add_files(paths)
    # add_files تضبط الصف الجاري على الأول، وضبطه يحدّده أيضًا — فيُفرَّغ
    # التحديد أولًا حتى يقيس الاختبار الحذف لا أثر الإضافة.
    window.files.clearSelection()
    window.files.item(1).setSelected(True)
    window.remove_selected()
    assert window.all_files() == [paths[0], paths[2]]


# ═══════════ الخيوط تُنظَّف بعد انتهائها ═══════════

def test_worker_is_retired_after_it_finishes(window):
    """
    مرجع الخيط يبقى محفوظًا حتى ينتهي فعلًا — لو استُبدل قبل ذلك أُتلف
    كائن QThread وهو يعمل، وهذا انهيار. و_retire يفرغه بعد الانتهاء.
    """
    class Signal:
        """إشارة Qt بأقل ما يكفي: تحفظ الـslot ليُستدعى يدويًا."""

        def __init__(self):
            self.slot = None

        def connect(self, slot):
            self.slot = slot

    class DummyWorker:
        """خيط وهمي — تشغيل QThread حقيقي في اختبار يجعله غير حتمي."""

        def __init__(self):
            self.started = False
            self.finished = Signal()

        def start(self):
            self.started = True

        def deleteLater(self):
            pass

    worker = DummyWorker()
    window.start_worker(worker)
    assert worker.started and worker in window._workers

    worker.finished.slot()                       # يحاكي إشارة الانتهاء
    assert worker not in window._workers
