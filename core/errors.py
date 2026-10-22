"""الأخطاء المخصصة للمنصة. رسائلها موجّهة للمستخدم وباللغة العربية الفصحى."""


class UserbotError(Exception):
    """الأصل المشترك لجميع أخطاء المنصة."""


class ConfigError(UserbotError):
    """خطأ في الإعدادات أو متغيرات البيئة."""


class StorageError(UserbotError):
    """خطأ في قاعدة البيانات أو في الاتصال بـ GitHub."""


class PluginError(UserbotError):
    """خطأ في تحميل الإضافات أو إدارتها."""
