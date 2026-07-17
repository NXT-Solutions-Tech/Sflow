"""The personal dictionary is created 0600 — it can hold names and text
substitutions that no other user on the machine should read."""
import os

import core.dictionary as d


def test_dictionary_is_created_0600(tmp_path, monkeypatch):
    p = tmp_path / "dictionary.txt"
    monkeypatch.setattr(d, "DICTIONARY_PATH", str(p))

    d.load_terms()  # triggers _ensure_file

    assert p.exists()
    assert oct(os.stat(p).st_mode & 0o777) == "0o600"
