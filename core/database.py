"""قاعدة بيانات تعتمد على مستودع GitHub: كل مجموعة بيانات ملف JSON في فرع مخصص.

- القراءة تتم عند أول استخدام للمجموعة ثم تُحفظ في الذاكرة.
- الكتابة مؤجلة ومجمّعة (افتراضيًا خمس ثوانٍ) لتقليل عدد الإيداعات.
- عند فشل الحفظ تبقى البيانات في الذاكرة وتُعاد المحاولة تلقائيًا.
"""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import re
import time
from typing import Any

from .errors import StorageError
from .github import GitHubClient, RemoteFile

log = logging.getLogger("userbot.database")
_NAME = re.compile(r"^[A-Za-z0-9_\-]+$")


class Collection:
    """مجموعة بيانات واحدة (قاموس مفاتيح وقيم قابلة للتحويل إلى JSON)."""

    def __init__(self, db: "Database", name: str):
        self.db = db
        self.name = name
        self.path = f"data/{name}.json"
        self._data: "dict | None" = None
        self._sha: "str | None" = None
        self._saved = b""
        self._dirty = False
        self._load_lock = asyncio.Lock()
        self._flush_lock = asyncio.Lock()

    @property
    def dirty(self) -> bool:
        return self._dirty

    @property
    def loaded(self) -> bool:
        return self._data is not None

    async def _ensure(self) -> dict:
        if self._data is None:
            async with self._load_lock:
                if self._data is None:
                    remote = await self.db.gh.get_file(self.path)
                    data: dict = {}
                    if remote:
                        try:
                            data = json.loads(remote.content.decode("utf-8"))
                        except ValueError as exc:
                            raise StorageError(f"ملف البيانات «{self.path}» تالف ويتعذّر قراءته.") from exc
                        if not isinstance(data, dict):
                            raise StorageError(f"ملف البيانات «{self.path}» لا يحتوي على كائن JSON صالح.")
                        self._sha, self._saved = remote.sha, remote.content
                    self._data = data
        return self._data

    def _touch(self) -> None:
        self._dirty = True
        self.db.mark_dirty()

    # ------------------------------------------------------------------ الواجهة العامة
    async def get(self, key: str, default: Any = None) -> Any:
        data = await self._ensure()
        return copy.deepcopy(data.get(key, default))

    async def set(self, key: str, value: Any) -> None:
        data = await self._ensure()
        json.dumps(value)  # للتأكد من أن القيمة قابلة للتخزين
        data[key] = copy.deepcopy(value)
        self._touch()

    async def update(self, values: dict) -> None:
        for key, value in values.items():
            await self.set(key, value)

    async def delete(self, key: str) -> bool:
        data = await self._ensure()
        existed = data.pop(key, None) is not None
        if existed:
            self._touch()
        return existed

    async def all(self) -> dict:
        return copy.deepcopy(await self._ensure())

    async def clear(self) -> None:
        data = await self._ensure()
        data.clear()
        self._touch()

    # ------------------------------------------------------------------ الحفظ
    async def flush(self) -> None:
        async with self._flush_lock:
            if not self._dirty or self._data is None:
                return
            payload = json.dumps(self._data, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
            if payload == self._saved:
                self._dirty = False
                return
            self._dirty = False
            try:
                self._sha = await self.db.gh.put_file(
                    self.path, payload, f"تحديث البيانات: {self.name}", self._sha
                )
            except Exception:
                self._dirty = True
                raise
            self._saved = payload


class Database:
    def __init__(self, gh: GitHubClient, *, debounce: float = 5.0, retry_delay: float = 30.0):
        self.gh = gh
        self.debounce = debounce
        self.retry_delay = retry_delay
        self._collections: dict[str, Collection] = {}
        self._task: "asyncio.Task | None" = None
        self.last_flush: "float | None" = None
        self.last_error: "str | None" = None

    @property
    def repo(self) -> str:
        return self.gh.repo

    @property
    def branch(self) -> str:
        return self.gh.branch

    def collection(self, name: str) -> Collection:
        if not _NAME.match(name):
            raise StorageError("اسم المجموعة يجب أن يتكوّن من أحرف لاتينية وأرقام وشرطات فقط.")
        if name not in self._collections:
            self._collections[name] = Collection(self, name)
        return self._collections[name]

    @property
    def collections(self) -> list[Collection]:
        return list(self._collections.values())

    @property
    def pending(self) -> int:
        return sum(1 for c in self._collections.values() if c.dirty)

    async def start(self) -> bool:
        """التحقق من الفرع وإنشاؤه عند الحاجة. تُعاد True إذا أُنشئ الفرع الآن."""
        return await self.gh.ensure_branch()

    # ------------------------------------------------------------------ الجدولة
    def mark_dirty(self, delay: "float | None" = None) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.get_running_loop().create_task(
                self._delayed(self.debounce if delay is None else delay)
            )

    async def _delayed(self, delay: float) -> None:
        await asyncio.sleep(delay)
        self._task = None
        if not await self.flush_all():
            self.mark_dirty(self.retry_delay)

    async def flush_all(self) -> bool:
        """حفظ جميع المجموعات المعدّلة فورًا. تُعاد True عند نجاح كل العمليات."""
        ok = True
        for col in list(self._collections.values()):
            if col.dirty:
                try:
                    await col.flush()
                except Exception as exc:  # noqa: BLE001
                    ok = False
                    self.last_error = str(exc)
                    log.error("تعذّر حفظ المجموعة %s: %s", col.name, exc)
        if ok:
            self.last_flush = time.time()
            self.last_error = None
        return ok

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        await self.flush_all()

    # ------------------------------------------------------------------ ملفات خام
    async def get_file(self, path: str) -> "RemoteFile | None":
        return await self.gh.get_file(path)

    async def put_file(self, path: str, content: bytes, message: str) -> str:
        return await self.gh.put_file(path, content, message)

    async def delete_file(self, path: str, message: str) -> bool:
        return await self.gh.delete_file(path, message)

    async def list_files(self, prefix: str) -> list[dict]:
        return await self.gh.list_dir(prefix)
