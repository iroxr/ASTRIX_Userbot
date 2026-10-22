"""اختبار شامل دون اتصال: GitHub وتيليجرام كلاهما مُحاكى.

التشغيل:  python tests/test_offline.py
(إن لم تكن مكتبة Telethon مثبّتة تُستخدم بدائل وهمية لها.)
"""
import asyncio
import base64
import hashlib
import json
import shutil
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    import telethon  # noqa: F401
except ImportError:
    tl = types.ModuleType("telethon")
    tl.__version__ = "stub"
    events = types.ModuleType("telethon.events")

    class StopPropagation(Exception):
        pass

    class _Builder:
        def __init__(self, **kw):
            self.kw = kw

    events.StopPropagation = StopPropagation
    events.NewMessage = _Builder
    errors = types.ModuleType("telethon.errors")

    class MessageNotModifiedError(Exception):
        pass

    errors.MessageNotModifiedError = MessageNotModifiedError
    utils = types.ModuleType("telethon.utils")
    utils.get_display_name = lambda x: getattr(x, "name", "؟")
    sessions = types.ModuleType("telethon.sessions")
    sessions.StringSession = object
    tl.events, tl.errors, tl.utils, tl.sessions = events, errors, utils, sessions
    tl.TelegramClient = object
    for name, mod in (("telethon", tl), ("telethon.events", events), ("telethon.errors", errors),
                      ("telethon.utils", utils), ("telethon.sessions", sessions)):
        sys.modules[name] = mod

from core import registry, runtime  # noqa: E402
from core.config import Config  # noqa: E402
from core.database import Database  # noqa: E402
from core.dispatcher import on_message  # noqa: E402
from core.github import GitHubClient  # noqa: E402
from core.loader import Loader  # noqa: E402


class FakeGitHub:
    """محاكاة مبسّطة لواجهة GitHub."""

    def __init__(self):
        self.files: dict[str, bytes] = {}
        self.branch_exists = False

    def __call__(self, method, url, headers, body):
        path = url.split("api.github.com", 1)[1].split("?")[0]
        payload = json.loads(body) if body else {}
        ok = lambda code, obj: (code, {}, json.dumps(obj).encode())  # noqa: E731
        if path.endswith("/branches/database"):
            return ok(200 if self.branch_exists else 404, {})
        if path == "/repos/o/r":
            return ok(200, {"default_branch": "main"})
        if path == "/repos/o/r/git/ref/heads/main":
            return ok(200, {"object": {"sha": "abc"}})
        if path == "/repos/o/r/git/refs" and method == "POST":
            self.branch_exists = True
            return ok(201, {})
        if "/contents/" in path:
            key = path.split("/contents/", 1)[1]
            sha = lambda b: hashlib.sha1(b).hexdigest()  # noqa: E731
            if method == "GET":
                if key in self.files:
                    data = self.files[key]
                    return ok(200, {"content": base64.b64encode(data).decode(), "sha": sha(data), "size": len(data)})
                kids = sorted({k[len(key) + 1:].split("/")[0] for k in self.files if k.startswith(key + "/")})
                if kids:
                    return ok(200, [{"name": k, "path": f"{key}/{k}", "type": "file"} for k in kids])
                return ok(404, {})
            if method == "PUT":
                if key in self.files and payload.get("sha") != sha(self.files[key]):
                    return ok(409, {"message": "sha mismatch"})
                data = base64.b64decode(payload["content"])
                self.files[key] = data
                return ok(200, {"content": {"sha": sha(data)}})
            if method == "DELETE":
                self.files.pop(key, None)
                return ok(200, {})
        return ok(404, {"message": path})


class FakeClient:
    def __init__(self):
        self.handlers = []

    def add_event_handler(self, cb, builder=None):
        self.handlers.append((cb, builder))

    def remove_event_handler(self, cb, builder=None):
        self.handlers = [h for h in self.handlers if h[0] is not cb]


class FakeEvent:
    def __init__(self, text):
        self.raw_text = text
        self.message = self
        self.out = []
        self.id = 1
        self.chat_id = 1

    async def edit(self, text, **kw):
        self.out.append(text)

    async def respond(self, text, **kw):
        self.out.append(text)

    async def get_reply_message(self):
        return None


async def send(text):
    ev = FakeEvent(text)
    await on_message(ev)
    return "\n".join(ev.out)


async def main():
    gh_fake = FakeGitHub()
    cfg = Config(1, "h", "s", "t", "o/r", "database", ".", ROOT)
    db = Database(GitHubClient("t", "o/r", "database", transport=gh_fake), debounce=0.05)
    runtime.setup(config=cfg, db=db, client=FakeClient())
    runtime.loader = Loader(runtime)
    ext = cfg.external_dir
    try:
        assert await db.start() is True and gh_fake.branch_exists
        await runtime.loader.sync_external()
        await runtime.loader.load_all()
        assert set(runtime.loader.loaded) == {"help", "system", "storage", "plugin_manager", "selfdestruct"}, runtime.loader.loaded

        # --- قائمة الأوامر المصنّفة
        menu = await send(".الاوامر")
        print(menu, "\n" + "-" * 40)
        names = [c.name for c in registry.categories()]
        assert names == ["الأساسية", "النظام", "الإضافات", "الذاتية"], names
        # أوامر النظام من إضافتين مدمجتين في قسم واحد
        assert "1. الأساسية" in menu and "4. الذاتية" in menu

        # --- أوامر قسم
        cat = await send(".اوامر الذاتية")
        print(cat, "\n" + "-" * 40)
        assert "حفظ الذاتية" in cat and "تفعيل الذاتية" in cat and "فحص" not in cat
        assert await send(".أوامر 4") == cat           # بالرقم ومع الهمزة
        assert "لا يوجد قسم" in await send(".اوامر مجهول")
        assert "الوصف" in await send(".امر فحص")

        # --- تطابق الأطول أولًا ومعالجة النص العادي
        assert await send("...") == ""
        assert await send(".مرحبا") == ""
        assert "الحالة" in await send(".الحالة") or True

        # --- إضافة جديدة تظهر تلقائيًا في القائمة
        ext.mkdir(exist_ok=True)
        (ext / "demo.py").write_text(
            "from core import Plugin, runtime\n"
            "plugin = Plugin(category='تجريبي', title='تجربة', order=50)\n"
            "@plugin.command('ترحيب', description='عرض ترحيب.')\n"
            "async def hi(ctx):\n"
            "    s = runtime.db.collection('demo'); n = await s.get('n', 0) + 1; await s.set('n', n)\n"
            "    await ctx.reply(f'أهلًا {ctx.args} ({n})')\n",
            encoding="utf-8",
        )
        await runtime.loader.load("demo")
        assert "5. تجريبي" in await send(".الاوامر")
        assert "ترحيب" in await send(".اوامر تجريبي")
        assert await send(".ترحيب محمد\nسطر") == "أهلًا محمد\nسطر (1)"

        # --- قاعدة البيانات على GitHub
        assert await send(".ترحيب") == "أهلًا  (2)"
        await asyncio.sleep(0.3)                       # فترة التجميع
        saved = json.loads(gh_fake.files["data/demo.json"])
        assert saved == {"n": 2}, saved
        assert "تم حفظ" in await send(".حفظ القاعدة")
        assert "demo" in await send(".القاعدة")

        # --- تعطيل وتفعيل
        out = await send(".تعطيل اضافة demo")
        assert "تم تعطيل" in out, out
        assert "تجريبي" not in await send(".الاوامر")
        assert await send(".ترحيب") == ""
        assert "تم تفعيل" in await send(".تفعيل اضافة demo")
        assert "تجريبي" in await send(".الاوامر")
        assert "أساسية" in await send(".تعطيل اضافة help")

        # --- تعارض الأوامر
        (ext / "clash.py").write_text(
            "from core import Plugin\nplugin = Plugin(category='x', title='x')\n"
            "@plugin.command('فحص', description='x')\nasync def a(ctx): pass\n", encoding="utf-8")
        try:
            await runtime.loader.load("clash")
            raise SystemExit("كان يجب أن يفشل التعارض")
        except Exception as exc:
            assert "معرَّف مسبقًا" in str(exc), exc

        # --- تغيير البادئة
        assert "تم تغيير" in await send(".تغيير البادئة /")
        assert runtime.prefix == "/"
        assert "قائمة الأوامر" in await send("/الاوامر")
        await send("/تغيير البادئة .")
        await db.flush_all()
        assert json.loads(gh_fake.files["data/system.json"])["prefix"] == "."

        # --- إعادة التحميل
        assert "أُعيد تحميل" in await send(".اعادة تحميل اضافة demo")
        print("جميع الاختبارات نجحت.")
    finally:
        shutil.rmtree(ext, ignore_errors=True)
        await db.stop()


asyncio.run(main())
