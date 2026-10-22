"""محمّل الإضافات: اكتشاف الملفات وتحميلها وإلغاء تحميلها وإعادة تحميلها أثناء التشغيل."""
from __future__ import annotations

import functools
import importlib.util
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from telethon.events import StopPropagation

from .errors import PluginError
from .registry import Plugin, registry

log = logging.getLogger("userbot.loader")
STEM = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,40}$")


@dataclass
class PluginFile:
    stem: str
    path: Path
    external: bool


@dataclass
class Loaded:
    file: PluginFile
    plugin: Plugin
    attached: list


class Loader:
    def __init__(self, rt) -> None:
        self.rt = rt
        self.loaded: dict[str, Loaded] = {}

    # ------------------------------------------------------------------ الاكتشاف
    def discover(self) -> dict[str, PluginFile]:
        found: dict[str, PluginFile] = {}
        for directory, external in ((self.rt.config.plugins_dir, False), (self.rt.config.external_dir, True)):
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.py")):
                if path.stem.startswith("_") or not STEM.match(path.stem):
                    continue
                found.setdefault(path.stem, PluginFile(path.stem, path, external))
        return found

    # ------------------------------------------------------------------ التعطيل الدائم
    def _system(self):
        return self.rt.db.collection("system")

    async def disabled(self) -> set[str]:
        return set(await self._system().get("disabled_plugins", []))

    async def set_enabled(self, stem: str, enabled: bool) -> None:
        names = await self.disabled()
        names.discard(stem) if enabled else names.add(stem)
        await self._system().set("disabled_plugins", sorted(names))

    # ------------------------------------------------------------------ مزامنة الإضافات المثبّتة
    async def sync_external(self) -> int:
        """جلب الإضافات المثبّتة من المستودع إلى المجلد المحلي. تُعاد عدد الملفات."""
        directory = self.rt.config.external_dir
        directory.mkdir(parents=True, exist_ok=True)
        for old in directory.glob("*.py"):
            old.unlink()
        count = 0
        for item in await self.rt.db.list_files("plugins"):
            name = item.get("name", "")
            if item.get("type") != "file" or not name.endswith(".py") or not STEM.match(name[:-3]):
                continue
            remote = await self.rt.db.get_file(item["path"])
            if remote:
                (directory / name).write_bytes(remote.content)
                count += 1
        return count

    # ------------------------------------------------------------------ التحميل
    async def load_all(self) -> None:
        disabled = await self.disabled()
        for stem in self.discover():
            if stem in disabled:
                continue
            try:
                await self.load(stem)
            except PluginError as exc:
                log.error("%s", exc)

    async def load(self, stem: str) -> Plugin:
        if stem in self.loaded:
            raise PluginError(f"الإضافة «{stem}» محمّلة بالفعل.")
        file = self.discover().get(stem)
        if file is None:
            raise PluginError(f"لا توجد إضافة بالمعرّف «{stem}».")

        module_name = f"userbot_plugins.{stem}"
        spec = importlib.util.spec_from_file_location(module_name, file.path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        registry.begin(stem)
        try:
            spec.loader.exec_module(module)
        except BaseException as exc:  # noqa: BLE001
            registry.end()
            sys.modules.pop(module_name, None)
            raise PluginError(f"تعذّر تحميل الإضافة «{stem}»: {type(exc).__name__}: {exc}") from exc
        plugins = registry.end()

        try:
            if len(plugins) != 1:
                raise PluginError(f"يجب أن يحتوي ملف الإضافة «{stem}» على كائن Plugin واحد بالضبط.")
            plugin = plugins[0]
            registry.add_plugin(plugin)
        except PluginError:
            sys.modules.pop(module_name, None)
            raise

        attached = []
        try:
            for callback, builder in plugin.handlers:
                wrapped = self._wrap(plugin, callback)
                self.rt.client.add_event_handler(wrapped, builder)
                attached.append((wrapped, builder))
            for hook in plugin.startup_hooks:
                await hook()
        except Exception as exc:  # noqa: BLE001
            self._detach(attached)
            registry.remove_plugin(plugin.name)
            sys.modules.pop(module_name, None)
            raise PluginError(f"تعذّر تشغيل الإضافة «{stem}»: {type(exc).__name__}: {exc}") from exc

        self.loaded[stem] = Loaded(file, plugin, attached)
        log.info("تم تحميل الإضافة «%s» (%d أمر)", stem, len(plugin.commands))
        return plugin

    @staticmethod
    def _wrap(plugin: Plugin, callback):
        @functools.wraps(callback)
        async def wrapper(event):
            try:
                await callback(event)
            except StopPropagation:
                raise
            except Exception:  # noqa: BLE001
                log.exception("خطأ في معالج حدث تابع للإضافة %s", plugin.name)
        return wrapper

    def _detach(self, attached: list) -> None:
        for wrapped, builder in attached:
            try:
                self.rt.client.remove_event_handler(wrapped, builder)
            except Exception:  # noqa: BLE001
                pass

    async def unload(self, stem: str, *, force: bool = False) -> None:
        entry = self.loaded.get(stem)
        if entry is None:
            raise PluginError(f"الإضافة «{stem}» غير محمّلة.")
        if entry.plugin.protected and not force:
            raise PluginError(f"الإضافة «{stem}» أساسية ولا يجوز تعطيلها.")
        for hook in entry.plugin.shutdown_hooks:
            try:
                await hook()
            except Exception:  # noqa: BLE001
                log.exception("خطأ أثناء إيقاف الإضافة %s", stem)
        self._detach(entry.attached)
        registry.remove_plugin(entry.plugin.name)
        sys.modules.pop(f"userbot_plugins.{stem}", None)
        del self.loaded[stem]

    async def reload(self, stem: str) -> Plugin:
        if stem in self.loaded:
            await self.unload(stem, force=True)
        return await self.load(stem)

    async def unload_all(self) -> None:
        for stem in list(self.loaded):
            try:
                await self.unload(stem, force=True)
            except PluginError:
                pass

    # ------------------------------------------------------------------ استعلامات
    def find(self, query: str) -> "str | None":
        """تحويل المعرّف أو العنوان إلى معرّف الإضافة."""
        from .text import normalize
        key = query.strip()
        if not key:
            return None
        files = self.discover()
        for stem in files:
            if stem.lower() == key.lower():
                return stem
        wanted = normalize(key)
        for stem, entry in self.loaded.items():
            if normalize(entry.plugin.title) == wanted:
                return stem
        return None
