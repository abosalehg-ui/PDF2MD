# PDF2MD

<div dir="rtl">

أداة سطح مكتب لاستخراج **نص عربي سليم** من ملفات PDF المعطوبة، وتحويله إلى **Markdown منظَّم**.

[English below ↓](#english)

---

## المشكلة التي تحلّها

ملفات PDF العربية المصدَّرة من Word ثم المعالَجة عبر macOS/iOS (محرّك Quartz) — وهي شائعة جدًّا في الكتب والأنظمة والوثائق العربية — تحمل خللًا في خريطة `ToUnicode`: **الرباطات العربية تُخزَّن بترتيب معكوس**.

النتيجة عند النسخ أو التحويل بأي أداة عادية:

| الصحيح | ما يخرج فعليًّا |
|---|---|
| المادة | املادة |
| اللائحة | الالئحة |
| المملكة | اململكة |
| الأول | األول |
| وتاريخ | واتريخ |
| اللازم | الالزم |

`pdftotext` و`PyMuPDF` و`Marker` ومحوّلات الويب كلها تنتج هذا التلف، لأن المشكلة في الملف نفسه لا في الأداة. في كتاب واحد قد تتجاوز الكلمات التالفة **اثني عشر ألف كلمة**.

---

## كيف تعمل

الأداة **لا تخمّن ولا تعتمد على قاموس**. كل الإصلاحات مبنية على قواعد هندسية مأخوذة من إحداثيات الحروف على الصفحة ومن بكسلات الصفحة المرسومة.

### ١. إصلاح الرباطات المقلوبة

الرباط يُرسم بجليف واحد، فيخرج حرفه الأول بعرض **صفر** لأنه ملتصق بالجليف — وترتيب الحرفين معكوس في مجرى النص.

القاعدة: أي حرف عرضه صفر وليس علامة تشكيل ← يُبدَّل مع الحرف الذي يليه مباشرة. النتيجة `chars[i+1] + chars[i]`.

القاعدة عامة ولا تُقيَّد بحرف اللام، فتغطي تلقائيًّا: `لا` `لأ` `لإ` `لآ` `لم` `لح` `لج` `لخ` `تا` `با` `في` وأي رباط آخر في أي خط.

### ٢. إعادة بناء السطر البصري

`PyMuPDF` يقسّم السطر الواحد عند كل تغيّر اتجاه، فينتج:

```
المادة الثانية
والعشرون(
22
):(
1)
```

تُجمع الأجزاء في سطر بصري واحد بشرطين **معًا**:

- **تقارب رأسي** — فرق مركز `y` ≤ `0.55 ×` أقصى ارتفاع
- **عدم تداخل أفقي** — التداخل < ٥٠٪ من أصغر عرض

فحص التداخل يجري على **كل جزء بمفرده** لا على الصندوق الجامع؛ ولو فُحص على الصندوق الجامع لرُفضت الأرقام الواقعة بين جزأين عربيين.

اتجاه السطر: إن كان فيه حرف عربي رُتّب تنازليًّا حسب `x1`، وإلا تصاعديًّا حسب `x0`.

### ٣. فحص الحبر — كشف المسافات الوهمية

بعض المسافات موجودة في مجرى النص لكنها **لا تُرسم**، لأن الحرف مرسوم فوق موضعها — فتخرج `يقتض ي` و`الأ صلي` و`المرسو م`.

تُرسم الصفحة بدقّة ١٥٠ نقطة/بوصة رماديًّا، ويُعدّ البكسل الأغمق من ١٢٨ حبرًا. ولكل مسافة مرشّحة بين حرفين عربيين تُؤخذ المنطقة بين `x1` للحرف الأيسر و`x0` للحرف الأيمن، وتُقلَّص ٣٠٪ من كل جهة، ويُحدّ نطاقها الرأسي بأعلى ٧٨٪ من السطر (تجاهلًا للذيول والتسطير).

القياس الفعلي:

| | كثافة الحبر |
|---|---|
| مسافة حقيقية | ≤ ٢٪ |
| مسافة وهمية | ٩–٢١٪ |

فالعتبة `0.06` تفصل بينهما بهامش واسع من الجهتين. (هذا الخيار يُبطئ المعالجة نحو ٣×، ويمكن تعطيله.)

### ٤. المسافات من الفجوات

العتبة: `الفجوة ÷ حجم الخط > 0.13`. (توزيع مقيس على ٢٨ ألف فجوة: داخل الكلمة < `0.02` بنسبة ٨١٪، وبين الكلمات ≥ `0.13`.)

المسافات المستنبطة من الفجوات تمرّ هي أيضًا على فحص الحبر، وإلا أعادت قاعدة الفجوة إدراج المسافة الوهمية بعد حذفها.

### ٥. ترتيب الأرقام والتواريخ

الأرقام تُكتب من اليسار لليمين داخل نص RTL، فتخرج معكوسة بعد الترتيب البصري. تُكتشف التسلسلات الرقمية/اللاتينية وتُعكس لتعود لترتيبها المنطقي:

- الأرقام الهندية `٠-٩` والفارسية `۰-۹` تُعامل معاملة `0-9` كأرقام قوية، لأنها تظهر مختلطة في العدد نفسه.
- الفواصل العددية `/ . , : -` بين رقمين تُضمّ داخل التسلسل نفسه.
- أي مسافة محصورة بين رقمين أو فواصل عددية تُسقط، لأنها تكسر التاريخ فيخرج `6/5/1436` بدل `1436/6/5`.
- الوحدات داخل التسلسل المعكوس تُعلَّم `glue` حتى لا تعيد قاعدة الفجوة إدراج مسافة داخل العدد.

### ٦. التشكيل الطائر

علامات التشكيل تُصدَّر منفصلة وقد **تسبق** حرفها في المجرى. تُربط كل علامة بالحرف العربي الذي يحتوي موقعها إحداثيًّا (أقرب حرف عربي لمركز العلامة). بدون ذلك تخرج `يوما.ً` بدل `يوماً.`

### ٧. تنظيف نهائي

حذف رموز التحكم الاتجاهي (`200E` `200F` `202A-202E` `2066-2069` `00AD` `FEFF`)، وتطبيع `NFC`، وإزالة المسافة بعد فتح القوس وقبل إغلاقه وقبل علامات الترقيم، وتوحيد الشرطة المائلة بين رقمين، وتحويل `1442 هـ` إلى `1442هـ`.

### ٨. البنية

- **العناوين** — بحجم الخط مقارنًا بحجم المتن الغالب، أو بأنماط `الباب / الفصل / المادة` في نمط الأنظمة السعودية
- **الفقرات** — تُلَمّ الأسطر المكسورة في فقرة واحدة بالاعتماد على الفجوة الرأسية (`> 0.75 ×` ارتفاع السطر يبدأ فقرة)
- **البنود المرقّمة** — `1-` و`3/1-` تُحفظ بترقيمها الأصلي دون إعادة ترقيم
- **الحواشي** — تُلتقط بحجم الخط الأصغر في النصف السفلي، وتُؤجَّل حتى نهاية القسم لئلا تقطع الفقرات
- **الترويسة والتذييل** — تُرصدان بتكرارهما عبر الصفحات وتُحذفان
- **الفهرس الأصلي** — يُتخطّى، ويُولَّد بدلًا منه فهرس بروابط داخلية

---

## التثبيت

</div>

```bash
pip install -r requirements.txt
```

<div dir="rtl">

المتطلبات: `PyMuPDF` و`numpy` و`PyQt6` — وبايثون ٣٫٩ فأحدث. (`PyQt6` لازم للواجهة فقط؛ سطر الأوامر يعمل بدونه.)

## التشغيل

| الطريقة | الأمر |
|---|---|
| الواجهة الرسومية | `python main.py` |
| ويندوز | نقرًا مزدوجًا على `run.bat` |
| لينكس/ماك | `./run.sh` |
| سطر الأوامر | `python main.py ملف.pdf -o مخرج.md` |

`run.bat` و`run.sh` يكتشفان مسار المشروع ويثبّتان المتطلبات تلقائيًّا لو كانت ناقصة.

### أمثلة سطر الأوامر

</div>

```bash
# فحص تشخيصي قبل التحويل
python main.py كتاب.pdf --diag

# نظام سعودي بعناوين الباب/الفصل/المادة
python main.py نظام.pdf --profile saudi_law --title "نظام العمل" -o نظام.md

# نطاق صفحات + وضع سريع بلا فحص حبر
python main.py كتاب.pdf --pages 20-60 --no-ink -o جزء.md

# دفعة كاملة إلى مجلد
python main.py *.pdf -o ./md/

# كل الخيارات
python main.py --help
```

<div dir="rtl">

---

## الواجهة

| العنصر | الوظيفة |
|---|---|
| **قائمة الملفات** | إضافة بالسحب والإفلات أو بالزر — تحويل دُفعي في طابور |
| **نمط المستند** | `تلقائي` بحجم الخط، `نظام سعودي` بالأنماط، `نص عادي` بلا عناوين |
| **مستوى العناوين** | تحديد `##` و`###` أو أي مستوى آخر |
| **نطاق الصفحات** | للتجربة على جزء قبل تحويل الملف كاملًا |
| **فجوة الفقرة** | ضبط حساسية لَمّ الأسطر في فقرة |
| **الحواشي** | اقتباس منفصل `>` أو ضمن النص أو حذف |
| **زر الفحص التشخيصي** | جدول قبل/بعد لثماني كلمات مؤشّرة + عيّنة نص + هل الملف مصوّر يحتاج OCR |
| **تبويب المعاينة** | الناتج مباشرة قبل الحفظ |
| **تبويب السجل** | تفاصيل التنفيذ وأي أخطاء |

التحويل يعمل في `QThread` منفصل، فالواجهة لا تتجمّد. الواجهة عربية كاملة الاتجاه (RTL)، بخط `Amiri` للعناوين و`Cairo` للمتن.

---

## ثوابت المعايرة

مستخرَجة من قياس فعلي على ٢٨ ألف فجوة في مستندات حقيقية، وموضعها `src/core.py`:

| الثابت | القيمة | المعنى |
|---|---|---|
| `ZERO_W` | `0.05` | عرض يُعتبر صفرًا — كشف نصف الرباط |
| `GAP_RATIO` | `0.13` | فجوة ÷ حجم الخط تُعدّ مسافة |
| `INK_MAX` | `0.06` | كثافة حبر تكشف المسافة الوهمية |
| `INK_BAND` | `0.78` | نطاق السطر المفحوص — نتجاهل الذيول والتسطير |
| `Y_TOL` | `0.55` | تسامح رأسي لتجميع السطر البصري |
| `CELL_GAP` | `6.0` | فجوة أفقية تفصل خلايا الجدول |
| `INK_DPI` | `150` | دقة رسم الصفحة لفحص الحبر |

عدِّلها إن واجهت ملفًا بخصائص مختلفة جذريًّا.

---

## الحدود المعروفة

- **الملفات المصوّرة** (بلا طبقة نص) خارج نطاق الأداة — تحتاج OCR أولًا، والفحص التشخيصي يخبرك بذلك.
- **الجداول متعددة الأعمدة** تخرج كل خلية في سطر مستقل — مقروءة، لكنها ليست جدول Markdown.
- **الأخطاء المطبعية في الأصل** تُنقل كما هي — الأداة أمينة للمصدر ولا تصحّح المحتوى.
- الأداة موجَّهة للعربي، لكنها تكتشف الأسطر اللاتينية تلقائيًّا وتعاملها من اليسار لليمين.

---

## البنية

</div>

```
PDF2MD/
├── main.py           نقطة الدخول: بلا وسائط يفتح الواجهة، مع وسائط يشتغل CLI
├── run.bat           مشغّل ويندوز — يثبّت المتطلبات تلقائيًا
├── run.sh            مشغّل لينكس/ماك — يثبّت المتطلبات تلقائيًا
├── requirements.txt
├── README.md
├── LICENSE
└── src/
    ├── core.py       محرّك الاستخراج — الرباطات، الاتجاه، الحبر، المسافات
    ├── structure.py  طبقة البنية — العناوين، الفقرات، الحواشي، الأنماط
    ├── gui.py        واجهة PyQt6
    └── cli.py        منطق سطر الأوامر
```

<div dir="rtl">

`main.py` يضيف `src` إلى `sys.path`، فالاستيرادات داخل `src` مطلقة (`import core`) لا نسبية، ولا حاجة لتشغيل المشروع كحزمة.

`core.py` مستقل تمامًا ويمكن استعماله وحده:

</div>

```python
import sys
sys.path.insert(0, "src")

import fitz
import core

doc = fitz.open("ملف.pdf")
for line in core.page_lines(doc[0]):
    print(line["text"], line["size"], line["bold"])
```

<div dir="rtl">

أو طبقة البنية كاملة:

</div>

```python
import sys
sys.path.insert(0, "src")

from structure import Options, convert, diagnose

md, stats = convert("ملف.pdf", Options(profile="saudi_law", title="عنوان"))
report = diagnose("ملف.pdf")
```

<div dir="rtl">

---

## الرخصة

[MIT](LICENSE) — © 2026 Abdulkarim ([abosalehg-ui](https://github.com/abosalehg-ui))

</div>

---

<a name="english"></a>

# PDF2MD — English

A desktop tool that extracts **correct Arabic text** from broken PDFs and converts it to **structured Markdown**.

## The problem

Arabic PDFs exported from Word and then processed through macOS/iOS (the Quartz engine) — extremely common for Arabic books, statutes and official documents — carry a broken `ToUnicode` map: **Arabic ligatures are stored in reversed order**.

| Correct | What actually comes out |
|---|---|
| المادة | املادة |
| اللائحة | الالئحة |
| المملكة | اململكة |
| الأول | األول |
| وتاريخ | واتريخ |

`pdftotext`, `PyMuPDF`, `Marker` and every web converter reproduce this corruption, because the defect is in the file, not the tool. A single book can contain **over twelve thousand** corrupted words.

## How it works

No dictionary, no guessing. Every fix is a geometric rule derived from glyph coordinates and from the rendered pixels of the page.

1. **Reversed ligatures** — the first glyph of a ligature pair is exported with **zero width** and the pair is stored backwards. Any zero-width glyph that is not a diacritic is swapped with the glyph that follows it, yielding `chars[i+1] + chars[i]`. The rule is general — it is not tied to the letter *lam* — so it covers `لا` `لأ` `لإ` `لآ` `لم` `لح` `لج` `لخ` `تا` `با` `في` and any other ligature in any font.

2. **Visual line reconstruction** — PyMuPDF splits a line at every direction change. Fragments are merged into one visual line when **both** hold: vertical proximity (`y`-centre delta ≤ `0.55 ×` max height) **and** no horizontal overlap (< 50% of the narrower width). The overlap test runs against **each fragment individually**, not the combined box — otherwise numbers sitting between two Arabic fragments get rejected. Line direction: descending by `x1` if any Arabic letter is present, ascending by `x0` otherwise.

3. **Ink probe — phantom spaces** — some spaces exist in the text stream but are never painted, because a glyph is drawn over them, producing `يقتض ي` / `الأ صلي` / `المرسو م`. The page is rasterised at 150 DPI greyscale (pixel < 128 = ink). For each candidate space between two Arabic glyphs, the region between the left glyph's `x1` and the right glyph's `x0` is shrunk 30% on each side and clipped to the top 78% of the line (ignoring descenders and underlines). Measured in practice: real spaces ≤ 2% ink, phantom spaces 9–21% — the `0.06` threshold separates them with wide margin on both sides.

4. **Gap-inferred spaces** — threshold `gap ÷ font size > 0.13`, from a distribution measured over 28,000 gaps (81% of intra-word gaps < `0.02`; inter-word gaps ≥ `0.13`). Gap-inferred spaces are passed through the ink probe too, otherwise the gap rule re-inserts the phantom space the probe just removed.

5. **Number ordering** — digits are LTR inside RTL text, so they come out reversed after visual sorting. Each numeric/Latin run is reversed back. Arabic-Indic `٠-٩` and Extended `۰-۹` digits count as strong LTR just like `0-9`, since they appear mixed within a single number. Numeric separators `/ . , : -` between two digits join the same run. Any space trapped between digits or numeric separators is dropped — it would otherwise break a date into `6/5/1436` instead of `1436/6/5`. Units inside a reversed run are marked *glue* so the gap rule cannot re-insert a space inside the number.

6. **Floating diacritics** — diacritics are exported as separate units and may **precede** their base letter in the stream. Each mark is bound to the Arabic letter that geometrically contains its position (nearest Arabic letter to the mark's centre), not to the previous letter in the stream. Without this you get `يوما.ً` instead of `يوماً.`

7. **Final cleanup** — strip bidi control characters (`200E` `200F` `202A-202E` `2066-2069` `00AD` `FEFF`), apply `NFC`, remove spaces after opening and before closing brackets and before punctuation, normalise the slash between digits, and join `1442 هـ` into `1442هـ`.

8. **Structure** — headings by font size (or `الباب / الفصل / المادة` patterns in the Saudi-law profile); broken lines reflowed into paragraphs by vertical gap; numbered items kept with their original numbering; footnotes captured by smaller font size in the lower half and deferred to the end of the section; repeated headers/footers detected by recurrence across pages and dropped; the original table of contents skipped and replaced by a generated one with internal links.

## Install & run

```bash
pip install -r requirements.txt

python main.py                          # GUI
python main.py file.pdf -o out.md       # CLI
python main.py file.pdf --diag          # diagnostic report
python main.py --help                   # all options
```

On Windows double-click `run.bat`; on Linux/macOS run `./run.sh`. Both locate the project directory themselves and install missing requirements automatically.

## Calibration constants

Located in `src/core.py`:

| Constant | Value | Meaning |
|---|---|---|
| `ZERO_W` | `0.05` | width treated as zero — ligature half detection |
| `GAP_RATIO` | `0.13` | gap ÷ font size that counts as a space |
| `INK_MAX` | `0.06` | ink density that reveals a phantom space |
| `INK_BAND` | `0.78` | portion of the line probed — ignores descenders/underlines |
| `Y_TOL` | `0.55` | vertical tolerance for visual line grouping |
| `CELL_GAP` | `6.0` | horizontal gap separating table cells |
| `INK_DPI` | `150` | rasterisation DPI for the ink probe |

## Known limits

- **Scanned files** (no text layer) are out of scope — they need OCR first; the diagnostic tells you so.
- **Multi-column tables** emit one cell per line — readable, but not a Markdown table.
- **Typos in the source** are carried through verbatim; the tool is faithful to the source and does not correct content.
- Arabic-oriented, but Latin-only lines are detected automatically and treated left-to-right.

## Layout

```
PDF2MD/
├── main.py           entry point: no args → GUI, args → CLI
├── run.bat           Windows launcher — auto-installs requirements
├── run.sh            Linux/macOS launcher — auto-installs requirements
├── requirements.txt
├── README.md
├── LICENSE
└── src/
    ├── core.py       extraction engine — ligatures, direction, ink, spacing
    ├── structure.py  structure layer — headings, paragraphs, footnotes, profiles
    ├── gui.py        PyQt6 interface
    └── cli.py        command-line logic
```

`main.py` adds `src` to `sys.path`, so imports inside `src` are absolute (`import core`) rather than relative, and the project never needs to run as a package.

## License

[MIT](LICENSE) — © 2026 Abdulkarim ([abosalehg-ui](https://github.com/abosalehg-ui))
