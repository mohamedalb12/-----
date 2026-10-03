"""صفحات البرنامج بالترتيب الظاهر في الشريط الجانبي: (المفتاح، الأيقونة، الاسم، الصنف، القسم)."""

from .dashboard import DashboardPage
from .duplicates import DuplicatesPage
from .extensions import ExtensionsPage
from .junk import JunkPage
from .large import LargePage
from .maintenance import MaintenancePage
from .monitor import MonitorPage
from .optimization import OptimizationPage
from .privacy import PrivacyPage
from .security import SecurityPage
from .settings import SettingsPage
from .shredder import ShredderPage
from .space import SpacePage
from .uninstaller import UninstallerPage
from .updater import UpdaterPage

PAGES = [
    ("dashboard", "🏠", "الفحص الذكي", DashboardPage, None),
    ("junk", "🧹", "مهملات النظام", JunkPage, "التنظيف"),
    ("large", "📦", "الملفات الكبيرة", LargePage, "التنظيف"),
    ("duplicates", "👯", "الملفات المكررة", DuplicatesPage, "التنظيف"),
    ("security", "🛡", "فحص التهديدات", SecurityPage, "الحماية"),
    ("privacy", "🕵️", "الخصوصية", PrivacyPage, "الحماية"),
    ("optimization", "🚀", "التحسين", OptimizationPage, "السرعة"),
    ("maintenance", "🔧", "الصيانة", MaintenancePage, "السرعة"),
    ("monitor", "📈", "مراقب الأداء", MonitorPage, "السرعة"),
    ("apps", "🗑", "إلغاء التثبيت", UninstallerPage, "التطبيقات"),
    ("updater", "⬆️", "التحديثات", UpdaterPage, "التطبيقات"),
    ("extensions", "🧩", "الإضافات", ExtensionsPage, "التطبيقات"),
    ("space", "🗺", "خريطة المساحة", SpacePage, "الملفات"),
    ("shredder", "✂️", "آلة التمزيق", ShredderPage, "الملفات"),
    ("settings", "⚙️", "الإعدادات", SettingsPage, "—"),
]
