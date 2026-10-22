"""سجل الإضافات والأوامر.

تُسجَّل الأوامر تلقائيًا عند تحميل الإضافة، وتُصنَّف حسب «القسم» الذي تعلنه الإضافة،
فتظهر في قائمة الأوامر دون أي إعداد إضافي.
"""
from __future__ import annotations

import difflib
import inspect
import re
from dataclasses import dataclass
from typing import Awaitable, Callable

from .errors import PluginError
from .text import normalize, strip_definite_article

Handler = Callable[..., Awaitable[None]]


@dataclass(eq=False)
class Command:
    name: str
    handler: Handler
    description: str
    usage: str = ""
    aliases: tuple[str, ...] = ()
    plugin: "Plugin | None" = None

    @property
    def keys(self) -> list[str]:
        """الأسماء المطبَّعة للأمر (الاسم الأصلي والأسماء البديلة دون تكرار)."""
        keys: list[str] = []
        for candidate in (self.name, *self.aliases):
            key = normalize(candidate)
            if key and key not in keys:
                keys.append(key)
        return keys


class Plugin:
    """وصف الإضافة. يُنشأ كائن واحد فقط في كل ملف إضافة.

    مثال:
        plugin = Plugin(category="الذاتية", title="الحفظ الذاتي", description="...")

        @plugin.command("حفظ", description="...")
        async def save(ctx): ...
    """

    def __init__(self, *, category: str, title: str, description: str = "", order: int = 100,
                 version: str = "1.0.0", protected: bool = False):
        self.name: str = registry.current_module or ""
        self.category = category
        self.title = title
        self.description = description
        self.order = order
        self.version = version
        self.protected = protected
        self.commands: list[Command] = []
        self.handlers: list[tuple[Handler, object]] = []
        self.startup_hooks: list[Handler] = []
        self.shutdown_hooks: list[Handler] = []
        registry._collect(self)

    def command(self, name: str, *, description: str, usage: str = "", aliases: tuple[str, ...] = ()):
        """تسجيل أمر جديد. يُكتب الاسم دون البادئة، ويجوز أن يتكوّن من عدة كلمات."""
        def decorator(func: Handler) -> Handler:
            if not inspect.iscoroutinefunction(func):
                raise PluginError(f"معالج الأمر «{name}» يجب أن يكون دالة غير متزامنة (async).")
            self.commands.append(Command(name, func, description, usage, tuple(aliases), self))
            return func
        return decorator

    def on(self, event_builder: object):
        """تسجيل معالج حدث من أحداث Telethon، مثل events.NewMessage(incoming=True)."""
        def decorator(func: Handler) -> Handler:
            self.handlers.append((func, event_builder))
            return func
        return decorator

    def startup(self, func: Handler) -> Handler:
        """دالة غير متزامنة تُستدعى بعد تحميل الإضافة."""
        self.startup_hooks.append(func)
        return func

    def shutdown(self, func: Handler) -> Handler:
        """دالة غير متزامنة تُستدعى قبل إيقاف الإضافة."""
        self.shutdown_hooks.append(func)
        return func


@dataclass(eq=False)
class Category:
    name: str
    plugins: list[Plugin]

    @property
    def commands(self) -> list[Command]:
        return [cmd for plugin in self.plugins for cmd in plugin.commands]


class Registry:
    def __init__(self) -> None:
        self.plugins: dict[str, Plugin] = {}
        self._index: dict[str, Command] = {}
        self._ordered: list[tuple[str, Command]] = []
        self._collecting: "list[Plugin] | None" = None
        self.current_module: "str | None" = None

    # ------------------------------------------------------------------ التجميع أثناء الاستيراد
    def begin(self, module_name: str) -> None:
        self.current_module = module_name
        self._collecting = []

    def end(self) -> list[Plugin]:
        items = self._collecting or []
        self._collecting = None
        self.current_module = None
        return items

    def _collect(self, plugin: Plugin) -> None:
        if self._collecting is None:
            raise PluginError("لا يمكن إنشاء إضافة خارج عملية التحميل.")
        self._collecting.append(plugin)

    # ------------------------------------------------------------------ التسجيل
    def add_plugin(self, plugin: Plugin) -> None:
        if plugin.name in self.plugins:
            raise PluginError(f"الإضافة «{plugin.name}» مسجّلة مسبقًا.")
        pending: dict[str, Command] = {}
        for command in plugin.commands:
            command.plugin = plugin
            for key in command.keys:
                owner = self._index.get(key) or pending.get(key)
                if owner is not None:
                    where = owner.plugin.name if owner.plugin else "غير معروفة"
                    raise PluginError(f"الأمر «{key}» معرَّف مسبقًا في الإضافة «{where}».")
                pending[key] = command
        self.plugins[plugin.name] = plugin
        self._index.update(pending)
        self._rebuild()

    def remove_plugin(self, name: str) -> None:
        plugin = self.plugins.pop(name, None)
        if plugin is None:
            return
        self._index = {k: c for k, c in self._index.items() if c.plugin is not plugin}
        self._rebuild()

    def _rebuild(self) -> None:
        # الأسماء الأطول (الأكثر كلمات) تُجرَّب أولًا لتفوز على الأقصر
        self._ordered = sorted(self._index.items(), key=lambda kv: (-kv[0].count(" "), -len(kv[0])))

    # ------------------------------------------------------------------ الاستعلام
    def resolve(self, body: str) -> "tuple[Command, str] | None":
        """مطابقة نص الأمر (دون البادئة). تُعاد (الأمر، الوسائط) أو None."""
        body = body.strip()
        if not body:
            return None
        norm = normalize(body)
        for key, command in self._ordered:
            if norm == key or norm.startswith(key + " "):
                words = key.count(" ") + 1
                parts = re.split(r"\s+", body, maxsplit=words)
                return command, (parts[words] if len(parts) > words else "")
        return None

    def ordered_plugins(self) -> list[Plugin]:
        return sorted(self.plugins.values(), key=lambda p: (p.order, p.name))

    def all_commands(self) -> list[Command]:
        return [cmd for plugin in self.ordered_plugins() for cmd in plugin.commands]

    def categories(self) -> list[Category]:
        grouped: dict[str, list[Plugin]] = {}
        for plugin in self.ordered_plugins():
            grouped.setdefault(plugin.category, []).append(plugin)
        ordered = sorted(grouped.items(), key=lambda kv: (min(p.order for p in kv[1]), kv[0]))
        return [Category(name, plugins) for name, plugins in ordered]

    def find_category(self, query: str) -> "Category | None":
        """البحث عن قسم بالاسم (مع أو دون «ال») أو برقمه في القائمة."""
        key = normalize(query)
        if not key:
            return None
        cats = self.categories()
        if key.isdigit():
            index = int(key)
            return cats[index - 1] if 1 <= index <= len(cats) else None
        wanted = strip_definite_article(key)
        for cat in cats:
            if strip_definite_article(normalize(cat.name)) == wanted:
                return cat
        return None

    def suggest_categories(self, query: str) -> list[str]:
        names = {strip_definite_article(normalize(c.name)): c.name for c in self.categories()}
        close = difflib.get_close_matches(strip_definite_article(normalize(query)), list(names), n=3, cutoff=0.5)
        return [names[k] for k in close]


registry = Registry()
