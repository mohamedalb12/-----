"""
compile_native.py — تحويل كود البرنامج إلى كود آلة (Native) لحمايته من النسخ.

يحوّل كل ملفات cleaner/*.py (عدا ملفات __init__.py البسيطة) إلى مكتبات مُجمّعة
(.so) باستخدام Cython. ملف التطبيق النهائي لا يحتوي على كود Python قابل للقراءة،
بل كود آلة مثل البرامج المكتوبة بلغة C — استرجاع الكود الأصلي منه شبه مستحيل.

    python3 tools/compile_native.py

النتيجة في مجلد build_native/ ويستخدمها DiskCleanerPro.spec تلقائياً.
"""

import glob
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "cleaner")
OUT = os.path.join(ROOT, "build_native")

DIRECTIVES = [
    "language_level=3",
    "annotation_typing=False",      # تجاهل التلميحات (نحافظ على سلوك Python تماماً)
    "binding=True",
    "always_allow_keywords=True",
    "embedsignature=False",
    "emit_code_comments=False",     # لا ننسخ أسطر الكود الأصلي داخل ملفات C
]


def main() -> int:
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    shutil.copytree(SRC, os.path.join(OUT, "cleaner"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    sources = [p for p in glob.glob(os.path.join(OUT, "cleaner", "**", "*.py"), recursive=True)
               if os.path.basename(p) != "__init__.py"]
    cmd = [sys.executable, "-m", "Cython.Build.Cythonize", "-i", "-q", "-j", str(os.cpu_count() or 2)]
    for d in DIRECTIVES:
        cmd += ["-X", d]
    cmd += sources
    print(f"==> تجميع {len(sources)} ملف إلى كود آلة...")
    subprocess.run(cmd, check=True, cwd=OUT)
    # حذف ملفات Python و C الوسيطة — يبقى فقط .so وملفات __init__.py
    for p in sources:
        base = p[:-3]
        if not glob.glob(base + ".*.so") and not glob.glob(base + ".*.pyd"):
            print(f"✘ لم يتم تجميع {p}")
            return 1
        os.remove(p)
        for ext in (".c", ".html"):
            if os.path.exists(base + ext):
                os.remove(base + ext)
    shutil.rmtree(os.path.join(OUT, "build"), ignore_errors=True)
    print(f"✅ تم: {len(sources)} وحدة مُجمّعة في {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
