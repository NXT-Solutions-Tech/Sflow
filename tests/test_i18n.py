"""i18n: catalog completeness (the build-breaker), tr() behaviour, language
resolution, and that error toasts localize."""
import config
import core.i18n as i18n
from core import error_messages as em


# ---------- catalog completeness: the gate ----------
def test_every_key_has_both_languages_and_no_orphans():
    """A half-translated string can never ship: every key must define es AND en,
    both non-empty, and no stray language codes."""
    for key, entry in i18n.CATALOG.items():
        assert set(entry.keys()) == set(i18n.LANGUAGES), f"{key} langs={set(entry.keys())}"
        for lang in i18n.LANGUAGES:
            assert entry[lang].strip(), f"{key}[{lang}] is empty"


def test_every_error_code_has_a_catalog_entry():
    """message_for() builds err.<code>.title/.body — every code must resolve, or
    a real failure would show the raw key to the user."""
    for code in em.CODES:
        assert f"err.{code}.title" in i18n.CATALOG
        assert f"err.{code}.body" in i18n.CATALOG


# ---------- tr ----------
def test_tr_returns_spanish_by_default():
    assert i18n.tr("tray.quit") == "Salir"


def test_tr_returns_english_when_language_is_en():
    config.set_setting("language", "en")
    assert i18n.tr("tray.quit") == "Quit"
    assert i18n.tr("nav.history") == "History"


def test_tr_unknown_key_returns_itself():
    assert i18n.tr("no.such.key") == "no.such.key"


def test_tr_formats_placeholders():
    config.set_setting("language", "en")
    assert "250" in i18n.tr("download.subtitle", size=250)


# ---------- resolve_language ----------
def test_explicit_language_wins():
    config.set_setting("language", "en")
    assert i18n.resolve_language() == "en"
    config.set_setting("language", "es")
    assert i18n.resolve_language() == "es"


def test_auto_follows_system_locale(monkeypatch):
    config.set_setting("language", "auto")

    class _FakeLocale:
        @staticmethod
        def system():
            return type("L", (), {"name": lambda self: "en_US"})()

    monkeypatch.setattr("PyQt6.QtCore.QLocale", _FakeLocale, raising=False)
    assert i18n.resolve_language() == "en"


# ---------- error toasts localize ----------
def test_error_toast_is_spanish_by_default():
    body = em.message_for(em.CODE_PASTE_FAILED).body
    assert "historial" in body.lower()


def test_error_toast_localizes_to_english():
    config.set_setting("language", "en")
    toast = em.message_for(em.CODE_OFFLINE)
    assert toast.title == "No connection"
    assert "internet" in toast.body.lower()


def test_error_toast_title_stays_short_in_both_languages():
    for code in em.CODES:
        for lang in ("es", "en"):
            config.set_setting("language", lang)
            assert len(em.message_for(code).title) < 40, (code, lang)
