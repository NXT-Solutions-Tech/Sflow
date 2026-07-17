"""Dynamic max_tokens: a fixed 1500 truncated 5-minute dictations in silence."""
from core.token_budget import max_tokens_for


def test_floor_is_respected_for_short_text():
    # Each caller's historical minimum is preserved as the floor.
    assert max_tokens_for("", floor=1500) == 1500
    assert max_tokens_for("hola", floor=2000) == 2000


def test_none_is_safe():
    assert max_tokens_for(None, floor=1500) == 1500


def test_grows_with_input_beyond_the_floor():
    """A long dictation must get MORE than the old fixed 1500 that cut it off."""
    long = "palabra " * 2000  # ~16k chars, well past a 5-minute dictation
    assert max_tokens_for(long, floor=1500) > 1500


def test_capped_so_a_giant_input_cannot_blow_the_budget():
    assert max_tokens_for("x" * 500_000, floor=1500) == 8000
