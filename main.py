#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF2MD — نقطة الدخول الوحيدة.

    python main.py                       ← يفتح الواجهة الرسومية
    python main.py ملف.pdf -o مخرج.md    ← يشتغل من سطر الأوامر
    python main.py --help                ← قائمة خيارات سطر الأوامر

هذا الملف يضيف مجلد src إلى sys.path، فتصبح استيرادات الوحدات داخله
مطلقة وبسيطة (import core) بلا حاجة إلى تشغيل المشروع كحزمة.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")

if not os.path.isdir(SRC):
    sys.exit(f"مجلد src غير موجود بجانب main.py:\n  {SRC}")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


# ── التحقق من المتطلبات قبل أي استيراد ثقيل ──

CORE_DEPS = [("fitz", "PyMuPDF"), ("numpy", "numpy")]
GUI_DEPS = [("PyQt6", "PyQt6")]


def missing(deps):
    out = []
    for module, package in deps:
        try:
            __import__(module)
        except ImportError:
            out.append(package)
    return out


def bail(packages):
    launcher = "run.bat" if os.name == "nt" else "./run.sh"
    sys.exit(
        "\nمتطلبات ناقصة: " + "، ".join(packages) + "\n\n"
        "ثبّتها بأحد الأمرين:\n"
        f"  {sys.executable} -m pip install -r requirements.txt\n"
        f"  {launcher}\n"
    )


def main():
    args = sys.argv[1:]

    lacking = missing(CORE_DEPS)
    if lacking:
        bail(lacking)

    if args:
        import cli
        return cli.main(args)

    lacking = missing(GUI_DEPS)
    if lacking:
        bail(lacking)

    import gui
    return gui.run()


if __name__ == "__main__":
    sys.exit(main() or 0)
