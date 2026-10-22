"""قراءة الإعدادات من متغيرات البيئة أو من ملف .env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .errors import ConfigError

REQUIRED = {
    "TG_API_ID": "معرّف التطبيق في تيليجرام (api_id)",
    "TG_API_HASH": "مفتاح التطبيق في تيليجرام (api_hash)",
    "TG_SESSION": "نص الجلسة (يُولَّد بالأداة tools/generate_session.py)",
    "GITHUB_TOKEN": "رمز الوصول الشخصي إلى GitHub",
    "GITHUB_REPO": "اسم المستودع بصيغة المالك/المستودع",
}


def load_env_file(path: Path) -> None:
    """تحميل ملف .env دون استبدال المتغيرات المعرَّفة مسبقًا في البيئة."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


@dataclass(frozen=True)
class Config:
    api_id: int
    api_hash: str
    session: str
    github_token: str
    github_repo: str
    github_branch: str
    prefix: str
    base_dir: Path

    @property
    def plugins_dir(self) -> Path:
        """مجلد الإضافات المدمجة."""
        return self.base_dir / "plugins"

    @property
    def external_dir(self) -> Path:
        """مجلد الإضافات المثبّتة (تُزامَن من المستودع عند كل تشغيل)."""
        return self.base_dir / "plugins_external"

    @classmethod
    def from_env(cls, base_dir: Path) -> "Config":
        load_env_file(base_dir / ".env")
        missing = [f"  - {key}: {label}" for key, label in REQUIRED.items() if not os.environ.get(key)]
        if missing:
            raise ConfigError("المتغيرات التالية مطلوبة ولم تُضبط:\n" + "\n".join(missing))
        try:
            api_id = int(os.environ["TG_API_ID"])
        except ValueError as exc:
            raise ConfigError("قيمة TG_API_ID يجب أن تكون رقمًا صحيحًا.") from exc
        repo = os.environ["GITHUB_REPO"].strip().strip("/")
        if repo.count("/") != 1:
            raise ConfigError("قيمة GITHUB_REPO يجب أن تكون بصيغة «المالك/المستودع».")
        return cls(
            api_id=api_id,
            api_hash=os.environ["TG_API_HASH"],
            session=os.environ["TG_SESSION"],
            github_token=os.environ["GITHUB_TOKEN"],
            github_repo=repo,
            github_branch=os.environ.get("GITHUB_BRANCH", "database"),
            prefix=os.environ.get("COMMAND_PREFIX", "."),
            base_dir=base_dir,
        )
