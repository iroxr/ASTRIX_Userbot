"""موزّع الأوامر: يلتقط رسائل الحساب الصادرة ويوجّهها إلى الأمر المطابق."""
from __future__ import annotations

import logging

from telethon import events

from .context import Context
from .registry import registry
from .runtime import runtime
from .text import escape

log = logging.getLogger("userbot.dispatcher")


async def on_message(event) -> None:
    text = event.raw_text or ""
    prefix = runtime.prefix
    if not text.startswith(prefix):
        return
    resolved = registry.resolve(text[len(prefix):])
    if resolved is None:
        return  # نص عادي يبدأ بالبادئة وليس أمرًا مسجّلًا
    command, args = resolved
    ctx = Context(event, command, args)
    try:
        await command.handler(ctx)
    except Exception as exc:  # noqa: BLE001
        log.exception("خطأ أثناء تنفيذ الأمر %s", command.name)
        try:
            await ctx.reply(
                "<b>حدث خطأ غير متوقع أثناء تنفيذ الأمر.</b>\n"
                f"<code>{escape(type(exc).__name__)}: {escape(exc)}</code>"
            )
        except Exception:  # noqa: BLE001
            log.exception("تعذّر عرض رسالة الخطأ")


def install() -> None:
    runtime.client.add_event_handler(on_message, events.NewMessage(outgoing=True))
