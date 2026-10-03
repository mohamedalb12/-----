"""صفحات البرنامج بالترتيب الظاهر في الشريط الجانبي: (المفتاح، الأيقونة، الاسم، الصنف)."""

from .dashboard import DashboardPage
from .duplicates import DuplicatesPage
from .junk import JunkPage
from .large import LargePage
from .settings import SettingsPage
from .space import SpacePage
from .uninstaller import UninstallerPage

PAGES = [
    ("dashboard", "🏠", "الرئيسية", DashboardPage),
    ("junk", "🧹", "مهملات النظام", JunkPage),
    ("large", "📦", "الملفات الكبيرة", LargePage),
    ("duplicates", "👯", "الملفات المكررة", DuplicatesPage),
    ("apps", "🧩", "إلغاء التثبيت", UninstallerPage),
    ("space", "🗺", "خريطة المساحة", SpacePage),
    ("settings", "⚙️", "الإعدادات", SettingsPage),
]
