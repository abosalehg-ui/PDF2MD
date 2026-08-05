# -*- coding: utf-8 -*-
"""
cli.py — منطق سطر الأوامر في PDF2MD.

لا يُشغَّل مباشرة، بل عبر نقطة الدخول الوحيدة:

    python main.py ملف.pdf -o مخرج.md
    python main.py *.pdf --profile saudi_law -o ./md/
    python main.py كتاب.pdf --diag
"""

import argparse
import os
import re
import sys

from structure import Options, convert, diagnose
from core import __version__


def build_parser():
    p = argparse.ArgumentParser(
        prog="python main.py",
        description="PDF2MD — استخراج نص عربي سليم من PDF وتحويله إلى Markdown",
        epilog="بلا وسائط تُفتح الواجهة الرسومية.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("pdf", nargs="+", help="ملف PDF واحد أو أكثر")
    p.add_argument("-o", "--out", help="ملف المخرج أو مجلده")
    p.add_argument("--profile", default="auto",
                   choices=["auto", "saudi_law", "plain"],
                   help="نمط المستند (الافتراضي: auto)")
    p.add_argument("--title", default="", help="العنوان الرئيسي في أول الملف")
    p.add_argument("--pages", help="نطاق الصفحات، مثل 10-40")
    p.add_argument("--footnotes", default="quote",
                   choices=["quote", "inline", "drop"],
                   help="معالجة الحواشي (الافتراضي: quote)")
    p.add_argument("--h-top", type=int, default=2, help="مستوى العناوين العليا")
    p.add_argument("--h-sub", type=int, default=3, help="مستوى العناوين الفرعية")
    p.add_argument("--para-gap", type=float, default=0.75,
                   help="فجوة رأسية (× ارتفاع السطر) تبدأ فقرة")
    p.add_argument("--no-ink", action="store_true",
                   help="تعطيل فحص الحبر — أسرع ٣× وأقل دقة")
    p.add_argument("--no-ligatures", action="store_true",
                   help="تعطيل إصلاح الرباطات المقلوبة")
    p.add_argument("--keep-digits", action="store_true",
                   help="إبقاء الأرقام الهندية كما هي")
    p.add_argument("--keep-headers", action="store_true",
                   help="إبقاء الترويسة والتذييل المتكررة")
    p.add_argument("--keep-toc", action="store_true",
                   help="إبقاء صفحات الفهرس الأصلية")
    p.add_argument("--no-toc", action="store_true",
                   help="عدم توليد فهرس بروابط")
    p.add_argument("--diag", action="store_true",
                   help="فحص تشخيصي فقط بلا تحويل")
    p.add_argument("-q", "--quiet", action="store_true", help="بلا رسائل تفصيلية")
    p.add_argument("-V", "--version", action="version",
                   version=f"PDF2MD {__version__}")
    return p


def options_from(args):
    opt = Options(
        profile=args.profile,
        fix_ligatures=not args.no_ligatures,
        check_ink=not args.no_ink,
        unify_digits=not args.keep_digits,
        drop_headers=not args.keep_headers,
        drop_toc=not args.keep_toc,
        footnotes=args.footnotes,
        build_toc=not args.no_toc,
        title=args.title,
        h_top=args.h_top,
        h_sub=args.h_sub,
        para_gap=args.para_gap,
    )
    if args.pages:
        m = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", args.pages)
        if not m:
            sys.exit("صيغة النطاق غير صحيحة — المتوقّع مثل: 10-40")
        opt.page_from, opt.page_to = int(m.group(1)), int(m.group(2))
        if opt.page_to < opt.page_from:
            sys.exit("نهاية النطاق أصغر من بدايته.")
    return opt


def out_path_for(pdf, out, many):
    """يحدّد مسار المخرَج: ملف واحد صريح، أو مجلد، أو بجانب ملف PDF."""
    if out and not many and not os.path.isdir(out) and not out.endswith(os.sep):
        return out
    folder = out if out else (os.path.dirname(os.path.abspath(pdf)))
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, os.path.splitext(os.path.basename(pdf))[0] + ".md")


def print_diag(pdf, d):
    print(f"\n── {os.path.basename(pdf)}")
    print(f"   الصفحات: {d['pages']}  |  العيّنة: {d['sampled']}  |  "
          f"الخطوط: {d['fonts']}")
    print(f"   المنتج: {d['producer'] or '—'}  |  المُنشئ: {d['creator'] or '—'}")
    if not d["has_text"]:
        print("   ⚠ لا توجد طبقة نص — الملف مصوّر ويحتاج OCR قبل التحويل."
              if d["needs_ocr"] else "   ⚠ لا توجد طبقة نص في هذا الملف.")
        return
    pairs = "، ".join(f"{k}×{v}" for k, v in d["pairs"]) or "—"
    print(f"   رباطات مُصلَحة في العيّنة: {d['ligatures']:,}  ({pairs})")
    print(f"\n   {'الكلمة':<12}{'قبل ✓':>8}{'قبل ✗':>8}{'بعد ✓':>8}{'بعد ✗':>8}")
    for r in d["rows"]:
        print(f"   {r['word']:<12}{r['before_ok']:>8}{r['before_bad']:>8}"
              f"{r['after_ok']:>8}{r['after_bad']:>8}")
    before_bad = sum(r["before_bad"] for r in d["rows"])
    after_bad = sum(r["after_bad"] for r in d["rows"])
    if before_bad == 0:
        print("\n   ✓ الملف سليم — لا حاجة لإصلاح الرباطات.")
    elif after_bad == 0:
        print(f"\n   ✓ رُصد تلف في الرباطات وأُصلح بالكامل ({before_bad} حالة في العيّنة).")
    else:
        print(f"\n   ! أُصلح أغلب التلف، وبقي {after_bad} حالة تحتاج فحصًا يدويًا.")


def main(argv=None):
    args = build_parser().parse_args(argv)

    missing = [f for f in args.pdf if not os.path.isfile(f)]
    if missing:
        sys.exit("ملفات غير موجودة:\n  " + "\n  ".join(missing))

    if args.diag:
        for pdf in args.pdf:
            print_diag(pdf, diagnose(pdf))
        return 0

    opt = options_from(args)
    say = (lambda m: None) if args.quiet else (lambda m: print("  " + m))

    for pdf in args.pdf:
        if not args.quiet:
            print(f"\n── {os.path.basename(pdf)}")
        md, st = convert(pdf, opt, log=say)
        out = out_path_for(pdf, args.out, len(args.pdf) > 1)
        with open(out, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"✓ {out}  ({st['chars']:,} حرف، {st['lig']:,} رباط، "
              f"{st['headings']} عنوانًا)")
    return 0
