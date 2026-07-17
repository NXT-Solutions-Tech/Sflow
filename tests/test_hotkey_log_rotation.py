"""hotkey.log rotates at ~1MB — it used to grow unbounded (it writes on every
keypress lifecycle event)."""
import core.hotkey as hk


def test_hotkey_log_rotates_at_max_bytes(tmp_path, monkeypatch):
    logp = tmp_path / "hotkey.log"
    monkeypatch.setattr(hk, "_LOG_PATH", str(logp))
    monkeypatch.setattr(hk, "_MAX_BYTES", 200)
    logp.write_text("x" * 300)  # already past the cap

    hk._log("nueva linea")

    assert (tmp_path / "hotkey.log.1").exists()  # old generation moved aside
    body = logp.read_text()
    assert "nueva linea" in body
    assert len(body) < 300  # fresh file, not the old bloat
