"""
Disk Cleaner Pro — منظّف القرص برو

التشغيل:
    python3 main.py
    python3 main.py --selftest     # اختبار ذاتي سريع
    python3 main.py --autoclean    # تنظيف تلقائي بدون واجهة (يستخدمه وكيل macOS)
"""

import sys

if sys.version_info < (3, 9):
    sys.exit("يحتاج البرنامج Python 3.9 أو أحدث.")

# وضع التنظيف التلقائي في الخلفية (يشغّله وكيل macOS) — بدون واجهة
if "--autoclean" in sys.argv:
    from cleaner.core.autoclean import cli_main
    sys.exit(cli_main())

try:
    import customtkinter  # noqa: F401
    import PIL  # noqa: F401
except ImportError:
    sys.exit("المكتبات غير مثبتة. نفّذ:  pip3 install -r requirements.txt")


def main():
    if "--selftest" in sys.argv:
        from cleaner.selftest import run_selftest
        sys.exit(run_selftest())
    from cleaner.ui.app import run
    run()


if __name__ == "__main__":
    main()
