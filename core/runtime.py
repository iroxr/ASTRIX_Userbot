"""حالة التشغيل المشتركة التي تصل إليها الإضافات: العميل وقاعدة البيانات والإعدادات."""
from __future__ import annotations

import time

from .registry import Registry, registry


class Runtime:
    def __init__(self) -> None:
        self.client = None
        self.db = None
        self.config = None
        self.loader = None
        self.prefix = "."
        self.started_at = time.monotonic()
        self.registry: Registry = registry

    def setup(self, *, config, db, client) -> None:
        self.config = config
        self.db = db
        self.client = client
        self.prefix = config.prefix
        self.started_at = time.monotonic()

    @property
    def uptime(self) -> float:
        return time.monotonic() - self.started_at


runtime = Runtime()
