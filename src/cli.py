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

from .common import ensure_parent, out_path_for, stats_summary, verdict_of
from .core import __version__
from .structure import Options, convert, diagnose


def build_parser():
    p = argparse.ArgumentParser(
        prog="python main.py",
        description="PDF2MD — استخراج نص عربي سليم من PDF وتحويله إلى Markdown",
        epilog="بلا وسائط تُفتح الواجهة الرسومية.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("pdf", nargs="+", help="ملف PDF واحد أو أكثر")
    p.add_argument("-o", "--out",
                   help="مسار ينتهي بـ.md يُعدّ ملفًا، وما عداه يُعدّ مجلدًا")
    p.add_argument("--profile", default="auto",
                   choices=["auto", "saudi_law", "plain"],
                   help="نمط المستند (الافتراضي: auto)")
    p.add_argument("--title", default="", help="العنوان الرئيسي في أول الملف")
    p.add_argument("--pages", help="نطاق الصفحات، مثل 10-40 أو صفحة واحدة: 12")
    p.add_argument("--footnotes", default="quote",
                   choices=["quote", "inline", "drop"],
                   help="معالجة الحواشي (الافتراضي: quote)")
    # المستويات محدودة بما يفهمه Markdown — بلا حدّ ينتج «--h-top 400»
    # عنوانًا بأربعمئة #
    p.add_argument("--h-top", type=int, default=2, choices=range(1, 7),
                   metavar="{1..6}", help="مستوى العناوين العليا")
    p.add_argument("--h-sub", type=int, default=3, choices=range(1, 7),
                   metavar="{1..6}", help="مستوى العناوين الفرعية")
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
    p.add_argument("--keep-watermark", action="store_true",
                   help="إبقاء نص العلامة المائية (المائل أو الباهت)")
    p.add_argument("--keep-toc", action="store_true",
                   help="إبقاء صفحات الفهرس الأصلية")
    p.add_argument("--no-toc", action="store_true",
                   help="عدم توليد فهرس بروابط")
    p.add_argument("--no-tables", action="store_true",
                   help="عدم بناء جداول Markdown — الصفوف تخرج فقرات")
    p.add_argument("-f", "--force", action="store_true",
                   help="الكتابة فوق ملف مخرَج موجود مسبقًا")
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
        drop_watermark=not args.keep_watermark,
        drop_toc=not args.keep_toc,
        footnotes=args.footnotes,
        build_toc=not args.no_toc,
        tables=not args.no_tables,
        title=args.title,
        h_top=args.h_top,
        h_sub=args.h_sub,
        para_gap=args.para_gap,
    )
    if args.pages:
        # الصفحة الواحدة تُكتب رقمًا مجردًا: `--pages 12`. بلا الجزء
        # الاختياري كان أشيع استعمال يتطلب `12-12`.
        m = re.match(r"^\s*(\d+)\s*(?:-\s*(\d+)\s*)?$", args.pages)
        if not m:
            sys.exit("صيغة النطاق غير صحيحة — المتوقّع مثل: 10-40 أو 12")
        opt.page_from = int(m.group(1))
        opt.page_to = int(m.group(2)) if m.group(2) else opt.page_from
        if opt.page_to < opt.page_from:
            sys.exit("نهاية النطاق أصغر من بدايته.")
    return opt


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
    verdict, ok = verdict_of(d["rows"])
    print(f"\n   {'✓' if ok else '!'} {verdict}")


def main(argv=None):
    args = build_parser().parse_args(argv)

    missing = [f for f in args.pdf if not os.path.isfile(f)]
    if missing:
        sys.exit("ملفات غير موجودة:\n  " + "\n  ".join(missing))

    # فشل ملف واحد لا يسقط الدفعة: يُسجَّل ويُتخطّى، ويظهر أثره في exit code.
    failed = []

    if args.diag:
        for pdf in args.pdf:
            try:
                print_diag(pdf, diagnose(pdf))
            except Exception as e:
                print(f"✗ فشل فحص {os.path.basename(pdf)}: {e}", file=sys.stderr)
                failed.append(pdf)
        return 1 if failed else 0

    opt = options_from(args)
    say = (lambda m: None) if args.quiet else (lambda m: print("  " + m))
    many = len(args.pdf) > 1

    for pdf in args.pdf:
        if not args.quiet:
            print(f"\n── {os.path.basename(pdf)}")
        out = out_path_for(pdf, args.out, many)
        if os.path.exists(out) and not args.force:
            print(f"⚠ تخطٍّ: {out} موجود مسبقًا — استخدم --force للكتابة فوقه.")
            continue
        # الكتابة داخل الحماية نفسها: مسار غير موجود أو قرص ممتلئ أو صلاحية
        # مرفوضة كانت تُنهي الدفعة كلها بـtraceback خام بعد إتمام التحويل.
        try:
            md, st = convert(pdf, opt, log=say)
            ensure_parent(out)
            with open(out, "w", encoding="utf-8") as f:
                f.write(md)
        except Exception as e:
            print(f"✗ فشل تحويل {os.path.basename(pdf)}: {e}", file=sys.stderr)
            failed.append(pdf)
            continue
        print(f"✓ {out}  ({st['chars']:,} حرف — {stats_summary(st)})")

    if failed:
        print(f"\nاكتملت الدفعة مع فشل {len(failed)} من {len(args.pdf)} ملف.",
              file=sys.stderr)
    return 1 if failed else 0
