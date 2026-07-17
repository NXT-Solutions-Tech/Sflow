"""Pure-logic unit tests for previously-untested modules: STT model resolver,
smart-command punctuation rules, dictionary-learner heuristics, snippet
matching, transform bounds, and the Groq hallucination filter."""
import config
from core.smart_commands import apply as smart
from core.dictionary_learner import diff_candidates
from core.transcriber_groq import _is_hallucination
from core.transform import TransformHandler
import core.snippets_matcher as sm
from db.snippets import SnippetsDB


# ---- config.get_stt_model ----
def test_get_stt_model_unknown_id_falls_back_to_groq():
    config.set_setting("stt_model", "does-not-exist")
    assert config.get_stt_model()["id"] == "groq-turbo"


def test_get_stt_model_known_id():
    config.set_setting("stt_model", "parakeet-v3")
    assert config.get_stt_model()["id"] == "parakeet-v3"


# ---- smart_commands ----
def test_smart_commands_punctuation():
    assert smart("uno coma dos") == "uno, dos"
    assert smart("a dos puntos b") == "a: b"
    assert smart("x punto y coma y") == "x; y"


def test_smart_commands_paragraph_and_newline():
    assert smart("fin punto y aparte inicio") == "fin.\n\ninicio"
    assert smart("linea uno nueva línea linea dos") == "linea uno\nlinea dos"


def test_smart_commands_collapse_blank_lines():
    assert smart("a\n\n\n\nb") == "a\n\nb"


# ---- dictionary_learner.diff_candidates ----
def test_diff_candidates_keeps_proper_nouns():
    c = diff_candidates("el equipo se reunió",
                        "el equipo Kubernetes se reunió con Anthropic")
    assert "Kubernetes" in c and "Anthropic" in c


def test_diff_candidates_filters_noise():
    c = diff_candidates("hola", "hola para rapidamente si")
    # "para"/"si" stopword or <4, "rapidamente" lowercase non-proper → all filtered
    assert c == []


# ---- snippets_matcher ----
def test_snippets_start_empty(tmp_path):
    # Seeding would paste someone else's data (or a placeholder) into real writing.
    assert SnippetsDB(str(tmp_path / "s.db")).list_all() == []


def test_snippet_longest_trigger_wins(tmp_path, monkeypatch):
    db = SnippetsDB(str(tmp_path / "s.db"))
    db.add("codigo", "CORTO")
    db.add("codigo secreto", "LARGO")
    monkeypatch.setattr(sm, "_db", lambda: db)
    out = sm.apply("el codigo secreto va aquí")
    assert "LARGO" in out and "CORTO" not in out


def test_snippet_respects_word_boundary(tmp_path, monkeypatch):
    db = SnippetsDB(str(tmp_path / "s.db"))
    db.add("token", "REEMPLAZO")
    monkeypatch.setattr(sm, "_db", lambda: db)
    assert sm.apply("tokens varios") == "tokens varios"


# ---- transform bounds ----
def test_transform_get_prompt_out_of_range():
    h = TransformHandler()
    assert h.get_prompt(-1) == ("", "")
    assert h.get_prompt(999) == ("", "")


def test_transform_run_empty_selection_is_noop():
    assert TransformHandler().run(0, "") == ""


# ---- hallucination filter ----
def test_is_hallucination_markers():
    assert _is_hallucination("Gracias por ver el video")
    assert _is_hallucination("Thanks for watching!")
    assert not _is_hallucination("hola cómo estás")
    assert not _is_hallucination("")
