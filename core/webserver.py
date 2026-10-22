"""خادم فحص الصحة: يفتح المنفذ الذي تشترطه الاستضافات المجانية (مثل Render Web Service).

يُشغَّل تلقائيًا عند وجود المتغير PORT، ويردّ على أي طلب HTTP بالنص OK
كي تتمكن خدمات المراقبة من إبقاء الخدمة مستيقظة.
"""
from __future__ import annotations

import asyncio

_RESPONSE = (
    b"HTTP/1.1 200 OK\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n"
    b"Content-Length: 2\r\n"
    b"Connection: close\r\n\r\nOK"
)


async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        await asyncio.wait_for(reader.read(1024), timeout=5)
        writer.write(_RESPONSE)
        await writer.drain()
    except (asyncio.TimeoutError, ConnectionError):
        pass
    finally:
        writer.close()


async def start(port: int) -> asyncio.AbstractServer:
    return await asyncio.start_server(_handle, "0.0.0.0", port)
