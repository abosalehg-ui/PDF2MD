#!/usr/bin/env bash
# PDF2MD — مشغّل لينكس وماك.
# يكتشف مسار نفسه، ويثبّت المتطلبات تلقائيًا لو كانت ناقصة، ثم يشغّل الأداة.
#
#   ./run.sh                    ← الواجهة الرسومية
#   ./run.sh ملف.pdf -o out.md  ← سطر الأوامر

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# ── اختيار مفسّر بايثون ٣ ──
PY=""
for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
        PY="$c"
        break
    fi
done

if [ -z "$PY" ]; then
    echo "لم يُعثر على Python 3.9 أو أحدث. ثبّته أولًا: https://www.python.org/downloads/" >&2
    exit 1
fi

# ── تثبيت المتطلبات عند الحاجة ──
if ! "$PY" -c 'import fitz, numpy, PyQt6' >/dev/null 2>&1; then
    echo "المتطلبات ناقصة — جارٍ تثبيتها من requirements.txt ..."
    if ! "$PY" -m pip install -r "$DIR/requirements.txt"; then
        echo "فشل التثبيت العام — إعادة المحاولة على مستوى المستخدم ..." >&2
        "$PY" -m pip install --user -r "$DIR/requirements.txt"
    fi
fi

exec "$PY" "$DIR/main.py" "$@"
