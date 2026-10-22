"""أوامر النظام: الفحص والحالة وإعادة التشغيل وضبط البادئة."""
import os
import platform
import sys
import time

from telethon import __version__ as telethon_version

from core import Plugin, escape, format_duration, plural, registry, runtime

plugin = Plugin(
    category="النظام",
    title="أوامر النظام",
    description="فحص الحالة وإدارة التشغيل والإعدادات العامة.",
    order=1,
    protected=True,
)


@plugin.command("فحص", description="قياس زمن الاستجابة.")
async def ping(ctx) -> None:
    start = time.perf_counter()
    await ctx.edit("جارٍ الفحص…")
    elapsed = (time.perf_counter() - start) * 1000
    await ctx.reply(f"<b>زمن الاستجابة:</b> {elapsed:.0f} مللي ثانية")


@plugin.command("الحالة", description="عرض حالة المنصة وقاعدة البيانات.")
async def status(ctx) -> None:
    db = runtime.db
    plugins = registry.plugins
    lines = [
        "<b>حالة المنصة</b>",
        f"مدة التشغيل: {format_duration(runtime.uptime)}",
        f"الإضافات المحمّلة: {len(plugins)}",
        f"الأوامر المسجّلة: {len(registry.all_commands())}",
        f"البادئة الحالية: <code>{escape(runtime.prefix)}</code>",
        "",
        "<b>قاعدة البيانات</b>",
        f"المستودع: <code>{escape(db.repo)}</code>",
        f"الفرع: <code>{escape(db.branch)}</code>",
        f"مجموعات بانتظار الحفظ: {db.pending}",
        "",
        f"بايثون {platform.python_version()} — Telethon {telethon_version}",
    ]
    await ctx.reply("\n".join(lines))


@plugin.command("اعادة تشغيل", aliases=("اعادة التشغيل",), description="إعادة تشغيل المنصة بعد حفظ البيانات.")
async def restart(ctx) -> None:
    await ctx.reply("جارٍ إعادة التشغيل…")
    await runtime.db.collection("system").set(
        "restart_notice", {"chat": ctx.event.chat_id, "message": ctx.event.id}
    )
    await runtime.db.flush_all()
    await runtime.client.disconnect()
    os.execv(sys.executable, [sys.executable, *sys.argv])


@plugin.startup
async def announce_restart() -> None:
    """تعديل رسالة إعادة التشغيل السابقة لإعلام المستخدم باكتمالها."""
    system = runtime.db.collection("system")
    notice = await system.get("restart_notice")
    if not notice:
        return
    await system.delete("restart_notice")
    try:
        await runtime.client.edit_message(notice["chat"], notice["message"], "اكتملت إعادة التشغيل بنجاح.")
    except Exception:  # noqa: BLE001
        pass


@plugin.command("البادئة", description="عرض البادئة الحالية للأوامر.")
async def show_prefix(ctx) -> None:
    await ctx.reply(f"البادئة الحالية للأوامر: <code>{escape(runtime.prefix)}</code>")


@plugin.command("تغيير البادئة", usage="<البادئة الجديدة>",
                description="تغيير بادئة الأوامر (من حرف إلى ثلاثة أحرف دون مسافات).")
async def set_prefix(ctx) -> None:
    value = ctx.args
    if not value or len(value) > 3 or any(ch.isspace() for ch in value):
        await ctx.fail(f"الصيغة الصحيحة: {ctx.usage_hint()}\nيجب أن تتكوّن البادئة من حرف إلى ثلاثة أحرف دون مسافات.")
        return
    runtime.prefix = value
    await runtime.db.collection("system").set("prefix", value)
    await ctx.reply(
        f"تم تغيير البادئة إلى <code>{escape(value)}</code>.\n"
        f"لعرض الأوامر: <code>{escape(value)}الاوامر</code>"
    )
