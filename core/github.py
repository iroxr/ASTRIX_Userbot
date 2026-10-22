"""عميل خفيف لواجهة GitHub (Contents API) يعتمد على المكتبة القياسية فقط."""
from __future__ import annotations

import asyncio
import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable
from urllib.parse import quote

from .errors import StorageError

API = "https://api.github.com"

# (الطريقة، العنوان، الترويسات، الجسم) -> (رمز الحالة، الترويسات، الجسم)
Transport = Callable[[str, str, dict, "bytes | None"], "tuple[int, dict, bytes]"]


@dataclass(slots=True)
class RemoteFile:
    content: bytes
    sha: str


def _urllib_transport(method: str, url: str, headers: dict, body: "bytes | None"):
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers or {}), exc.read()


class GitHubClient:
    def __init__(self, token: str, repo: str, branch: str, *, transport: "Transport | None" = None):
        self.repo = repo
        self.branch = branch
        self._transport = transport or _urllib_transport
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "telegram-userbot",
        }

    # ------------------------------------------------------------------ أساسيات
    async def _request(self, method: str, path: str, *, params: "dict | None" = None,
                       payload: "dict | None" = None) -> "tuple[int, dict]":
        url = API + path
        if params:
            url += "?" + "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items())
        body = json.dumps(payload).encode() if payload is not None else None
        headers = dict(self._headers)
        if body is not None:
            headers["Content-Type"] = "application/json"

        last: "Exception | None" = None
        for attempt in range(4):
            try:
                status, resp_headers, raw = await asyncio.to_thread(self._transport, method, url, headers, body)
            except OSError as exc:
                last = exc
            else:
                if status < 500:
                    self._guard(status, resp_headers)
                    try:
                        data = json.loads(raw.decode("utf-8")) if raw else {}
                    except ValueError:
                        data = {}
                    return status, data
                last = StorageError(f"أعاد GitHub الرمز {status}.")
            if attempt < 3:
                await asyncio.sleep(2 ** attempt)
        raise StorageError("تعذّر الاتصال بـ GitHub بعد عدة محاولات.") from last

    @staticmethod
    def _guard(status: int, headers: dict) -> None:
        lowered = {k.lower(): v for k, v in headers.items()}
        if status == 401:
            raise StorageError("رمز الوصول إلى GitHub غير صالح أو منتهي الصلاحية.")
        if status in (403, 429) and (lowered.get("x-ratelimit-remaining") == "0" or "retry-after" in lowered):
            raise StorageError("تم تجاوز الحد المسموح من الطلبات إلى GitHub. يُرجى المحاولة لاحقًا.")

    @staticmethod
    def _fail(status: int, data: dict, action: str) -> StorageError:
        detail = data.get("message", "") if isinstance(data, dict) else ""
        return StorageError(f"تعذّر تنفيذ العملية ({action}). رمز الحالة {status}. {detail}".strip())

    def _contents(self, path: str) -> str:
        return f"/repos/{self.repo}/contents/{quote(path)}"

    # ------------------------------------------------------------------ الفرع
    async def ensure_branch(self) -> bool:
        """التأكد من وجود فرع قاعدة البيانات وإنشاؤه من الفرع الافتراضي عند غيابه."""
        status, data = await self._request("GET", f"/repos/{self.repo}/branches/{quote(self.branch, safe='')}")
        if status == 200:
            return False
        if status != 404:
            raise self._fail(status, data, "التحقق من الفرع")
        status, repo = await self._request("GET", f"/repos/{self.repo}")
        if status == 404:
            raise StorageError("المستودع غير موجود، أو أن الرمز لا يملك صلاحية الوصول إليه.")
        if status != 200:
            raise self._fail(status, repo, "قراءة المستودع")
        default = repo["default_branch"]
        status, ref = await self._request("GET", f"/repos/{self.repo}/git/ref/heads/{quote(default, safe='')}")
        if status != 200:
            raise StorageError("المستودع فارغ. يُرجى إنشاء أول إيداع (مثل ملف README) ثم إعادة المحاولة.")
        status, created = await self._request(
            "POST", f"/repos/{self.repo}/git/refs",
            payload={"ref": f"refs/heads/{self.branch}", "sha": ref["object"]["sha"]},
        )
        if status != 201:
            raise self._fail(status, created, "إنشاء فرع قاعدة البيانات")
        return True

    # ------------------------------------------------------------------ الملفات
    async def get_file(self, path: str) -> "RemoteFile | None":
        status, data = await self._request("GET", self._contents(path), params={"ref": self.branch})
        if status == 404:
            return None
        if status != 200 or isinstance(data, list):
            raise self._fail(status, data, "قراءة ملف")
        if data.get("content"):
            raw = base64.b64decode(data["content"])
        elif data.get("size", 0) == 0:
            raw = b""
        else:  # الملفات الأكبر من 1 ميغابايت تُقرأ عبر واجهة الكتل
            status, blob = await self._request("GET", f"/repos/{self.repo}/git/blobs/{data['sha']}")
            if status != 200:
                raise self._fail(status, blob, "قراءة ملف كبير")
            raw = base64.b64decode(blob["content"])
        return RemoteFile(raw, data["sha"])

    async def put_file(self, path: str, content: bytes, message: str, sha: "str | None" = None) -> str:
        """إنشاء الملف أو تحديثه، وتُعاد قيمة sha الجديدة. تُعالَج حالات التعارض تلقائيًا."""
        for _ in range(3):
            payload = {"message": message, "content": base64.b64encode(content).decode(), "branch": self.branch}
            if sha:
                payload["sha"] = sha
            status, data = await self._request("PUT", self._contents(path), payload=payload)
            if status in (200, 201):
                return data["content"]["sha"]
            if status in (409, 422):
                current = await self.get_file(path)
                if current and current.content == content:
                    return current.sha
                sha = current.sha if current else None
                continue
            raise self._fail(status, data, "كتابة ملف")
        raise StorageError("تعذّر حفظ الملف بسبب تعارض متكرر في الإصدارات.")

    async def delete_file(self, path: str, message: str) -> bool:
        current = await self.get_file(path)
        if current is None:
            return False
        status, data = await self._request(
            "DELETE", self._contents(path),
            payload={"message": message, "sha": current.sha, "branch": self.branch},
        )
        if status != 200:
            raise self._fail(status, data, "حذف ملف")
        return True

    async def list_dir(self, path: str) -> list[dict]:
        status, data = await self._request("GET", self._contents(path), params={"ref": self.branch})
        if status == 404:
            return []
        if status != 200 or not isinstance(data, list):
            raise self._fail(status, data, "قراءة مجلد")
        return data
