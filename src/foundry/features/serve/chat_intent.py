from __future__ import annotations

import re


_GREETING_RE = re.compile(r"^(hi|hello|hey|yo|hola|namaste|good (morning|afternoon|evening))[\s!.?]*$", re.I)


def is_small_talk(prompt: str) -> bool:
    text = prompt.strip()
    if not text:
        return True
    if len(text.split()) > 6:
        return False
    if _GREETING_RE.match(text):
        return True
    lowered = text.lower()
    if lowered in {"thanks", "thank you", "ok", "okay", "bye", "goodbye"}:
        return True
    return False
