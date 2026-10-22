"""قالب إضافة. انسخه إلى مجلد plugins/ (أو ثبّته بالأمر «تثبيت اضافة») وعدّل ما يلزم.

تظهر أوامر هذه الإضافة تلقائيًا في «.الاوامر» ضمن القسم المعلَن أدناه.
اسم الملف (بالحروف اللاتينية) هو معرّف الإضافة.
"""
from core import Plugin, escape, runtime

plugin = Plugin(
    category="أمثلة",           # اسم القسم؛ الإضافات ذات الاسم نفسه تُجمع في قسم واحد
    title="إضافة تجريبية",       # العنوان الظاهر في قائمة الإضافات
    description="مثال على بناء إضافة.",
    order=100,                   # ترتيب القسم في القائمة (الأصغر أولًا)
)


@plugin.command("ترحيب", usage="<الاسم>", description="عرض رسالة ترحيب، مع عدّاد محفوظ في قاعدة البيانات.")
async def hello(ctx) -> None:
    store = runtime.db.collection("example")          # ملف data/example.json في المستودع
    count = await store.get("count", 0) + 1
    await store.set("count", count)                   # يُحفظ في GitHub تلقائيًا
    await ctx.reply(f"أهلًا بك {escape(ctx.args or 'أيها الزائر')}. عدد الاستخدامات: {count}")


@plugin.startup
async def on_start() -> None:
    """تُستدعى عند تحميل الإضافة."""


# لمعالجة الأحداث الواردة:
# from telethon import events
# @plugin.on(events.NewMessage(incoming=True))
# async def handler(event): ...
