"""Output-token budget for the LLM calls (cleanup / transform / command mode).

A fixed ``max_tokens`` silently truncates long dictations: a 5-minute cleanup
whose output ran past the old 1500-token cap was cut off mid-sentence with no
error and no way for the user to tell. Since cleanup/transform output length
tracks the input, size the budget from the input instead of pinning it.
"""

# These models (Groq Llama 3.3 70B, OpenRouter GLM) allow output far above this;
# 8k tokens is ~24k characters, longer than any single dictation, so the ceiling
# is a runaway guard, not a real limit anyone hits.
_CEIL = 8000


def max_tokens_for(text: str, floor: int = 1024, ceil: int = _CEIL) -> int:
    """Pick a max_tokens that won't truncate the output for ``text``.

    ~1 token per 3 characters for es/en, times 1.5 headroom for the punctuation
    and capitalization cleanup adds, plus a small constant. ``floor`` preserves
    each caller's historical minimum (so this can only ever grow the budget,
    never shrink it below what a call used to get).
    """
    est = int(len(text or "") / 3 * 1.5) + 256
    return max(floor, min(ceil, est))
