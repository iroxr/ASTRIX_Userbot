"""أدوات نصية مشتركة: التطبيع، والتنسيق، وصيغ الجمع العربية."""
from __future__ import annotations

import html
import re

_DIACRITICS = re.compile("[ـً-ٰٟ]")
_LETTER_MAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي"})


def normalize(text: str) -> str:
    """توحيد النص العربي للمطابقة: إزالة التشكيل والتطويل وتوحيد الألف والياء."""
    text = _DIACRITICS.sub("", text).translate(_LETTER_MAP).casefold()
    return re.sub(r"\s+", " ", text).strip()


def strip_definite_article(text: str) -> str:
    """حذف «ال» التعريف من بداية الكلمة المطبَّعة (لتسهيل المطابقة)."""
    return text[2:] if text.startswith("ال") and len(text) > 3 else text


def escape(value: object) -> str:
    """تهريب النص ليكون آمنًا داخل رسائل HTML."""
    return html.escape(str(value), quote=False)


def split_message(text: str, limit: int = 4000) -> list[str]:
    """تقسيم نص طويل إلى أجزاء لا يتجاوز كلٌّ منها الحد الذي يسمح به تيليجرام."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def plural(n: int, forms: tuple[str, str, str, str]) -> str:
    """اختيار صيغة العدد العربية: (المفرد، المثنى، الجمع من 3 إلى 10، التمييز المنصوب).

    مثال: plural(3, ("أمر واحد", "أمران", "{n} أوامر", "{n} أمرًا"))
    """
    one, two, few, many = forms
    if n == 1:
        form = one
    elif n == 2:
        form = two
    elif 3 <= n <= 10:
        form = few
    else:
        form = many
    return form.format(n=n)


def format_duration(seconds: float) -> str:
    """تحويل عدد من الثواني إلى عبارة عربية مقروءة."""
    seconds = int(seconds)
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    parts: list[str] = []
    if days:
        parts.append(plural(days, ("يوم واحد", "يومان", "{n} أيام", "{n} يومًا")))
    if hours:
        parts.append(plural(hours, ("ساعة واحدة", "ساعتان", "{n} ساعات", "{n} ساعةً")))
    if minutes:
        parts.append(plural(minutes, ("دقيقة واحدة", "دقيقتان", "{n} دقائق", "{n} دقيقةً")))
    if secs or not parts:
        parts.append(plural(secs, ("ثانية واحدة", "ثانيتان", "{n} ثوانٍ", "{n} ثانيةً")))
    return " و".join(parts)
