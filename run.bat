@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem PDF2MD - مشغّل ويندوز.
rem يكتشف مسار نفسه، ويثبّت المتطلبات تلقائيًا لو كانت ناقصة، ثم يشغّل الأداة.
rem
rem   run.bat                     الواجهة الرسومية
rem   run.bat ملف.pdf -o out.md   سطر الأوامر

set "PY=python"
where python >nul 2>nul
if errorlevel 1 (
    set "PY=py -3"
    where py >nul 2>nul
    if errorlevel 1 (
        echo لم يُعثر على Python. ثبّته أولًا من https://www.python.org/downloads/
        echo واحرص على تفعيل الخيار "Add Python to PATH" أثناء التثبيت.
        pause
        exit /b 1
    )
)

rem الفحص بالاسم الجديد pymupdf مع سقوط إلى fitz - مثل core.py تمامًا. لو بقي
rem على fitz وحده لأعاد التثبيت في كل تشغيل بعد إزالة الاسم المهجور.
%PY% -c "import numpy, PyQt6; exec('try:\n import pymupdf\nexcept ImportError:\n import fitz')" >nul 2>nul
if errorlevel 1 (
    echo المتطلبات ناقصة - جارٍ تثبيتها من requirements.txt ...
    %PY% -m pip install -r "%~dp0requirements.txt"
    if errorlevel 1 (
        echo فشل التثبيت العام - إعادة المحاولة على مستوى المستخدم ...
        %PY% -m pip install --user -r "%~dp0requirements.txt"
        if errorlevel 1 (
            echo تعذّر تثبيت المتطلبات. راجع الرسائل أعلاه.
            pause
            exit /b 1
        )
    )
)

%PY% "%~dp0main.py" %*
set "RC=%ERRORLEVEL%"

rem النافذة تبقى مفتوحة عند الخطأ فقط، حتى لا تعترض التشغيل الدُفعي
if not "%RC%"=="0" pause
exit /b %RC%
