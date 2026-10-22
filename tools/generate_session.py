"""أداة توليد نص الجلسة (TG_SESSION). تُشغَّل مرة واحدة على جهازك:

    python tools/generate_session.py
"""
import asyncio

from telethon import TelegramClient
from telethon.sessions import StringSession


async def main() -> None:
    api_id = int(input("api_id: ").strip())
    api_hash = input("api_hash: ").strip()
    async with TelegramClient(StringSession(), api_id, api_hash) as client:
        await client.start()  # يطلب رقم الهاتف ورمز التحقق
        print("\nنص الجلسة (احتفظ به سرًّا، فهو يمنح وصولًا كاملًا إلى حسابك):\n")
        print(client.session.save())


if __name__ == "__main__":
    asyncio.run(main())
