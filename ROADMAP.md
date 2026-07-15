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

## Post-audit backlog (2026-07-15)

A 4-agent audit (backend, security, UX-vs-Wispr, stability) ran on the whole app. The
security/reliability findings were **fixed** on `feat/visual-refactor` (see CLAUDE.md
"Auto-Blindaje log"). The remaining items are product/UX bets, prioritized:

### Blocking / decision
- [ ] **Purge the 33 voice recordings from git history** (`audio/*.wav` are reachable on
  `origin` — the earlier commit only untracked them). Needs a `git filter-repo` +
  force-push and a public/private check. **Awaiting user approval** (destructive).

### High-value UX (Wispr-parity)
- [ ] **Permission onboarding wizard** — guided mic + Accessibility + Input Monitoring
  with live "granted ✓" polling (today only the API key is asked; Input Monitoring is
  never surfaced, so hotkeys can silently fail).
- [ ] **Optional API key for local-only users** — the default model is offline yet the app
  refuses to start without a `gsk_` key. Offer "Continue offline".
- [ ] **Real-time / pre-paste transcription preview** — biggest "premium feel" lever;
  today only a spinner shows during processing.
- [ ] **Informative error surfacing** — every failure collapses to a 1.2s red X; route the
  error message to a pill tooltip / notification.
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
- [ ] Consolidate serif titles onto the `QLabel[role="title"]` QSS role (currently inline).
