"""نواة منصة بوت تيليجرام (Userbot): نظام إضافات، وأوامر مصنّفة تلقائيًا، وقاعدة بيانات على GitHub."""
from .errors import ConfigError, PluginError, StorageError, UserbotError
from .registry import Plugin, registry
from .runtime import runtime
from .text import escape, format_duration, normalize, plural

__all__ = [
    "ConfigError", "PluginError", "StorageError", "UserbotError",
    "Plugin", "registry", "runtime",
    "escape", "format_duration", "normalize", "plural",
    "dispatcher",
]


def __getattr__(name):
    # الموزّع يعتمد على Telethon، لذا يُستورد عند الطلب فقط
    if name == "dispatcher":
        from . import dispatcher
        return dispatcher
    raise AttributeError(name)
