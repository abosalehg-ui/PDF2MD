# PDF2MD

<div dir="rtl">

أداة لاستخراج **نص عربي سليم** من ملفات PDF المعطوبة، وتحويله إلى **Markdown منظَّم** — بثلاث واجهات فوق محرّك واحد: سطر أوامر، وتطبيق سطح مكتب، و**صفحة ويب تعمل بلا خادم**.

🌐 **[جرّبها في المتصفّح](https://abosalehg-ui.github.io/PDF2MD/)** — بلا تثبيت وبلا رفع: ملفك لا يغادر جهازك.

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

الرباط يُرسم بجليف واحد، فتخرج حروفه كلها عدا الأخير بعرض **صفر** لأنها ملتصقة بالجليف — وترتيبها في مجرى النص بصريّ، أي معكوس عن الترتيب المنطقي.

القاعدة: كل تتابع من الحروف عرضها صفر (وليست تشكيلًا) يليه حرف حامل للصندوق ← يخرج الحرف الحامل ثم حروف التتابع **معكوسة**.

التتابع لا يُقيَّد بحرف واحد: `الله` جليف واحد يبتلع `ه ل ل` بعرض صفر ثم الألف بالصندوق كاملًا، فالمبادلة الثنائية وحدها كانت تنتج `لهال`.

القاعدة عامة ولا تُقيَّد بحرف اللام، فتغطي تلقائيًّا: `لا` `لأ` `لإ` `لآ` `لم` `لح` `لج` `لخ` `تا` `با` `في` `لله` وأي رباط آخر في أي خط.

### ٢. حذف العلامة المائية

التوقيع أو الختم أو شعار الجهة يُرسم فوق المتن أو خلفه بميل وشفافية، فتتقاطع إحداثياته مع أسطر المتن. وبما أن بناء الأسطر يضمّ الأجزاء حسب مركزها الرأسي، فإن جزءًا مائلًا يعبر عشرة أسطر **يُحشر داخل كل سطر يمرّ به**: النص يتقطّع، والكلمات تلتحم، وأسطر المتن القصيرة الناتجة تُقرأ عناوين. لذلك يُحذف قبل الضمّ لا بعده.

الرصد بثلاث علامات مستقلة — أي واحدة تكفي:

| العلامة | القاعدة | لماذا |
|---|---|---|
| الشفافية | `alpha < 60%` | المتن يُطبع معتمًا، فالباهت طبقة زخرفية لا محتوى |
| اللون | لمعان اللون `> 0.62` | أكثر الأختام تُرسم رماديًا **معتمًا** لا شفافًا |
| الميل | انحراف اتجاه السطر عن الأفق `> 0.08` | المتن أفقي، والمائل ختم أو توقيع |

**لماذا اللون علامة مستقلة:** ختم «صورة طبق الأصل» يُرسم غالبًا بلون رمادي معتم (`alpha=255`)، فلا تمسكه الشفافية. وهو ينجو كبير الخط فيُصنَّف **عنوانًا** ويدخل الفهرس المولَّد — أي أن تركه لا يبقيه في الناتج فحسب، بل يلوّث بنية المستند كلها.

**حارس الميل:** لو كانت كل أسطر الصفحة مائلة فالصفحة نفسها مائلة (مسح ضوئي مائل أو صفحة عرضية بلا `/Rotate`)، فلا يُحذف شيء — الميل يميّز العلامة عن المتن فقط حين يوجد متن أفقي تُقارن به.

يُعطَّل بـ `--keep-watermark`.

### ٣. إعادة بناء السطر البصري

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

### ٤. فحص الحبر — كشف المسافات الوهمية

بعض المسافات موجودة في مجرى النص لكنها **لا تُرسم**، لأن الحرف مرسوم فوق موضعها — فتخرج `يقتض ي` و`الأ صلي` و`المرسو م`.

تُرسم الصفحة بدقّة ١٥٠ نقطة/بوصة رماديًّا، ويُعدّ البكسل الأغمق من ١٢٨ حبرًا. ولكل مسافة مرشّحة بين حرفين عربيين تُؤخذ المنطقة بين `x1` للحرف الأيسر و`x0` للحرف الأيمن، وتُقلَّص ٣٠٪ من كل جهة، ويُحدّ نطاقها الرأسي بأعلى ٧٨٪ من السطر (تجاهلًا للذيول والتسطير)، ثم يُقصر على امتداد الحرفين نفسيهما.

القصر على امتداد الحرفين ضروري: نطاق السطر يبدأ من أعلى وحدة فيه، فحرفٌ واحد مرفوع (بداية فقرة بخط عريض مثلًا) يرفع سقف السطر كله فوق المتن، فيدخل في النطاق **تسطير السطر السابق** — وهو خط ممتد يعبر كل الفجوات، فتُحذف مسافات الكلمات في السطر بأكمله وتخرج `فيما يتعلقبدفعوكيلالمدعى عليها`.

القياس الفعلي:

| | كثافة الحبر |
|---|---|
| مسافة حقيقية | ≤ ٢٪ |
| مسافة وهمية | ٩–٢١٪ |

فالعتبة `0.06` تفصل بينهما بهامش واسع من الجهتين. (هذا الخيار يُبطئ المعالجة نحو ٣×، ويمكن تعطيله.)

### ٥. المسافات من الفجوات

العتبة: `الفجوة ÷ حجم الخط > 0.13`. (توزيع مقيس على ٢٨ ألف فجوة: داخل الكلمة < `0.02` بنسبة ٨١٪، وبين الكلمات ≥ `0.13`.)

المسافات المستنبطة من الفجوات تمرّ هي أيضًا على فحص الحبر، وإلا أعادت قاعدة الفجوة إدراج المسافة الوهمية بعد حذفها.

### ٦. ترتيب الأرقام والتواريخ

الأرقام تُكتب من اليسار لليمين داخل نص RTL، فتخرج معكوسة بعد الترتيب البصري. تُكتشف التسلسلات الرقمية/اللاتينية وتُعكس لتعود لترتيبها المنطقي:

- الأرقام الهندية `٠-٩` والفارسية `۰-۹` تُعامل معاملة `0-9` كأرقام قوية، لأنها تظهر مختلطة في العدد نفسه.
- الفواصل العددية `/ . , : -` بين رقمين تُضمّ داخل التسلسل نفسه.
- أي مسافة محصورة بين رقمين أو فواصل عددية تُسقط، لأنها تكسر التاريخ فيخرج `6/5/1436` بدل `1436/6/5`.
- الوحدات داخل التسلسل المعكوس تُعلَّم `glue` حتى لا تعيد قاعدة الفجوة إدراج مسافة داخل العدد.

### ٧. التشكيل الطائر

علامات التشكيل تُصدَّر منفصلة وقد **تسبق** حرفها في المجرى. تُربط كل علامة بالحرف العربي الذي يحتوي موقعها إحداثيًّا (أقرب حرف عربي لمركز العلامة). بدون ذلك تخرج `يوما.ً` بدل `يوماً.`

### ٨. تنظيف نهائي

حذف رموز التحكم الاتجاهي (`200E` `200F` `202A-202E` `2066-2069` `00AD` `FEFF`)، وتطبيع `NFC`، وإزالة المسافة بعد فتح القوس وقبل إغلاقه وقبل علامات الترقيم، وتوحيد الشرطة المائلة بين رقمين، وتحويل `1442 هـ` إلى `1442هـ`.

### ٩. البنية

- **العناوين** — بحجم الخط مقارنًا بحجم المتن الغالب، أو بأنماط `الباب / الفصل / المادة` في نمط الأنظمة السعودية
- **الفقرات** — تُلَمّ الأسطر المكسورة في فقرة واحدة بالاعتماد على الفجوة الرأسية (`> 0.75 ×` ارتفاع السطر يبدأ فقرة)
- **البنود المرقّمة** — `1-` و`3/1-` تُحفظ بترقيمها الأصلي دون إعادة ترقيم
- **الحواشي** — تُلتقط بحجم الخط الأصغر في النصف السفلي، وتُؤجَّل حتى نهاية القسم لئلا تقطع الفقرات
- **الترويسة والتذييل** — تُرصدان بتكرارهما عبر الصفحات وتُحذفان
- **العلامة المائية** — توقيع أو ختم أو شعار جهة، تُرصد بالشفافية أو بالميل وتُحذف قبل ضمّ الأسطر (القسم ٢ أعلاه)
- **الفهرس الأصلي** — يُتخطّى، ويُولَّد بدلًا منه فهرس بروابط داخلية (المراسي مصغَّرة الحروف ومفضوضة التعارض، فالعناوين المتكررة لا تشترك في مرساة واحدة)
- **الجداول** — صفوف الجدول المرصودة هندسيًا (أربعة أجزاء فأكثر تفصلها فجوات أوسع من `CELL_GAP`) تُجمَّع في جدول Markdown حقيقي؛ صفّان متتاليان على الأقل، والصف المعزول يبقى فقرة

العنوان يشترط **شكل العنوان** لا مجرد كِبَر حجم الخط: الجملة المنتهية بنقطة أو فاصلة ليست عنوانًا مهما كبر خطها. بدون هذا الشرط تنقلب صفحة محشوّة بنص صغير كثيف فيصير متنها عناوين.

---

## التثبيت

</div>

```bash
pip install -r requirements.txt
```

<div dir="rtl">

المتطلبات: `PyMuPDF` و`numpy` و`PyQt6` — وبايثون ٣٫٩ فأحدث. (`PyQt6` لازم للواجهة فقط؛ سطر الأوامر يعمل بدونه.)

**تنبيه:** `run.sh` و`run.bat` يثبّتان المتطلبات تلقائيًا عند أول تشغيل على مستوى النظام أو المستخدم، لا داخل بيئة معزولة. هذا يريح الجمهور غير التقني، لكنه يخلط اعتماديات المشروع بغيرها. من يفضّل العزل يثبّت يدويًا:

</div>

```bash
python -m venv .venv
source .venv/bin/activate        # ويندوز: .venv\Scripts\activate
pip install -r requirements.txt
```

<div dir="rtl">

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

# صفحة واحدة — رقم مجرّد بلا نطاق
python main.py كتاب.pdf --pages 12 -o صفحة.md

# مسار بلا امتداد .md يُعدّ مجلدًا يُكتب فيه باسم ملف PDF
python main.py كتاب.pdf -o ./md

# دفعة كاملة إلى مجلد — الملف الفاشل يُتخطّى ولا يوقف البقية
python main.py *.pdf -o ./md/

# الكتابة فوق مخرَج موجود مسبقًا تتطلب إذنًا صريحًا
python main.py كتاب.pdf --force

# تعطيل بناء الجداول — صفوف الجداول تخرج فقرات
python main.py تقرير.pdf --no-tables -o تقرير.md

# إبقاء نص العلامة المائية (التوقيع أو الختم) بدل حذفه
python main.py مذكرة.pdf --keep-watermark -o مذكرة.md

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
| **الجداول** | تجميع صفوف الجداول المرصودة في جداول Markdown — يمكن تعطيله |
| **تبويب المعاينة** | الناتج مباشرة قبل الحفظ |
| **تبويب السجل** | تفاصيل التنفيذ وأي أخطاء |

التحويل يعمل في `QThread` منفصل، فالواجهة لا تتجمّد، والفحص التشخيصي قابل للإيقاف مثله. الواجهة عربية كاملة الاتجاه (RTL)، بخط `Amiri` للعناوين و`Cairo` للمتن.

الاختيارات (النمط، الحواشي، مجلد الحفظ، مستويات العناوين، مربّعات الخيارات، وحجم النافذة) **تُحفظ تلقائيًا** عند الخروج وتُستعاد عند التشغيل التالي، فلا يُعاد ضبطها كل مرة.

---

## واجهة الويب — بلا تثبيت وبلا خادم

**[abosalehg-ui.github.io/PDF2MD](https://abosalehg-ui.github.io/PDF2MD/)**

الصفحة ليست نسخة ثانية من الأداة، بل **الأداة نفسها**: ملفات `src/*.py` التي يشغّلها سطر الأوامر وتطبيق سطح المكتب تُنزَّل إلى المتصفّح وتُنفَّذ فيه حرفيًا بلا تعديل، فوق مفسّر بايثون مُصرَّف إلى WebAssembly ([Pyodide](https://pyodide.org)) ومعه PyMuPDF و numpy بالصيغة نفسها. الناتج مطابق بايتًا ببايت لما يخرج من `python main.py`، لأن الشيفرة واحدة لا نظيرتان.

| | |
|---|---|
| **الخصوصية** | الملف يُقرأ في المتصفّح ولا يُرفع. سياسة أمن المحتوى في الصفحة `connect-src 'self'` — أي أن الصفحة **لا تملك إذن** الاتصال بأي خادم خارجي، فالوعد مضمون تقنيًا لا لفظيًا |
| **بلا شبكة توصيل محتوى** | زمن التشغيل مستضاف ذاتيًا مع الصفحة، وكل ملف يُتحقّق من بصمة sha256 قبل النشر |
| **أول تشغيل** | ~٣٢ م.ب تُنزَّل مرة واحدة ثم تُخزَّن في المتصفّح — الزيارات التالية تُقلع في ثوانٍ |
| **بلا تجمّد** | التحويل يجري في `Web Worker` منفصل، والتقدّم يُبثّ صفحةً صفحة |
| **الإيقاف** | يُنهي الخيط ويُقلع بديلًا من الذاكرة المؤقتة — بايثون داخل Pyodide لا يُقاطَع بلا `SharedArrayBuffer`، وهي تتطلّب ترويستَي COOP/COEP لا ترسلهما GitHub Pages |
| **الدفعات** | قائمة ملفات كاملة، وتنزيل الناتج مفردًا `.md` أو مجموعًا `.zip` |

كل خيارات `Options` معروضة في الصفحة كما في تطبيق سطح المكتب، وتُحفظ في `localStorage` فلا يُعاد ضبطها كل زيارة.

### التشغيل محليًا

</div>

```bash
python3 tools/fetch_web_runtime.py   # ينزّل زمن التشغيل إلى web/vendor/ (مرة واحدة)
python3 tools/serve.py               # http://127.0.0.1:8000
```

<div dir="rtl">

`web/vendor/` خارج المستودع (٣٢ م.ب من الثنائيات). و`tools/build_site.py` يجمّع `_site/` للنشر، وهو ما يشغّله سير عمل `.github/workflows/pages.yml` عند كل دفعة إلى `main`.

**لتفعيل النشر مرة واحدة:** Settings → Pages → Build and deployment → Source = **GitHub Actions**.

### حدود واجهة الويب

- **البطء**: التنفيذ داخل WebAssembly أبطأ من بايثون الأصلي (٢–٣× تقريبًا). الكتب الكبيرة تُحوَّل أسرع في سطر الأوامر.
- **الذاكرة**: لسان المتصفّح محدود الذاكرة أكثر من العملية الأصلية — الملفات الضخمة جدًا قد تفشل هنا وتنجح على سطح المكتب.
- **الحفظ**: الناتج يُنزَّل إلى مجلد التنزيلات، فلا يُكتب بجانب ملف PDF كما في `-o`.
- **متصفّح حديث** لازم: WebAssembly و`Web Worker` والوحدات النمطية (ES modules).

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
| `WM_ALPHA` | `0.60` | شفافية دونها يُعدّ النص علامة مائية |
| `WM_LUMA` | `0.62` | لمعان لون أعلى منه = ختم رمادي باهت لا متن |
| `WM_TILT` | `0.08` | انحراف اتجاه السطر عن الأفق يُعدّ ميلًا |
| `INK_PAD` | `0.30` | نسبة تقليص الفجوة من كل جهة قبل قياس الحبر |
| `SEG_CLASH` | `0.50` | تداخل أفقي فوقه لا يُضمّ الجزآن في سطر واحد |
| `INK_MAX_PIXELS` | `40M` | سقف بكسلات الصفحة المرسومة — فوقه تنزل الدقة |

عدِّلها إن واجهت ملفًا بخصائص مختلفة جذريًّا.

---

## الحدود المعروفة

- **الملفات المصوّرة** (بلا طبقة نص) خارج نطاق الأداة — تحتاج OCR أولًا، والفحص التشخيصي يخبرك بذلك.
- **كشف الجداول هندسي** — الصف يحتاج أربعة أجزاء فأكثر تفصلها فجوات أوسع من `CELL_GAP`، ويحتاج صفّين متتاليين على الأقل ليصير جدولًا. الجداول غير المنتظمة أو المدموجة الخلايا تخرج فقرات، و`--no-tables` تعطّل الميزة كليًا.
- **الأخطاء المطبعية في الأصل** تُنقل كما هي — الأداة أمينة للمصدر ولا تصحّح المحتوى.
- الأداة موجَّهة للعربي، لكنها تكتشف الأسطر اللاتينية تلقائيًّا وتعاملها من اليسار لليمين.
- **الكتب الضخمة جدًّا** (ألف صفحة فأكثر): أسطر المستند كله تُحمَّل في الذاكرة قبل البناء، لأن حساب حجم المتن الغالب والترويسات المتكررة يحتاج المستند كاملًا.
- **الملفات المحمية بكلمة مرور** تُرفض برسالة واضحة — أزل الحماية أولًا.
- **الصفحات العملاقة** (أكبر من ٤٠ مليون بكسل عند ١٥٠ نقطة/بوصة) تُرسم بدقة أدنى تلقائيًا في فحص الحبر، حمايةً من نفاد الذاكرة. الفحص عليها أقل دقة، وبقية المسار لا يتأثر.

---

## الخصوصية

المعالجة **محلية بالكامل**. الأداة لا تتصل بالشبكة إطلاقًا أثناء التحويل، ولا ترفع شيئًا، ولا تكتب ملفات مؤقتة. الناتج يُكتب بجانب ملف PDF ما لم يُحدَّد `-o`، والشيء الوحيد المحفوظ خارج المخرَجات هو تفضيلات الواجهة (النمط، مجلد الحفظ، مقاس النافذة) في ملف إعدادات المستخدم.

هذا يعني أن تحويل مذكرة أو مرافعة أو وثيقة سرّية لا يخرجها من جهازك. (الاتصال الوحيد بالشبكة في المشروع هو `pip` داخل `run.sh` و`run.bat` عند أول تشغيل لتثبيت المتطلبات.)

**وواجهة الويب ليست استثناءً:** الصفحة تُنزّل محرّكها مرة واحدة ثم تعمل كليًا داخل المتصفّح — الملف لا يُرفع، ولا يوجد خادم تحويل أصلًا. وسياسة أمن المحتوى `connect-src 'self'` تجعل هذا قيدًا يفرضه المتصفّح لا وعدًا في نص.

**قاعدة `-o`:** المسار المنتهي بـ`.md` يُعدّ **ملفًا**، وما عداه يُعدّ **مجلدًا** يُكتب فيه ملف باسم ملف PDF. القاعدة واحدة سواء حوّلت ملفًا أو دفعة.

---

## البنية

</div>

```
PDF2MD/
├── main.py           نقطة الدخول: بلا وسائط يفتح الواجهة، مع وسائط يشتغل CLI
├── run.bat           مشغّل ويندوز — يثبّت المتطلبات تلقائيًا
├── run.sh            مشغّل لينكس/ماك — يثبّت المتطلبات تلقائيًا
├── requirements.txt
├── pyproject.toml    بيانات الحزمة وإعداد ruff و pytest
├── README.md
├── LICENSE
├── index.html        صفحة الويب — تعمل بلا خادم فوق Pyodide
├── src/
│   ├── core.py       محرّك الاستخراج — الرباطات، الاتجاه، الحبر، المسافات، الخلايا
│   ├── structure.py  طبقة البنية — العناوين، الفقرات، الجداول، الحواشي، الأنماط
│   ├── common.py     المشترك بين الواجهات — الحكم التشخيصي ومسار المخرَج
│   ├── gui.py        واجهة PyQt6
│   ├── cli.py        منطق سطر الأوامر
│   └── web.py        جسر واجهة الويب — يعمل داخل المتصفّح، ويُختبر على CPython
├── web/
│   ├── css/styles.css
│   ├── js/app.js     الواجهة
│   ├── js/engine.js  غلاف الخيط العامل
│   ├── js/worker.js  إقلاع Pyodide وتشغيل المحرّك
│   ├── js/zip.js     كاتب ZIP صغير لتنزيل الدفعة
│   ├── runtime.json  إصدارات زمن التشغيل وبصماتها — مصدر الحقيقة الوحيد
│   └── vendor/       زمن التشغيل المُنزَّل — خارج المستودع
├── tools/
│   ├── fetch_web_runtime.py  ينزّل Pyodide و numpy و PyMuPDF بصيغة wasm
│   ├── build_site.py         يجمّع _site/ للنشر
│   └── serve.py              خادم تطوير محلي
└── tests/            اختبارات pytest — تعمل تلقائيًا في GitHub Actions
```

<div dir="rtl">

`src` حزمة بايثون عادية والاستيرادات داخلها نسبية، فتُستورد من جذر المشروع مباشرة. `main.py` وحده يضيف جذر المشروع إلى `sys.path` ليعمل عند تشغيله من مجلد آخر.

`core.py` مستقل تمامًا ويمكن استعماله وحده:

</div>

```python
import fitz
from src import core

doc = fitz.open("ملف.pdf")
for line in core.page_lines(doc[0]):
    print(line["text"], line["size"], line["bold"])
```

<div dir="rtl">

أو طبقة البنية كاملة:

</div>

```python
from src.structure import Options, convert, diagnose

md, stats = convert("ملف.pdf", Options(profile="saudi_law", title="عنوان"))
report = diagnose("ملف.pdf")
```

<div dir="rtl">

## الاختبارات

</div>

```bash
pip install pytest
pytest -q
```

<div dir="rtl">

---

## الرخصة

[MIT](LICENSE) — © 2026 Abdulkarim ([abosalehg-ui](https://github.com/abosalehg-ui))

</div>

---

<a name="english"></a>

# PDF2MD — English

A tool that extracts **correct Arabic text** from broken PDFs and converts it to **structured Markdown** — three front-ends over one engine: a CLI, a desktop app, and a **serverless web page**.

🌐 **[Try it in your browser](https://abosalehg-ui.github.io/PDF2MD/)** — no install, no upload: the file never leaves your machine.

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

1. **Reversed ligatures** — every glyph of a ligature except the last is exported with **zero width**, and the run is stored in visual (reversed) order. Each run of zero-width non-diacritic glyphs followed by a box-carrying glyph is emitted as the carrier followed by the run **reversed**. Runs are not limited to one glyph: `الله` is a single glyph swallowing `ه ل ل` at zero width plus the alef carrying the box, so pairwise swapping alone produced `لهال`. The rule is general — it is not tied to the letter *lam* — so it covers `لا` `لأ` `لإ` `لآ` `لم` `لح` `لج` `لخ` `تا` `با` `في` `لله` and any other ligature in any font.

2. **Watermark removal** — a signature, stamp, or agency logo is painted over or under the body at an angle and with transparency, so its coordinates intersect body lines. Because line building groups fragments by vertical centre, one tilted fragment crossing ten lines is spliced into every line it passes through: text fractures, words fuse, and the resulting short body lines read as headings — so it is dropped before grouping, not after. Three independent signals, any one is enough: transparency (`alpha < 60%` — body text is printed opaque, so faint text is decoration), colour (luminance `> 0.62` — most stamps are painted in **opaque grey** rather than transparent, and surviving at a large font size they get classified as *headings* and pollute the generated table of contents), and tilt (line direction deviating from horizontal by `> 0.08` — body text is horizontal). Tilt guard: if *every* line on the page is tilted, the page itself is tilted (a skewed scan, or a landscape page with no `/Rotate`) and nothing is dropped. Disable with `--keep-watermark`.

3. **Visual line reconstruction** — PyMuPDF splits a line at every direction change. Fragments are merged into one visual line when **both** hold: vertical proximity (`y`-centre delta ≤ `0.55 ×` max height) **and** no horizontal overlap (< 50% of the narrower width). The overlap test runs against **each fragment individually**, not the combined box — otherwise numbers sitting between two Arabic fragments get rejected. Line direction: descending by `x1` if any Arabic letter is present, ascending by `x0` otherwise.

4. **Ink probe — phantom spaces** — some spaces exist in the text stream but are never painted, because a glyph is drawn over them, producing `يقتض ي` / `الأ صلي` / `المرسو م`. The page is rasterised at 150 DPI greyscale (pixel < 128 = ink). For each candidate space between two Arabic glyphs, the region between the left glyph's `x1` and the right glyph's `x0` is shrunk 30% on each side, clipped to the top 78% of the line (ignoring descenders and underlines), and then narrowed to the vertical extent of the two glyphs themselves. That last clip matters: the line band starts at the topmost unit in the line, so a single raised glyph (a bold paragraph opener, say) lifts the band above the body and pulls in **the previous line's underline** — a continuous rule crossing every gap, which deletes the word spaces of the entire line. Measured in practice: real spaces ≤ 2% ink, phantom spaces 9–21% — the `0.06` threshold separates them with wide margin on both sides.

5. **Gap-inferred spaces** — threshold `gap ÷ font size > 0.13`, from a distribution measured over 28,000 gaps (81% of intra-word gaps < `0.02`; inter-word gaps ≥ `0.13`). Gap-inferred spaces are passed through the ink probe too, otherwise the gap rule re-inserts the phantom space the probe just removed.

6. **Number ordering** — digits are LTR inside RTL text, so they come out reversed after visual sorting. Each numeric/Latin run is reversed back. Arabic-Indic `٠-٩` and Extended `۰-۹` digits count as strong LTR just like `0-9`, since they appear mixed within a single number. Numeric separators `/ . , : -` between two digits join the same run. Any space trapped between digits or numeric separators is dropped — it would otherwise break a date into `6/5/1436` instead of `1436/6/5`. Units inside a reversed run are marked *glue* so the gap rule cannot re-insert a space inside the number.

7. **Floating diacritics** — diacritics are exported as separate units and may **precede** their base letter in the stream. Each mark is bound to the Arabic letter that geometrically contains its position (nearest Arabic letter to the mark's centre), not to the previous letter in the stream. Without this you get `يوما.ً` instead of `يوماً.`

8. **Final cleanup** — strip bidi control characters (`200E` `200F` `202A-202E` `2066-2069` `00AD` `FEFF`), apply `NFC`, remove spaces after opening and before closing brackets and before punctuation, normalise the slash between digits, and join `1442 هـ` into `1442هـ`.

9. **Structure** — headings by font size **and heading shape** (a line ending in a full stop is never a heading, however large its font — without that guard a page dense with small text inverts and its body becomes headings), or `الباب / الفصل / المادة` patterns in the Saudi-law profile; broken lines reflowed into paragraphs by vertical gap; numbered items kept with their original numbering; detected table rows assembled into real Markdown tables; footnotes captured by smaller font size in the lower half and deferred to the end of the section; repeated headers/footers detected by recurrence across pages and dropped; watermarks dropped by transparency or tilt; the original table of contents skipped and replaced by a generated one with lowercased, collision-resolved anchors.

## Install & run

```bash
pip install -r requirements.txt

python main.py                          # GUI
python main.py file.pdf -o out.md       # CLI
python main.py file.pdf --diag          # diagnostic report
python main.py --help                   # all options
```

On Windows double-click `run.bat`; on Linux/macOS run `./run.sh`. Both locate the project directory themselves and install missing requirements automatically.

## Web interface — no install, no server

**[abosalehg-ui.github.io/PDF2MD](https://abosalehg-ui.github.io/PDF2MD/)**

The page is not a second implementation — it is *the same* one. The `src/*.py` files the CLI and the desktop app run are fetched into the browser and executed there verbatim, on a Python interpreter compiled to WebAssembly ([Pyodide](https://pyodide.org)) with PyMuPDF and numpy in the same form. Output is byte-for-byte identical to `python main.py`, because there is one codebase, not two.

- **Privacy.** The PDF is read in the browser and never uploaded. The page's Content-Security-Policy is `connect-src 'self'` — it has *no permission* to reach any external server, so the promise is enforced by the browser, not by a sentence in a README.
- **No CDN.** The runtime is self-hosted alongside the page, and every file is sha256-verified before publishing.
- **First visit** downloads ~32 MB once, then the browser caches it; later visits boot in seconds.
- **No freezing.** Conversion runs in a `Web Worker`, streaming progress page by page.
- **Stop** terminates the worker and boots a replacement from cache — Python inside Pyodide cannot be interrupted without a `SharedArrayBuffer`, which needs COOP/COEP headers GitHub Pages does not send.
- **Batches.** A full file queue, with per-file `.md` download or a combined `.zip`.

Every `Options` field is exposed exactly as in the desktop app and remembered in `localStorage`.

Run it locally:

```bash
python3 tools/fetch_web_runtime.py   # download the runtime into web/vendor/ (once)
python3 tools/serve.py               # http://127.0.0.1:8000
```

`web/vendor/` is git-ignored (32 MB of binaries). `tools/build_site.py` assembles `_site/` for publishing, which is what `.github/workflows/pages.yml` runs on every push to `main`. To enable it once: Settings → Pages → Build and deployment → Source = **GitHub Actions**.

**Limits of the web build:** WebAssembly runs roughly 2–3× slower than native Python, a browser tab has less memory than a native process, output lands in the Downloads folder rather than next to the PDF, and a modern browser (WebAssembly, Web Workers, ES modules) is required.

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
| `WM_ALPHA` | `0.60` | opacity below which text counts as a watermark |
| `WM_LUMA` | `0.62` | colour luminance above which text is a faint grey stamp |
| `WM_TILT` | `0.08` | line-direction deviation from horizontal that counts as tilted |
| `INK_PAD` | `0.30` | gap shrink ratio per side before probing ink |
| `SEG_CLASH` | `0.50` | horizontal overlap above which fragments are not one line |
| `INK_MAX_PIXELS` | `40M` | pixel ceiling for the rasterised page — DPI scales down above it |

## Known limits

- **Scanned files** (no text layer) are out of scope — they need OCR first; the diagnostic tells you so.
- **Table detection is geometric** — a row needs four or more fragments separated by gaps wider than `CELL_GAP`, and at least two consecutive rows to become a table. Irregular or merged-cell layouts fall back to paragraphs; `--no-tables` disables the feature entirely.
- **Typos in the source** are carried through verbatim; the tool is faithful to the source and does not correct content.
- Arabic-oriented, but Latin-only lines are detected automatically and treated left-to-right.
- **Very large books** (1000+ pages): the whole document's lines are held in memory before building, because the dominant body font size and the repeated headers can only be computed across the full document.
- **Password-protected files** are rejected with a clear message — remove the protection first.
- **Oversized pages** (above 40M pixels at 150 DPI) are rasterised at a reduced DPI for the ink probe, to avoid exhausting memory. The probe is less precise on those pages; nothing else changes.

## Privacy

Processing is **entirely local**. The tool never touches the network during conversion, uploads nothing, and writes no temporary files. Output goes next to the source PDF unless `-o` says otherwise, and the only thing stored outside the output is the GUI's preferences (profile, output folder, window size) in the user's settings file. Converting a confidential document does not take it off your machine. (The project's only network access is `pip` inside `run.sh` / `run.bat` on first launch.)

**The web build is no exception:** the page downloads its engine once and then runs entirely in the browser — nothing is uploaded, and there is no conversion server to upload to. `connect-src 'self'` makes that a constraint the browser enforces, not a claim in prose.

**The `-o` rule:** a path ending in `.md` is a **file**; anything else is a **directory** that receives a file named after the PDF. The rule is the same for a single file and for a batch.

## Layout

```
PDF2MD/
├── main.py           entry point: no args → GUI, args → CLI
├── run.bat           Windows launcher — auto-installs requirements
├── run.sh            Linux/macOS launcher — auto-installs requirements
├── requirements.txt
├── pyproject.toml    package metadata, ruff and pytest config
├── README.md
├── LICENSE
├── index.html        web page — runs serverless on Pyodide
├── src/
│   ├── core.py       extraction engine — ligatures, direction, ink, spacing, cells
│   ├── structure.py  structure layer — headings, paragraphs, tables, footnotes, profiles
│   ├── common.py     shared across front-ends — diagnostics verdict, output paths
│   ├── gui.py        PyQt6 interface
│   ├── cli.py        command-line logic
│   └── web.py        browser bridge — runs in the browser, tested on CPython
├── web/
│   ├── css/styles.css
│   ├── js/app.js     the interface
│   ├── js/engine.js  worker wrapper
│   ├── js/worker.js  Pyodide boot and engine calls
│   ├── js/zip.js     small ZIP writer for batch download
│   ├── runtime.json  runtime versions and checksums — the single source of truth
│   └── vendor/       downloaded runtime — git-ignored
├── tools/
│   ├── fetch_web_runtime.py  downloads Pyodide, numpy and PyMuPDF as wasm
│   ├── build_site.py         assembles _site/ for publishing
│   └── serve.py              local development server
└── tests/            pytest suite — runs automatically in GitHub Actions
```

`src` is a regular Python package with relative imports inside — use `from src import core` or `from src.structure import Options, convert` from the project root. Only `main.py` prepends the project root to `sys.path`, so it runs from any working directory. Run the tests with `pytest -q`.

## License

[MIT](LICENSE) — © 2026 Abdulkarim ([abosalehg-ui](https://github.com/abosalehg-ui))
