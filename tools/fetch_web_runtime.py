#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_web_runtime.py — ينزّل زمن تشغيل بايثون في المتصفح إلى web/vendor/.

    python3 tools/fetch_web_runtime.py

الملفات المنزَّلة ثنائية بحجم ~٣٣ ميغابايت، ولذلك لا تدخل المستودع: هذا
السكربت يجلبها للتطوير المحلي، وسير عمل GitHub Pages يشغّله نفسه قبل
النشر — فما يُنشر يبقى ذاتيَّ الاستضافة بالكامل بلا شبكة توصيل محتوى.

الإصدارات وبصماتها في web/runtime.json وحده. وكل ملف يُتحقّق من بصمته
قبل استعماله: الأداة تُشغَّل من متصفّح المستخدم، فحزمة مبدَّلة في الطريق
تعني تنفيذ شيفرة غريبة على مستنداته.
"""

import hashlib
import json
import os
import shutil
import sys
import tarfile
import tempfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MANIFEST = os.path.join(ROOT, "web", "runtime.json")
VENDOR = os.path.join(ROOT, "web", "vendor")

# ما يحتاجه المتصفّح فعلًا من حزمة pyodide-core. البقية تعريفات TypeScript
# ومشغّل سطر أوامر لا محلّ لهما في صفحة ويب.
CORE_FILES = {
    "pyodide.js",
    "pyodide.asm.js",
    "pyodide.asm.wasm",
    "pyodide-lock.json",
    "python_stdlib.zip",
}

CHUNK = 1 << 16


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def fetch(url, dest, sha256):
    """ينزّل url إلى dest ويتحقّق من بصمته — ويتخطّى ما هو موجود سليمًا."""
    if os.path.exists(dest) and digest(dest) == sha256:
        print(f"  ✓ موجود: {os.path.basename(dest)}")
        return dest

    print(f"  ↓ {os.path.basename(dest)}")
    tmp = dest + ".part"
    with urllib.request.urlopen(url) as response, open(tmp, "wb") as out:
        shutil.copyfileobj(response, out, CHUNK)

    found = digest(tmp)
    if found != sha256:
        os.remove(tmp)
        sys.exit(
            f"✗ بصمة غير مطابقة لـ{url}\n"
            f"  المتوقّع: {sha256}\n  الموجود : {found}\n"
            "  حدِّث web/runtime.json إن كان التغيير مقصودًا."
        )
    os.replace(tmp, dest)
    return dest


def extract_core(archive):
    """
    يستخرج ملفات pyodide الأساسية وحدها إلى web/vendor بلا مجلد وسيط.

    الاستخراج انتقائي بالاسم لا بالمسار: أرشيف يحمل عضوًا اسمه `../x` أو
    مسارًا مطلقًا يكتب خارج المجلد المقصود، وtarfile في بايثون ٣٫٩ لا يمنعه
    من تلقاء نفسه.
    """
    with tarfile.open(archive, "r:bz2") as tar:
        for member in tar.getmembers():
            name = os.path.basename(member.name)
            if not member.isfile() or name not in CORE_FILES:
                continue
            source = tar.extractfile(member)
            if source is None:
                continue
            with source, open(os.path.join(VENDOR, name), "wb") as out:
                shutil.copyfileobj(source, out, CHUNK)
            print(f"  ✓ {name}")


def main():
    with open(MANIFEST, encoding="utf-8") as f:
        manifest = json.load(f)

    os.makedirs(VENDOR, exist_ok=True)
    print(f"زمن تشغيل Pyodide {manifest['pyodide']} → web/vendor/")

    core = manifest["core"]
    with tempfile.TemporaryDirectory() as tmp:
        archive = fetch(core["url"], os.path.join(tmp, "pyodide-core.tar.bz2"),
                        core["sha256"])
        extract_core(archive)

    for wheel in manifest["wheels"]:
        fetch(wheel["url"], os.path.join(VENDOR, wheel["file"]), wheel["sha256"])

    missing = [name for name in CORE_FILES
               if not os.path.exists(os.path.join(VENDOR, name))]
    if missing:
        sys.exit("✗ ملفات ناقصة بعد الاستخراج: " + "، ".join(missing))

    total = sum(os.path.getsize(os.path.join(VENDOR, name))
                for name in os.listdir(VENDOR))
    print(f"\n✓ جاهز — {total / (1 << 20):.1f} م.ب في web/vendor/")
    print("  شغّل الواجهة محليًا:  python3 tools/serve.py")


if __name__ == "__main__":
    main()
