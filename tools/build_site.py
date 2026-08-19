#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_site.py — يجمّع الموقع الساكن في _site/ استعدادًا للنشر.

    python3 tools/build_site.py            # يفترض أن web/vendor جاهز
    python3 tools/build_site.py --fetch     # ينزّل زمن التشغيل أولًا

المستودع مشروع بايثون قبل أن يكون موقعًا: فيه اختبارات ومراجعات وملفّ
main.py لا شأن لها بصفحة الويب. لذلك لا يُنشر المستودع كما هو، بل تُجمَّع
منه أربعة أشياء فقط: الصفحة، وأصولها، وزمن التشغيل، وملفات المحرّك التي
يذكرها web/runtime.json — والبيان وحده يقرّر أيّها، فلا تنشأ قائمة ثانية
هنا تنسى ملفًا أُضيف هناك.
"""

import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SITE = os.path.join(ROOT, "_site")
VENDOR = os.path.join(ROOT, "web", "vendor")


def main():
    if "--fetch" in sys.argv[1:]:
        sys.path.insert(0, HERE)
        import fetch_web_runtime

        fetch_web_runtime.main()

    if not os.path.isdir(VENDOR):
        sys.exit("✗ web/vendor غير موجود — شغّل: python3 tools/fetch_web_runtime.py")

    with open(os.path.join(ROOT, "web", "runtime.json"), encoding="utf-8") as f:
        manifest = json.load(f)

    if os.path.isdir(SITE):
        shutil.rmtree(SITE)
    os.makedirs(os.path.join(SITE, "src"))

    shutil.copy(os.path.join(ROOT, "index.html"), SITE)
    shutil.copytree(os.path.join(ROOT, "web"), os.path.join(SITE, "web"))
    for name in manifest["sources"]:
        shutil.copy(os.path.join(ROOT, "src", name),
                    os.path.join(SITE, "src", name))

    # يمنع Jekyll من ابتلاع أي ملف يبدأ بشرطة سفلية إن فُعّل على المستودع
    open(os.path.join(SITE, ".nojekyll"), "w").close()

    total = sum(
        os.path.getsize(os.path.join(base, name))
        for base, _, names in os.walk(SITE)
        for name in names
    )
    print(f"✓ _site جاهز — {total / (1 << 20):.1f} م.ب")


if __name__ == "__main__":
    main()
