"""قسم «الذاتية»: حفظ الوسائط ذاتية التدمير (الصور ومقاطع الفيديو المؤقتة) في الرسائل المحفوظة."""
import os
import tempfile
import time

from telethon import events, utils

from core import Plugin, escape, runtime

plugin = Plugin(
    category="الذاتية",
    title="حفظ الوسائط الذاتية",
    description="حفظ الوسائط ذاتية التدمير في الرسائل المحفوظة يدويًا أو تلقائيًا.",
    order=10,
)


def _store():
    return runtime.db.collection("selfdestruct")


def _is_timed(message) -> bool:
    media = getattr(message, "media", None)
    return bool(media and getattr(media, "ttl_seconds", None))


async def _save(message) -> None:
    sender = await message.get_sender()
    name = utils.get_display_name(sender) if sender else "غير معروف"
    caption = (
        "<b>وسائط ذاتية التدمير</b>\n"
        f"المرسِل: {escape(name)}\n"
        f"التاريخ: {time.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = await message.download_media(file=os.path.join(tmp, ""))
        if not path:
            raise RuntimeError("تعذّر تنزيل الوسائط.")
        await runtime.client.send_file("me", path, caption=caption, parse_mode="html")
    store = _store()
    await store.set("saved_count", await store.get("saved_count", 0) + 1)
    await store.set("last_saved", time.strftime("%Y-%m-%d %H:%M:%S"))


@plugin.command("حفظ الذاتية", description="حفظ الوسائط الذاتية بالرد عليها؛ تُرسَل نسخة إلى الرسائل المحفوظة.")
async def save_replied(ctx) -> None:
    reply = await ctx.get_reply()
    if reply is None or not _is_timed(reply):
        return await ctx.fail("يجب الرد على رسالة تحتوي على وسائط ذاتية التدمير.")
    try:
        await _save(reply)
    except Exception as exc:  # noqa: BLE001
        return await ctx.fail(f"تعذّر حفظ الوسائط: {escape(exc)}")
    await ctx.reply("تم حفظ الوسائط في الرسائل المحفوظة.")


@plugin.command("تفعيل الذاتية", description="تفعيل الحفظ التلقائي لكل وسائط ذاتية التدمير ترد إليك.")
async def enable_auto(ctx) -> None:
    await _store().set("auto", True)
    await ctx.reply("تم تفعيل الحفظ التلقائي للوسائط الذاتية.")


@plugin.command("تعطيل الذاتية", description="إيقاف الحفظ التلقائي للوسائط الذاتية.")
async def disable_auto(ctx) -> None:
    await _store().set("auto", False)
    await ctx.reply("تم إيقاف الحفظ التلقائي للوسائط الذاتية.")


@plugin.command("حالة الذاتية", description="عرض حالة الحفظ التلقائي وإحصاءاته.")
async def show_status(ctx) -> None:
    store = _store()
    auto = await store.get("auto", False)
    lines = [
        "<b>حالة قسم الذاتية</b>",
        f"الحفظ التلقائي: {'مفعّل' if auto else 'معطّل'}",
        f"عدد الوسائط المحفوظة: {await store.get('saved_count', 0)}",
        f"آخر حفظ: {escape(await store.get('last_saved', 'لا يوجد'))}",
    ]
    await ctx.reply("\n".join(lines))


@plugin.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
async def auto_save(event) -> None:
    if not _is_timed(event.message) or not await _store().get("auto", False):
        return
    await _save(event.message)
