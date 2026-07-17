# SFlow — Roadmap toward Wispr Flow parity

Iterate SFlow (Python 3.12 · PyQt6 · PyObjC · sounddevice) toward Wispr Flow feature
parity, quality-first, never breaking a working feature. Three tracks advanced in priority
order: **(1) transcription quality → (2) settings GUI → (3) app interface**.

**Operating rules:** branch per milestone · commit after each phase gate · one phase at a
time · preserve working features (hotkeys, non-focus-stealing pill, auto-paste, SQLite,
dashboard) · fail-open on network/LLM · no secrets in git/logs · verify volatile library
APIs at build time.

Related docs: [`PRP-sflow-local-llm.md`](PRP-sflow-local-llm.md) (local-STT + OpenRouter
cleanup PRP) · this file. Kickoff prompt lives in the session that created the plan.

---

## Milestones

| # | Track | Goal | Size | Status |
|---|-------|------|------|--------|
| M1 | Interface | Reactive pill: live waveform + visibility bound to dictation state (fade in/out, no idle pill) | S | **DONE** ✅ |
| M2 | Quality | Auto Cleanup levels None/Light/Medium (None bypasses LLM) | M | **DONE** ✅ |
| M3 | Quality | Text substitutions ("btw→by the way") as a post-transcription pass, editable in Dictionary | M | **DONE** ✅ |
| M4 | Settings | Unified native Settings window, General/System tabs; consolidate the two UIs; keys→Keychain | L | **DONE** ✅ |
| M5 | Settings | Transforms editor for the 8 Opt+N prompt slots | S | **DONE** ✅ |
| M6 | Interface | Richer Insights (WPM, per-app usage, streak) — needs DB columns | L | **DONE** ✅ |

---

> **M1 CLOSED ✅** — accepted on-device. Commits: `be29347` (state-bound show/hide),
> `fix(pill)` (fade hardening), `feat(pill): larger, fuller audio waveform`. Next: **M2**.

## M1 (done) — Reactive audio-waveform pill

**Branch:** `feat/pill-reactive`. Outcome: pill fades in with live voice-reactive bars while
dictating/processing, then fades out and is fully hidden. No persistent idle pill.

### Recon findings (Phase 1.0)
- Pill = **Qt `PillWidget(QWidget)`** (`ui/pill_widget.py:23`), not a native NSWindow → fade
  via Qt `setWindowOpacity` + `QPropertyAnimation` (maps to `NSWindow.alphaValue` on cocoa).
  Native fallback available via the `NSWindow` handle in `_setup_native_macos` (`:90`).
- **Bars already driven by real mic audio** — FFT + spring physics over the shared
  `recorder.audio_queue` in `AudioVisualizer._update_bars` (`ui/audio_visualizer.py:94-163`).
  So Phases 1.1/1.2 pre-exist.
- The pill was **shown once at startup (`main.py:255`) and never hidden**; `set_state()`
  (`ui/pill_widget.py:154`) only changed width + visualizer visibility — no opacity fade.
- Reference pattern: `RedDotIndicator` binds visibility to state (`ui/red_dot_indicator.py:75-84`).

### Phase checklist
- [x] **1.0 Recon** — symbols mapped (above).
- [x] **1.1 Real amplitude → GUI** — pre-existing; validated headless (voice fills bars to
  0.98, silence 0.04, 24× ratio).
- [x] **1.2 Smooth 60fps animation** — pre-existing; validated (VIZ timer runs while
  recording, stops otherwise).
- [x] **1.3 Visibility bound to state + fades** — added `fade_in`/`fade_out` +
  `_on_fade_out_done` and wired them into `set_state()`; startup no longer force-shows the
  pill (`main.py:start`). Headless state-machine test: idle→hidden, recording→visible+viz on,
  processing→visible+viz off, done→visible, idle→hidden, rapid start/stop/start→single pill.
  All pass.
- [x] **Gate 1.3 (real-display acceptance)** — **ACCEPTED by user (2026-07-15)** on their Mac:
  pill fades in on dictation, bars react live, pastes with no focus steal, fades out. Follow-up
  tuning `feat(pill): larger, fuller audio waveform` (taller/wider/brighter bars) — accepted.
  Also hardened the fade so it can never leave the pill stuck invisible.

### Session handoff (all milestones complete)
- **M1–M6 all DONE**, each validated headless and committed. Branches: `feat/pill-reactive`
  (M1) → `feat/cleanup-levels` (M2–M6 stacked). Key commits: `be29347`/`1bdcc90` pill,
  `e9172a6` cleanup levels, `334d9a5` substitutions, `c9b1a15` settings+Keychain, `00c97d9`
  transforms editor, `964b114` insights, plus the settings-tabs scroll polish.
- **Validated headless:** full `SFlowApp` graph constructs; 34 modules import; all 7 Hub
  pages construct + reload; pill state machine; real-audio bars (24× voice/silence); Auto
  Cleanup Light≠Medium via real LLM; substitutions; Keychain roundtrip; insights math
  (WPM/per-app/streak + legacy backfill); dashboard via Playwright. UI previews rendered
  (settings General/System, Transforms, Insights) — clean/minimalist.
- **On-device acceptance — ACCEPTED by user (2026-07-15):** ran `python3 main.py`, migration
  applied to real history with no traceback, and all new GUI surfaces (tabbed Settings +
  Keychain, Transforms editor, Insights, Auto Cleanup levels, substitutions) approved.
  **All six milestones complete and accepted.** Remaining step: package via `bash build.sh`.
- **Deferred (noted):** raw-text preservation for "undo AI edit" (Wispr parity) — deferred
  from M2 to a future pass; dashboard footer still says "Groq Whisper" (cosmetic).
- **Open decision:** none blocking.

## Code review vs PRP + ROADMAP (2026-07-17) — **DONE ✅**

A full review against [`PRP-sflow-local-llm.md`](PRP-sflow-local-llm.md) and this file
(3 parallel audits: plan-vs-code, security, paste/focus). Verdict: the engine beats Wispr
(CGEvent paste never touches the clipboard — *better* than the PRP's "clipboard survives"
criterion; local STT by default; the pill genuinely never steals focus). What lagged was
the **contract with the user**: three UI controls that lied. All fixed on `feat/onboarding`.

- [x] **Command Mode toggle was inert** — `hotkey.py` never read `command_mode_enabled`,
  yet it sat in `_restart_snapshot()`, so the Hub promised a relaunch and the user believed
  it applied. It uploads audio **and the current selection** to Groq → now opt-in
  (default `False`), honoured live, no relaunch.
- [x] **"Focus Mode" switch was a placebo** — wrote a setting only a never-imported module
  read. Removed with the module.
- [x] **The cloud fallback was silent** — the default model is labelled *offline*; when MLX
  failed the audio went to Groq behind a normal DONE check. Now `STATE_DONE_CLOUD` (amber,
  held longer) via `_was_cloud_fallback()`.
- [x] **Voice recordings leaked forever** — 26 of 44 WAVs on disk were orphans (5.8 MB): the
  WAV was written *before* the insert, so any failed dictation left a permanent recording
  the row-driven prune could never see. Now every no-insert path discards it, plus an
  mtime sweep (`prune_orphan_audio_files`) as the net.
- [x] **API key hygiene** — the `.env` cleartext copy was written *even when the Keychain
  accepted* ("fallback" in name only, and nothing ever deleted it). Now Keychain-only
  unless it refuses, created 0600 via `os.open`+`fchmod` (the old post-hoc `chmod` left a
  world-readable window, and `O_TRUNC` alone inherits an existing 0644).
- [x] **Paste stole focus** — `_restore_focus()` ran on *every* paste, activating an app
  that was already frontmost: the flash, and a foco-grab if the user switched windows
  mid-transcription. Dropped from the keystroke path (kept for clipboard, which needs it).
- [x] **`copy_selection` lost selections silently** — compared clipboard *content*; now
  `changeCount`. Plus `timeout` on the repo's only unguarded `subprocess`.
- [x] **Prompt-injection guard was half-applied** — the PRP marked it "Keep that rule"; it
  existed only in Medium. Added to `_BASE_RULES` (Light).
- [x] **Author PII shipped to every user** — `db/snippets.py` seeded the upstream author's
  real email/signature; "mi correo" pasted a stranger's address.
- [x] **Tests wrote to the real `sflow.log`** — 93 lines per run into the user's dictation
  log; simulated-failure WARNs read as real incidents (this cost the audit 10 minutes of
  chasing a phantom). `conftest.py` now isolates both loggers.
- [x] **Dead code + stale docs** — deleted `core/clipboard.py`, `core/focus_mode.py` (and
  `core.clipboard` from `sflow.spec`'s hiddenimports, where it was pinned *because* nothing
  imported it). Wired `core/dictation_actions.py`: the "dale enter" hotkey CLAUDE.md had
  advertised for versions was implemented but never connected. CLAUDE.md corrected.
- [x] **The PRP wasn't in the repo** — it lived in `~/Downloads`; this file's link to it had
  always been broken. Committed.

Deviations from the PRP, accepted: `STT_BACKEND`→`stt_model` and `ENHANCE_ENABLED`→
`auto_cleanup_level` (both richer than the flags the PRP asked for), toggles in the Hub
rather than the menu bar (criterion #78), `raw_text`/`enhanced_text` still deferred, and
the raw-vs-enhanced dashboard retired with Flask.

## Post-audit backlog (2026-07-15)

A 4-agent audit (backend, security, UX-vs-Wispr, stability) ran on the whole app. The
security/reliability findings were **fixed** on `feat/visual-refactor` (see CLAUDE.md
"Auto-Blindaje log"). The remaining items are product/UX bets, prioritized:

### High-value UX (Wispr-parity)
- [x] **Permission onboarding wizard** — `ui/onboarding_wizard.py`, shipped on
  `feat/onboarding` (2026-07-17). Mic (live level test) + Accessibility + Input Monitoring
  with "Concedido ✓" polling. Also the rescue flow when a rebuild revokes a grant.
- [x] **Optional API key for local-only users** — `onboarding.api_key_required()`. The key
  step only appears for a cloud model or Auto Cleanup; otherwise "Continuar sin conexión".
- [x] **Informative error surfacing** — `core/error_messages.py` → tray toast. Also fixed
  the pill flashing DONE on a failed paste.
- [ ] **Real-time / pre-paste transcription preview** — biggest "premium feel" lever;
  today only a spinner shows during processing.
- [ ] **Idle discoverability** — the pill is fully hidden when idle; add a coach mark or
  optional idle nub with the hotkey tooltip.

### Medium
- [ ] Configurable push-to-talk hotkey (only the mouse button is selectable today).
- [ ] Persist pill drag position (re-centers every dictation).
- [ ] Live full-Hub re-skin on theme change (inline-styled pages re-skin only on reopen).
- [ ] WCAG contrast pass on `text_faint` tokens (~2.3–3:1, below 4.5:1).
- [ ] Hub keyboard nav + visible focus rings + `Switch` accessibleName.
- [ ] History filters (by app / date / model — all already stored).

### Low
- [ ] Empty-state illustrations + primary CTA buttons.
- [ ] Sidebar label language consistency (mixes EN/ES).
- [ ] Push Instrument Serif onto card/section titles. Page headers moved to sans
  (`role="page"`), so the serif now only appears on the wizard's welcome hero — the other
  half of the Wispr language (serif card titles) is still unclaimed.
- [ ] Consolidate serif titles onto the `QLabel[role="title"]` QSS role (currently inline).
