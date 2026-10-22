"""نقطة تشغيل المنصة."""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from telethon import TelegramClient
from telethon.sessions import StringSession

from core import ConfigError, StorageError, dispatcher, runtime, webserver
from core.config import Config
from core.database import Database
from core.github import GitHubClient
from core.loader import Loader

log = logging.getLogger("userbot")


async def run() -> None:
    config = Config.from_env(Path(__file__).resolve().parent)
    db = Database(GitHubClient(config.github_token, config.github_repo, config.github_branch))
    client = TelegramClient(StringSession(config.session), config.api_id, config.api_hash)
    runtime.setup(config=config, db=db, client=client)
    loader = Loader(runtime)
    runtime.loader = loader
    web = None
    if os.environ.get("PORT"):  # الاستضافات المجانية (Web Service) تشترط منفذًا مفتوحًا
        web = await webserver.start(int(os.environ["PORT"]))
        log.info("خادم فحص الصحة يعمل على المنفذ %s.", os.environ["PORT"])
    try:
        if await db.start():
            log.info("أُنشئ فرع قاعدة البيانات «%s» لأول مرة.", config.github_branch)
        runtime.prefix = await db.collection("system").get("prefix", config.prefix)
        synced = await loader.sync_external()
        log.info("زُومنت %d إضافة مثبّتة من المستودع.", synced)

        await client.connect()
        if not await client.is_user_authorized():
            raise ConfigError("جلسة تيليجرام غير صالحة. يُرجى توليد جلسة جديدة بالأداة tools/generate_session.py.")
        me = await client.get_me()
        log.info("تم تسجيل الدخول بحساب: %s", getattr(me, "first_name", me.id))

        await loader.load_all()
        dispatcher.install()
        log.info("المنصة جاهزة. البادئة الحالية: %s", runtime.prefix)
        await client.run_until_disconnected()
    finally:
        await loader.unload_all()
        await db.stop()
        await client.disconnect()
        if web:
            web.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    try:
        asyncio.run(run())
    except (ConfigError, StorageError) as exc:
        print(f"خطأ: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
