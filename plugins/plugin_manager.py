"""إدارة الإضافات: العرض والتفعيل والتعطيل وإعادة التحميل والتثبيت والحذف."""
import re

from core import Plugin, PluginError, StorageError, escape, plural, runtime
from core.loader import STEM

plugin = Plugin(
    category="الإضافات",
    title="إدارة الإضافات",
    description="تثبيت الإضافات وتفعيلها وتعطيلها دون إعادة تشغيل المنصة.",
    order=3,
    protected=True,
)

MAX_SIZE = 200 * 1024
_CMDS = ("أمر واحد", "أمران", "{n} أوامر", "{n} أمرًا")


def _resolve(ctx) -> "str | None":
    return runtime.loader.find(ctx.args) if ctx.args else None


async def _not_found(ctx) -> None:
    await ctx.fail(
        "لم يُعثر على إضافة بهذا المعرّف.\n"
        f"لعرض الإضافات المتاحة: <code>{escape(runtime.prefix)}الاضافات</code>"
    )


@plugin.command("الاضافات", description="عرض جميع الإضافات وحالة كلٍّ منها.")
async def list_plugins(ctx) -> None:
    loader = runtime.loader
    disabled = await loader.disabled()
    lines = ["<b>الإضافات</b>", ""]
    for stem, file in loader.discover().items():
        origin = "مثبّتة" if file.external else "مدمجة"
        entry = loader.loaded.get(stem)
        if entry:
            lines.append(
                f"• <code>{escape(stem)}</code> — {escape(entry.plugin.title)}\n"
                f"    مفعّلة · {origin} · القسم: {escape(entry.plugin.category)} · "
                f"{plural(len(entry.plugin.commands), _CMDS)}"
            )
        else:
            state = "معطّلة" if stem in disabled else "غير محمّلة"
            lines.append(f"• <code>{escape(stem)}</code>\n    {state} · {origin}")
    await ctx.reply("\n".join(lines))


@plugin.command("تفعيل اضافة", usage="<المعرّف>", description="تفعيل إضافة معطّلة وإضافة أوامرها إلى القائمة.")
async def enable(ctx) -> None:
    stem = _resolve(ctx)
    if stem is None:
        return await _not_found(ctx)
    await runtime.loader.set_enabled(stem, True)
    if stem in runtime.loader.loaded:
        return await ctx.reply(f"الإضافة <code>{escape(stem)}</code> مفعّلة بالفعل.")
    try:
        loaded = await runtime.loader.load(stem)
    except PluginError as exc:
        return await ctx.fail(escape(exc))
    await ctx.reply(f"تم تفعيل الإضافة «{escape(loaded.title)}» وأُضيفت أوامرها إلى القائمة.")


@plugin.command("تعطيل اضافة", usage="<المعرّف>", description="تعطيل إضافة وإزالة أوامرها من القائمة.")
async def disable(ctx) -> None:
    stem = _resolve(ctx)
    if stem is None or stem not in runtime.loader.loaded:
        return await _not_found(ctx)
    try:
        await runtime.loader.unload(stem)
    except PluginError as exc:
        return await ctx.fail(escape(exc))
    await runtime.loader.set_enabled(stem, False)
    await ctx.reply(f"تم تعطيل الإضافة <code>{escape(stem)}</code> وأُزيلت أوامرها من القائمة.")


@plugin.command("اعادة تحميل اضافة", usage="<المعرّف | الكل>",
                description="إعادة تحميل إضافة بعد تعديل ملفها.")
async def reload(ctx) -> None:
    loader = runtime.loader
    if ctx.args == "الكل":
        names = [s for s, e in loader.loaded.items() if not e.plugin.protected]
    else:
        stem = _resolve(ctx)
        if stem is None:
            return await _not_found(ctx)
        names = [stem]
    done, failed = [], []
    for stem in names:
        try:
            await loader.reload(stem)
            done.append(stem)
        except PluginError as exc:
            failed.append(f"<code>{escape(stem)}</code>: {escape(exc)}")
    lines = []
    if done:
        lines.append("أُعيد تحميل: " + "، ".join(f"<code>{escape(s)}</code>" for s in done))
    if failed:
        lines.append("<b>تعذّر تحميل:</b>\n" + "\n".join(failed))
    await ctx.reply("\n".join(lines) or "لا توجد إضافات لإعادة تحميلها.")


@plugin.command("تثبيت اضافة", description="تثبيت إضافة من ملف بايثون بالرد على الملف. تُحفظ في المستودع تلقائيًا.")
async def install(ctx) -> None:
    reply = await ctx.get_reply()
    name = getattr(getattr(reply, "file", None), "name", None) if reply else None
    if not name or not name.endswith(".py"):
        return await ctx.fail("يجب الرد على رسالة تحتوي على ملف إضافة بامتداد <code>.py</code>.")
    stem = name[:-3]
    if not STEM.match(stem):
        return await ctx.fail("اسم الملف غير صالح. يجب أن يبدأ بحرف لاتيني ويتكوّن من أحرف وأرقام وشرطة سفلية فقط.")
    loader = runtime.loader
    existing = loader.discover().get(stem)
    if existing and not existing.external:
        return await ctx.fail("هذا المعرّف محجوز لإضافة مدمجة. يُرجى تغيير اسم الملف.")
    if getattr(reply.file, "size", 0) > MAX_SIZE:
        return await ctx.fail("حجم الملف يتجاوز الحد المسموح (200 كيلوبايت).")

    data = await reply.download_media(bytes)
    try:
        compile(data, name, "exec")
    except SyntaxError as exc:
        return await ctx.fail(f"الملف يحتوي على خطأ في الصياغة: <code>{escape(exc)}</code>")

    target = runtime.config.external_dir / name
    backup = target.read_bytes() if target.exists() else None
    if stem in loader.loaded:
        await loader.unload(stem, force=True)
    runtime.config.external_dir.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    try:
        loaded = await loader.load(stem)
    except PluginError as exc:
        if backup is None:
            target.unlink(missing_ok=True)
        else:
            target.write_bytes(backup)
            try:
                await loader.load(stem)
            except PluginError:
                pass
        return await ctx.fail(escape(exc))

    await loader.set_enabled(stem, True)
    try:
        await runtime.db.put_file(f"plugins/{name}", data, f"تثبيت الإضافة {stem}")
    except StorageError as exc:
        return await ctx.reply(
            f"حُمّلت الإضافة «{escape(loaded.title)}» لكن تعذّر حفظها في المستودع، "
            f"وستزول عند إعادة التشغيل: {escape(exc)}"
        )
    await ctx.reply(
        f"تم تثبيت الإضافة «{escape(loaded.title)}» في قسم «{escape(loaded.category)}» "
        f"({plural(len(loaded.commands), _CMDS)}) وحُفظت في المستودع."
    )


@plugin.command("حذف اضافة", usage="<المعرّف>", description="حذف إضافة مثبّتة نهائيًا من الجهاز والمستودع.")
async def remove(ctx) -> None:
    loader = runtime.loader
    stem = _resolve(ctx)
    file = loader.discover().get(stem) if stem else None
    if file is None:
        return await _not_found(ctx)
    if not file.external:
        return await ctx.fail("الإضافات المدمجة لا تُحذف. يمكن تعطيلها بدلًا من ذلك.")
    if stem in loader.loaded:
        await loader.unload(stem, force=True)
    file.path.unlink(missing_ok=True)
    await loader.set_enabled(stem, True)  # إزالة المعرّف من قائمة المعطّلة
    try:
        await runtime.db.delete_file(f"plugins/{file.path.name}", f"حذف الإضافة {stem}")
    except StorageError as exc:
        return await ctx.fail(f"حُذفت محليًا فقط: {escape(exc)}")
    await ctx.reply(f"تم حذف الإضافة <code>{escape(stem)}</code> من الجهاز والمستودع.")
