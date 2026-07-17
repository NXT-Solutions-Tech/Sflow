"""text_faint must meet WCAG AA (>=4.5:1) on its background, in both themes."""
from ui import theme


def test_contrast_ratio_endpoints():
    assert round(theme.contrast_ratio("#000000", "#ffffff"), 1) == 21.0
    assert theme.contrast_ratio("#ffffff", "#ffffff") == 1.0


def test_text_faint_meets_wcag_aa_in_both_themes():
    for scheme in ("dark", "light"):
        tok = theme.tokens(scheme)
        ratio = theme.contrast_ratio(tok["text_faint"], tok["bg"])
        assert ratio >= 4.5, f"{scheme}: text_faint {tok['text_faint']} = {ratio:.2f}:1"
