"""Text substitutions — expand abbreviations from the personal dictionary.

Lines like "btw -> by the way" in the dictionary file become automatic,
case-insensitive, word-boundary replacements applied to the final transcript
(e.g. after cleanup). Case of the trigger's first letter is preserved on the
replacement ("Btw" -> "By the way").
"""
import re
from core.dictionary import load_substitutions


def _make_repl(to: str):
    def _repl(m: re.Match) -> str:
        matched = m.group(0)
        if matched[:1].isupper():
            return to[:1].upper() + to[1:]
        return to
    return _repl


def apply(text: str) -> str:
    if not text or not text.strip():
        return text
    for frm, to in load_substitutions():
        if not frm:
            continue
        pattern = re.compile(r"\b" + re.escape(frm) + r"\b", re.IGNORECASE)
        text = pattern.sub(_make_repl(to), text)
    return text
