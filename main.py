#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF2MD — نقطة الدخول الوحيدة.

    python main.py                       ← يفتح الواجهة الرسومية
    python main.py ملف.pdf -o مخرج.md    ← يشتغل من سطر الأوامر
    python main.py --help                ← قائمة خيارات سطر الأوامر

src حزمة بايثون عادية (فيها __init__.py) واستيراداتها الداخلية نسبية.
نضمن فقط أن جذر المشروع على sys.path عند التشغيل من مجلد آخر.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

if not os.path.isdir(os.path.join(HERE, "src")):
    sys.exit(f"مجلد src غير موجود بجانب main.py:\n  {os.path.join(HERE, 'src')}")


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
        from src import cli
        return cli.main(args)

    lacking = missing(GUI_DEPS)
    if lacking:
        bail(lacking)

    from src import gui
    return gui.run()


if __name__ == "__main__":
    sys.exit(main() or 0)
