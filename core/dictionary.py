"""Personal vocabulary dictionary. Fed to Whisper as `prompt=` hint.

Whisper uses the prompt as vocabulary bias — boosts recognition of proper
nouns, jargon, acronyms, etc. The `prompt` is NOT prepended to the output.

File format: plain text, one term or phrase per line, # comments allowed.
Max ~224 tokens is Whisper's hard limit — keep concise.
"""
import os
import re
from config import DICTIONARY_PATH


# Substitution syntax: "abreviatura -> texto completo" (also => or →).
_SEP_RE = re.compile(r"\s*(?:->|=>|→)\s*")


# Seeded verbatim into every install, and every line here is fed to Whisper as a
# vocabulary hint on every dictation — so it holds only terms this app itself
# needs recognised. A person's name would bias each transcription towards a
# stranger (the upstream author's was seeded here for a while).
_DEFAULT_SEED = """# SFlow Personal Dictionary
# One word, name, or phrase per line. Used as Whisper vocabulary hint.
# For text substitutions use an arrow:  btw -> by the way
# Add your own names, jargon and acronyms below.

SFlow
Groq
Whisper
Parakeet
btw -> by the way
"""


def _is_substitution(line: str) -> bool:
    return bool(_SEP_RE.search(line))


def _ensure_file():
    if not os.path.exists(DICTIONARY_PATH):
        os.makedirs(os.path.dirname(DICTIONARY_PATH), exist_ok=True)
        with open(DICTIONARY_PATH, "w") as f:
            f.write(_DEFAULT_SEED)


def load_terms() -> list[str]:
    _ensure_file()
    terms = []
    with open(DICTIONARY_PATH) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                terms.append(line)
    return terms


def load_substitutions() -> list[tuple[str, str]]:
    """Parse 'from -> to' lines into (from, to) pairs, longest trigger first."""
    _ensure_file()
    subs = []
    with open(DICTIONARY_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = _SEP_RE.split(line, maxsplit=1)
            if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                subs.append((parts[0].strip(), parts[1].strip()))
    subs.sort(key=lambda p: len(p[0]), reverse=True)
    return subs


def as_whisper_prompt(max_chars: int = 800) -> str:
    """Pack vocab terms into a comma-separated hint, truncated to avoid token cap.
    Substitution lines (a -> b) are excluded — they're not vocabulary."""
    terms = [t for t in load_terms() if not _is_substitution(t)]
    if not terms:
        return ""
    joined = ", ".join(terms)
    if len(joined) > max_chars:
        joined = joined[:max_chars].rsplit(",", 1)[0]
    return joined
