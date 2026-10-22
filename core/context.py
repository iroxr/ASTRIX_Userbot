"""سياق تنفيذ الأمر: يُمرَّر إلى كل معالج أمر."""
from __future__ import annotations

from telethon.errors import MessageNotModifiedError

from .registry import Command
from .runtime import runtime
from .text import split_message


class Context:
    def __init__(self, event, command: Command, args: str):
        self.event = event
        self.message = event.message
        self.command = command
        self.args = args.strip()
        self.runtime = runtime

    @property
    def arg_list(self) -> list[str]:
        return self.args.split()

    @property
    def db(self):
        return runtime.db

    @property
    def client(self):
        return runtime.client

    @property
    def prefix(self) -> str:
        return runtime.prefix

    async def edit(self, text: str) -> None:
        """تعديل رسالة الأمر نفسها (بصيغة HTML)."""
        try:
            await self.event.edit(text, parse_mode="html", link_preview=False)
        except MessageNotModifiedError:
            pass

    async def reply(self, text: str) -> None:
        """عرض الجواب بتعديل رسالة الأمر، مع تقسيم النصوص الطويلة."""
        chunks = split_message(text)
        await self.edit(chunks[0])
        for extra in chunks[1:]:
            await self.event.respond(extra, parse_mode="html", link_preview=False)

    async def send(self, text: str) -> None:
        """إرسال رسالة جديدة في المحادثة نفسها."""
        await self.event.respond(text, parse_mode="html", link_preview=False)

    async def fail(self, text: str) -> None:
        """عرض رسالة تعذّر التنفيذ بصيغة موحّدة."""
        await self.reply(f"<b>تعذّر تنفيذ الأمر.</b>\n{text}")

    async def delete(self) -> None:
        await self.event.delete()

    async def get_reply(self):
        """الرسالة التي يردّ عليها الأمر، أو None."""
        return await self.event.get_reply_message()

    def usage_hint(self) -> str:
        from .text import escape
        cmd = self.command
        return f"<code>{escape(self.prefix + cmd.name + (' ' + cmd.usage if cmd.usage else ''))}</code>"
