#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
serve.py — خادم تطوير محلي لواجهة الويب.

    python3 tools/serve.py            # http://127.0.0.1:8000
    python3 tools/serve.py 9000

`python3 -m http.server` وحده لا يكفي: لا يعرف امتداد ‎.wasm على كل
الأنظمة، وبدون النوع `application/wasm` يرفض المتصفّح تصريف الوحدة
ويقف الإقلاع عند «تحميل مفسّر بايثون».
"""

import functools
import http.server
import os
import socketserver
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR = os.path.join(ROOT, "web", "vendor")


class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = dict(
        http.server.SimpleHTTPRequestHandler.extensions_map,
        **{
            ".wasm": "application/wasm",
            ".js": "text/javascript",
            ".mjs": "text/javascript",
            ".json": "application/json",
            ".whl": "application/octet-stream",
            ".py": "text/plain; charset=utf-8",
            ".md": "text/plain; charset=utf-8",
        },
    )

    def end_headers(self):
        # التطوير يعني تعديل ملف وتحديث الصفحة؛ الذاكرة المؤقتة هنا تُظهر
        # نسخة قديمة وتُضيّع وقتًا في مطاردة عيب مُصلَح أصلًا.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        if "404" in (fmt % args):
            super().log_message(fmt, *args)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    if not os.path.isdir(VENDOR):
        print("⚠ web/vendor غير موجود — شغّل أولًا:\n"
              "   python3 tools/fetch_web_runtime.py\n", file=sys.stderr)

    handler = functools.partial(Handler, directory=ROOT)
    # خادم بخيوط: الصفحة والخيط العامل يطلبان معًا، وملف wasm بحجم ٨
    # ميغابايت على خادم بخيط واحد يوقف بقية الطلبات حتى ينتهي.
    Server.allow_reuse_address = True
    with Server(("127.0.0.1", port), handler) as httpd:
        print(f"PDF2MD على http://127.0.0.1:{port}/  — Ctrl+C للإيقاف")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nتوقّف الخادم.")


if __name__ == "__main__":
    main()
