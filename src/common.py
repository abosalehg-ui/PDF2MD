# -*- coding: utf-8 -*-
"""
common.py — منطق مشترك بين cli.py و gui.py.

كل ما كان مكررًا بين الواجهتين يعيش هنا مرة واحدة: حكم التشخيص،
بناء مسار المخرَج، وسطر ملخّص الإحصاءات.
"""

import os


def verdict_of(rows):
    """
    يرجّع (نص الحكم، هل النتيجة سليمة) من جدول قبل/بعد للكلمات المؤشّرة.
    """
    before_bad = sum(r["before_bad"] for r in rows)
    after_bad = sum(r["after_bad"] for r in rows)
    if before_bad == 0:
        return "الملف سليم — لا حاجة لإصلاح الرباطات.", True
    if after_bad == 0:
        return (f"رُصد تلف في الرباطات وأُصلح بالكامل "
                f"({before_bad} حالة في العيّنة)."), True
    return f"أُصلح أغلب التلف، وبقي {after_bad} حالة تحتاج فحصًا يدويًا.", False


def out_path_for(pdf, out, many):
    """
    يحدّد مسار المخرَج: ملف واحد صريح، أو مجلد، أو بجانب ملف PDF.

    حسابية بحتة بلا أي أثر على القرص — كانت تنشئ المجلد بنفسها، فكانت
    الواجهة تُنشئ مجلدات لمجرد فحص وجود ملفات المخرَج قبل موافقة المستخدم،
    وكان فشل الإنشاء يُرفع داخل slot في Qt فيُنهي التطبيق. إنشاء المجلد
    مسؤولية موضع الكتابة الفعلي: ensure_parent().
    """
    if out and not many and not os.path.isdir(out) and not out.endswith(os.sep):
        return out
    folder = out if out else (os.path.dirname(os.path.abspath(pdf)))
    return os.path.join(folder, os.path.splitext(os.path.basename(pdf))[0] + ".md")


def ensure_parent(path):
    """ينشئ مجلد الأب لمسار الكتابة إن لم يكن موجودًا."""
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def stats_summary(st):
    """سطر إحصاءات موحّد يُعرض بعد كل تحويل."""
    return (f"رباطات {st['lig']:,} | عناوين {st['headings']} | "
            f"حواشي {st.get('notes', 0)} | جداول {st.get('tables', 0)} | "
            f"فهارس متخطّاة {st.get('toc_skipped', 0)}")
