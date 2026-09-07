# -*- coding: utf-8 -*-
"""
gui_theme.py — هوية PDF2MD البصرية في تطبيق سطح المكتب.

اللوحة والثوابت وورقة الأنماط (QSS) في ملف واحد، لأنها تُقرأ وتُعدَّل معًا
ولا علاقة لها بمنطق النافذة. ونظيرها على الويب `web/css/styles.css` —
واللوحتان متطابقتان عمدًا: من استعمل التطبيق يجب أن يتعرّف على الصفحة.

النِّسَب المذكورة في التعليقات محسوبة بمعادلة WCAG على الخلفيتين CREAM
و PANEL، ومثبَّتة في الاختبارات لئلا تُنقض بتعديل لاحق.
"""

from PyQt6.QtCore import Qt

APP_NAME = "PDF2MD"
ORG_NAME = "PDF2MD"

TAGLINE = "استخراج نص عربي سليم من PDF المعطوب الرباطات، وتحويله إلى Markdown منظَّم"

# المسار الكامل يُخزَّن في بيانات عنصر القائمة، ويُعرض اسم الملف وحده
PATH_ROLE = Qt.ItemDataRole.UserRole

# ── لوحة الألوان ──
# النِّسَب أدناه محسوبة بمعادلة WCAG على الخلفيتين CREAM و PANEL.
BROWN = "#6B4423"
GOLD = "#C9A227"
CREAM = "#FAF6EE"
INK = "#2E2418"
LINE = "#E0D6C2"        # إطار زخرفي للمجموعات — 1.4:1، لا يحمل معنى
# ٥٫٠١:١ على خلفية الترويسة #F3EADA التي يظهر عليها حكم التشخيص.
# كان #2E7D52 يعطي ٤٫٢٢:١ — دون ٤٫٥ التي يفرضها WCAG SC 1.4.3.
# اللون نفسه في web/css/styles.css: اللوحة واحدة في الواجهتين.
OK = "#2A7049"
BAD = "#B3261E"
PANEL = "#FFFDF8"

# حدّ عناصر الإدخال. الحقل أبيض على خلفية كريمية (تباين 1.08:1)، فالحدّ هو
# وسيلة تمييزه الوحيدة — وWCAG 2.2 SC 1.4.11 يطلب 3:1 لحدود عناصر التحكم.
# كان LINE (1.44:1 على الأبيض) فلم تكن الحقول تُرى أصلًا. هذا 3.36:1.
FIELD_LINE = "#9C8A66"

# مؤشّر التركيز. GOLD يعطي 2.24:1 على CREAM — دون حدّ SC 1.4.11 نفسه، أي أن
# قاعدة :focus كانت موجودة وغير مرئية عمليًا. هذا 3.52:1 على CREAM
# و3.73:1 على PANEL. ويبقى GOLD لشريط التقدّم والتبويب: عنصران زخرفيان.
GOLD_FOCUS = "#A07F15"

# Amiri للعناوين و Cairo للمتن، مع بدائل مضمونة على كل نظام
SERIF = '"Amiri", "Scheherazade New", "Traditional Arabic", serif'
SANS = '"Cairo", "Segoe UI", "Tahoma", "Noto Sans Arabic", sans-serif'

QSS = f"""
* {{ font-family: {SANS}; font-size: 13px; color: {INK}; }}
QMainWindow, QWidget {{ background: {CREAM}; }}
QLabel#title {{ font-family: {SERIF}; font-size: 30px; font-weight: 700;
                color: {BROWN}; }}
QLabel#tagline {{ color: #7A6A55; }}
QLabel#section {{ font-family: {SERIF}; font-size: 15px; color: {BROWN};
                  font-weight: 700; }}
QGroupBox {{
    border: 1px solid {LINE}; border-radius: 10px; background: {PANEL};
    margin-top: 14px; padding: 12px 10px 10px 10px;
}}
QGroupBox::title {{
    subcontrol-origin: margin; right: 14px; padding: 2px 8px;
    font-family: {SERIF}; font-size: 15px; color: {BROWN}; font-weight: 700;
}}
QPushButton {{
    background: {BROWN}; color: #FFF9EC; border: none;
    border-radius: 8px; padding: 9px 18px; font-weight: 700;
}}
QPushButton:hover {{ background: #7D5230; }}
/* نص الحالة المعطَّلة كان #F2ECE0 على #C4B8A6 — تباين 1.66:1 يكاد يختفي
   أثناء التحويل. #6F6355 يرفعه إلى ~3.1:1 ويبقى واضحًا أنه معطَّل. */
QPushButton:disabled {{ background: #C4B8A6; color: #6F6355; }}
QPushButton#ghost {{ background: transparent; color: {BROWN};
                     border: 1px solid {BROWN}; }}
QPushButton#ghost:hover {{ background: #F0E7D6; }}
QPushButton#gold {{ background: {GOLD}; color: #3A2C08; }}
QPushButton#gold:hover {{ background: #D9B23B; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QListWidget,
QPlainTextEdit, QTableWidget {{
    background: #FFFFFF; border: 1px solid {FIELD_LINE};
    border-radius: 8px; padding: 6px; selection-background-color: {GOLD};
    selection-color: {INK};
}}
/* المعاينة والسجل نصّ عربي يُقرأ لا كود يُحاذى عموديًا — والخط الأحادي
   اللاتيني كان يخرجه مفكّك الوصل لانعدام تغطيته العربية. */
QPlainTextEdit {{ font-family: {SANS}; font-size: 13px; }}
QProgressBar {{
    border: 1px solid {LINE}; border-radius: 8px; height: 20px;
    text-align: center; background: #FFFFFF;
}}
QProgressBar::chunk {{ background: {GOLD}; border-radius: 7px; }}
QTabBar::tab {{
    background: transparent; padding: 8px 18px;
    border-bottom: 3px solid transparent; font-weight: 600;
}}
QTabBar::tab:selected {{ color: {BROWN}; border-bottom: 3px solid {GOLD}; }}
QTabWidget::pane {{ border: 1px solid {LINE}; border-radius: 10px;
                    background: {PANEL}; }}
QHeaderView::section {{
    background: #F3EADA; padding: 6px; border: none;
    border-bottom: 1px solid {LINE}; font-weight: 700; color: {BROWN};
}}
QCheckBox::indicator {{ width: 17px; height: 17px; }}
/* مؤشّر تركيز ظاهر: بدونه يفقد المتنقّل بلوحة المفاتيح موضعه بين ثمانية
   مربّعات اختيار متتالية فوق خلفية كريمية مسطّحة. اللون GOLD_FOCUS لا GOLD
   لأن الأخير 2.24:1 على الخلفية — دون 3:1 التي يفرضها WCAG 2.2 SC 1.4.11
   للمؤشّرات غير النصية، أي أن القاعدة كانت تُطبَّق ولا تُرى. */
QPushButton:focus, QCheckBox:focus, QComboBox:focus, QLineEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QListWidget:focus,
QPlainTextEdit:focus, QTableWidget:focus {{
    border: 2px solid {GOLD_FOCUS};
}}
QTabBar::tab:focus {{ border-bottom: 3px solid {GOLD_FOCUS}; }}
QStatusBar {{ background: #F3EADA; color: {BROWN}; }}
QScrollArea {{ border: none; background: transparent; }}
QSplitter::handle {{ background: transparent; }}
"""
