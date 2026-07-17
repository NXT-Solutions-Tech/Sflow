# Changelog

All notable changes to SFlow. Versions follow the single source in
`config.APP_VERSION`.

## 3.0.0 — Market-ready (offline real + i18n + product UX)

The iteration that makes the offline promise true and the whole app honest.

### Offline, out of the box
- **ModelManager** (`core/models.py`): weights resolve bundle-first (the .app ships
  Parakeet) then the Hugging Face cache — never an implicit download. A missing
  local model raises `ModelNotDownloaded` → a truthful "download it in Ajustes →
  Modelo" toast (`CODE_MODEL_MISSING`), never the old false "missing API key".
- **Cancelable download UI** (`ui/model_download.py`): a real progress bar you start
  on purpose, in Settings → Modelo and an optional wizard step.
- **Local-first router**: selected engine unavailable/missing → bundled Parakeet
  (still on-device) → Groq only as a last resort.
- **Offline LLM cleanup**: new `"local"` provider (mlx-lm + Qwen2.5-1.5B-4bit),
  lazy-loaded, fail-open. Cleanup can now run with no network.
- **Private Command Mode**: transcribes on-device (`transcribe_raw`) — the audio no
  longer leaves the Mac; only the LLM transform uses the configured provider.

### Robustness (F1)
- Corrupt history DB recovers instead of crashing at launch (quarantine + recreate).
- SQLite WAL + busy_timeout; 0600 perms on the DB and personal dictionary.
- Dynamic `max_tokens` (no more silently truncated 5-minute dictations); Groq STT
  timeout scaled to the upload size.
- Recorder `stop()` guarded; hands-free recording auto-caps with a toast.
- API key kept out of `os.environ` (subprocess/numba workers never inherit it).
- `hotkey.log` rotates; paste-last restores the clipboard; start/done sounds work.

### Bilingual (F3)
- `core/i18n.py`: `tr()` + a `language` setting (auto/es/en). Error toasts, tray,
  sidebar, wizard model step, and the download UI are localized, with a
  build-breaking catalog-completeness check.

### Product UX (F4)
- Live re-skin via `rebuild_pages()` (theme/language change, no half-painted Hub).
- In-app toast (`ui/toast.py`) as the guaranteed error surface.
- Distinct cloud glyph for the cloud-fallback pill state.
- Menu bar: Pause, a Modelo submenu, and Paste-last.
- Pill remembers its dragged position; `text_faint` now meets WCAG AA in both
  themes; history filters by app / model / recency.
- Onboarding records "seen" only on completion (a mid-way close keeps the rescue).
- Microphone status added to `permissions.snapshot()`.

### Deferred (see ROADMAP)
Developer ID signing + notarization + DMG + Sparkle auto-update; streaming STT /
live preview; `raw_text`/`enhanced_text` + undo-AI; FTS5 search; opt-in telemetry.

## Earlier

Pre-3.0 the app already had: global-hotkey capture, local Whisper Turbo / Parakeet
with a Groq cloud fallback, LLM cleanup, per-app tone, Command Mode, a floating pill
with a live visualizer, SQLite history, a native light+dark Hub, and an onboarding
wizard covering the three TCC grants (mic / Accessibility / Input Monitoring).
