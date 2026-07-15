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

### Session handoff
- **Done:** M1 code complete on `feat/pill-reactive`; validated everything that's checkable
  headless (state machine, real-audio bars, full import graph, dashboard). Also on this
  branch's history: OpenRouter/GLM cleanup provider, glm-4.7-flash default, ffmpeg fix, new
  app icon, mic-device selector, multilingual auto-detect.
- **Next:** user runs the real-display acceptance test for Gate 1.3. If the Qt opacity fade
  doesn't render on their Qt build, switch to native `NSWindow.alphaValue` (fallback noted
  above). Then start **M2 — Auto Cleanup levels None/Light/Medium** (reuses
  `core/llm_cleanup.py` `_build_system_prompt`).
- **Open decision:** none blocking.
