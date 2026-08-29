# -*- coding: utf-8 -*-
"""
gui_workers.py — خيوط العمل في تطبيق سطح المكتب.

التحويل والفحص عمليتان تمتدّان ثوانيَ إلى دقائق، وتشغيلهما في خيط الواجهة
يجمّد النافذة كلها: لا شريط تقدّم يتحرّك ولا زرّ يستجيب ولا إيقاف يُسمَع.
كلٌّ منهما هنا QThread يبثّ تقدّمه بإشارات Qt، ويمسك استثناءه بنفسه —
فالاستثناء الذي يعبر حدّ الخيط في PyQt6 يُنهي التطبيق بـqFatal.
"""

import traceback

from PyQt6.QtCore import QThread, pyqtSignal

from .common import ensure_parent
from .structure import ConversionCancelled, convert, diagnose

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
