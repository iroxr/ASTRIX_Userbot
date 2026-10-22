"""أوامر قاعدة البيانات المعتمدة على مستودع GitHub."""
import json
import time

from core import Plugin, StorageError, escape, plural, runtime

plugin = Plugin(
    category="النظام",
    title="قاعدة البيانات",
    description="استعراض قاعدة البيانات المخزّنة في GitHub وحفظها.",
    order=2,
    protected=True,
)


@plugin.command("القاعدة", description="عرض حالة قاعدة البيانات ومجموعاتها.")
async def show_db(ctx) -> None:
    db = runtime.db
    remote = [i["name"][:-5] for i in await db.list_files("data") if i.get("name", "").endswith(".json")]
    local = {c.name for c in db.collections}
    names = sorted(set(remote) | local)
    last = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(db.last_flush)) if db.last_flush else "لم يُجرَ حفظ بعد"
    lines = [
        "<b>قاعدة البيانات</b>",
        f"المستودع: <code>{escape(db.repo)}</code>",
        f"الفرع: <code>{escape(db.branch)}</code>",
        f"آخر حفظ ناجح: {escape(last)}",
        f"مجموعات بانتظار الحفظ: {db.pending}",
    ]
    if db.last_error:
        lines.append(f"آخر خطأ: {escape(db.last_error)}")
    lines += ["", f"<b>المجموعات ({plural(len(names), ('مجموعة واحدة', 'مجموعتان', '{n} مجموعات', '{n} مجموعةً'))}):</b>"]
    lines += [f"• <code>{escape(n)}</code>" for n in names] or ["لا توجد مجموعات بعد."]
    await ctx.reply("\n".join(lines))


@plugin.command("حفظ القاعدة", description="حفظ جميع التغييرات المعلّقة في GitHub فورًا.")
async def flush(ctx) -> None:
    await ctx.edit("جارٍ الحفظ في GitHub…")
    if await runtime.db.flush_all():
        await ctx.reply("تم حفظ جميع التغييرات في المستودع بنجاح.")
    else:
        await ctx.fail(f"تعذّر الحفظ: {escape(runtime.db.last_error)}\nستُعاد المحاولة تلقائيًا.")


@plugin.command("بيانات", usage="<اسم المجموعة>", description="عرض محتوى مجموعة بيانات بصيغة JSON.")
async def show_data(ctx) -> None:
    if not ctx.args:
        await ctx.fail(f"الصيغة الصحيحة: {ctx.usage_hint()}")
        return
    try:
        data = await runtime.db.collection(ctx.args.split()[0]).all()
    except StorageError as exc:
        await ctx.fail(escape(exc))
        return
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if len(text) > 3500:
        text = text[:3500] + "\n… (اقتُطع النص)"
    await ctx.reply(f"<pre>{escape(text)}</pre>")
