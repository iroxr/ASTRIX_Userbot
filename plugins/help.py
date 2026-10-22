"""قائمة الأوامر: تُبنى تلقائيًا من الأوامر المسجّلة في الإضافات المحمّلة."""
from core import Plugin, escape, plural, registry, runtime

plugin = Plugin(
    category="الأساسية",
    title="قائمة الأوامر",
    description="عرض الأوامر المتاحة مصنّفةً حسب الأقسام.",
    order=0,
    protected=True,
)

_COMMANDS = ("أمر واحد", "أمران", "{n} أوامر", "{n} أمرًا")


def _signature(command) -> str:
    text = f"{runtime.prefix}{command.name}"
    return f"{text} {command.usage}" if command.usage else text


async def _menu(ctx) -> None:
    categories = registry.categories()
    p = escape(runtime.prefix)
    lines = [
        "<b>قائمة الأوامر</b>",
        f"البادئة الحالية: <code>{p}</code>",
        "",
        "<b>الأقسام المتاحة:</b>",
    ]
    for index, cat in enumerate(categories, 1):
        lines.append(f"{index}. {escape(cat.name)} — {plural(len(cat.commands), _COMMANDS)}")
    lines += [
        "",
        f"لعرض أوامر قسم: <code>{p}اوامر اسم_القسم</code> (أو رقمه)",
        f"لعرض تفاصيل أمر: <code>{p}امر اسم_الأمر</code>",
    ]
    await ctx.reply("\n".join(lines))


@plugin.command("الاوامر", aliases=("القائمة", "المساعدة"), description="عرض أقسام الأوامر المتاحة.")
async def show_menu(ctx) -> None:
    await _menu(ctx)


@plugin.command("اوامر", usage="<اسم القسم>", description="عرض أوامر قسم معيّن، مثل: اوامر الذاتية.")
async def show_category(ctx) -> None:
    if not ctx.args:
        await _menu(ctx)
        return
    category = registry.find_category(ctx.args)
    if category is None:
        text = f"لا يوجد قسم باسم «{escape(ctx.args)}»."
        close = registry.suggest_categories(ctx.args)
        if close:
            text += "\nلعلّك تقصد: " + "، ".join(escape(c) for c in close)
        text += f"\nلعرض الأقسام المتاحة: <code>{escape(runtime.prefix)}الاوامر</code>"
        await ctx.fail(text)
        return
    commands = category.commands
    lines = [f"<b>أوامر قسم «{escape(category.name)}»</b>", f"عددها: {plural(len(commands), _COMMANDS)}", ""]
    for command in commands:
        lines.append(f"<code>{escape(_signature(command))}</code>")
        lines.append(f"    {escape(command.description)}")
    await ctx.reply("\n".join(lines))


@plugin.command("امر", usage="<اسم الأمر>", description="عرض تفاصيل أمر محدّد.")
async def show_command(ctx) -> None:
    query = ctx.args
    if query.startswith(runtime.prefix):
        query = query[len(runtime.prefix):]
    resolved = registry.resolve(query) if query else None
    if resolved is None:
        await ctx.fail(f"لا يوجد أمر بهذا الاسم. للاطلاع على الأوامر: <code>{escape(runtime.prefix)}الاوامر</code>")
        return
    command = resolved[0]
    lines = [
        f"<b>الأمر:</b> <code>{escape(_signature(command))}</code>",
        f"<b>الوصف:</b> {escape(command.description)}",
        f"<b>القسم:</b> {escape(command.plugin.category)}",
        f"<b>الإضافة:</b> {escape(command.plugin.title)} (<code>{escape(command.plugin.name)}</code>)",
    ]
    if command.aliases:
        lines.append("<b>الأسماء البديلة:</b> " + "، ".join(f"<code>{escape(a)}</code>" for a in command.aliases))
    await ctx.reply("\n".join(lines))
