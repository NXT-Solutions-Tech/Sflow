# CLAUDE.md — SFlow Development Instructions

## What is SFlow?

SFlow is a macOS voice-to-text desktop tool that replaces Wispr Flow ($15/month). It captures audio via global hotkeys, transcribes on-device with local Whisper Turbo/Parakeet (Groq cloud as fallback), and auto-pastes text wherever the cursor is. It includes a floating pill UI overlay, real-time audio visualization, SQLite history, and a native light+dark Hub (the former Flask web dashboard was retired — the Hub supersedes it).

## Quick Start (Dev Mode)

```bash
# 1. Install system dependency
brew install portaudio

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Set up environment
cp .env.example .env
# Edit .env and add your GROQ_API_KEY (get one at https://console.groq.com/keys)

# 5. Run
python3 main.py
```

## Build Desktop App (.app bundle)

```bash
# Recommended: full install dance (build + ditto + kill old proc + relaunch + open Accessibility panel)
bash install.sh

# Or just build the bundle without installing
bash build.sh
```

`install.sh` exists because `build.sh` alone leaves you with a broken paste —
see "Critical: ad-hoc rebuild → silent Accessibility revocation" below.

The .app bundle is self-contained (~478MB — INCLUYE el stack MLX: mlx-whisper +
parakeet-mlx + librosa/numba/scipy + los Metal .metallib). No Python, no venv,
no terminal. Menu-bar app. On first launch the **onboarding wizard** runs
(micrófono → Accesibilidad → Input Monitoring → API key opcional); la key SOLO se
pide si el modelo activo es de nube o si Auto Cleanup está encendido — el default
(`whisper-turbo-local`) arranca sin key.

### Modelos de transcripción SELECCIONABLES (v3.0)
Catálogo en `config.py` → `STT_MODELS` (3), elegible en Hub → Ajustes → "Modelo":
1. **whisper-turbo-local** (`mlx-community/whisper-large-v3-turbo`) — DEFAULT. Mejor
   precisión es (WER 2.9%), offline, usa el diccionario personal. ~950ms warm en M4.
2. **parakeet-v3** (`mlx-community/parakeet-tdt-0.6b-v3`, motor de Handy) — el más
   rápido (~280ms), pierde en nombres propios, NO usa diccionario.
3. **groq-turbo** — nube, fallback. Router (`core/transcriber.py`) cae a Groq si el
   motor local no está disponible en runtime.
Setting: `stt_model` (migra del legacy `transcribe_backend`). El modelo local activo
se **warm-loadea en background al arrancar** (`Transcriber.warm_active()` en main.py).
Los modelos se descargan a `~/.cache/huggingface` en el primer uso (~1.6GB turbo, ~600MB parakeet).

### Build Requirements (CRÍTICO)
- **Python 3.12** (NO 3.14 — MLX no instala ahí). El venv DEBE ser 3.12: `python3.12 -m venv venv`.
- `pip install -r requirements.txt` ya incluye mlx-whisper + parakeet-mlx.
- PyInstaller (auto por build.sh) · portaudio (`brew install portaudio`)

### Gotchas del bundle MLX (aprendidos 12-jul-2026)
- **`multiprocessing.freeze_support()` OBLIGATORIO** al inicio de main.py. numba/librosa
  lanzan procesos con start-method "spawn" que re-ejecutan el binario; sin freeze_support
  cada worker cae en `main()` y ABRE OTRA PILL (la app se multiplica al dictar con modelo local).
- **NO excluir `unittest`/`test`** en sflow.spec — numba los importa en runtime; excluirlos
  rompe AMBOS motores locales (whisper cae a Groq, parakeet tira ModuleNotFoundError).
- **torch/torchaudio SÍ se excluyen** (dep transitiva de mlx-whisper que el path MLX no usa;
  ahorra ~2GB). Verificado: ningún motor importa torch en runtime.
- **`collect_all('mlx')`** trae el `mlx.metallib` (shaders Metal) — sin él MLX no corre en el bundle.
- **Race `rm: dist: Directory not empty`** en build.sh: lo causaba `open dist/` (Finder + mds).
  Ya se quitó. Si reaparece, pre-limpia con retry loop antes de buildear.
- **Selftest:** `SFlow --selftest-stt` (o `python main.py --selftest-stt`) prueba los motores
  locales dentro del binario (frozen o dev) e imprime PASS/FAIL. Úsalo para validar cada rebuild.

## macOS Permissions Required

- **Accessibility**: System Settings → Privacy & Security → Accessibility → add your Terminal/IDE
- **Microphone**: Automatically requested on first use
- **Input Monitoring**: May be required for pynput — add your Terminal/IDE

## Benchmark: local model selection (M4, Spanish voice, real samples, 12-jul-2026)

Warm median latency + WER on an M4 (mlx 0.32, real es voice):
**whisper-large-v3-turbo ~950ms (WER 2.9%, best accuracy, default)** ·
**parakeet-v3 ~280ms (WER 4.3%, fastest, bundled)** · groq ~1.4-2.7s (cloud fallback).

To re-verify a build's local engines end to end, run `SFlow --selftest-stt` (or
`python main.py --selftest-stt`) — it loads each local model and prints PASS/FAIL.

## Project Structure (v3.0 — offline real + i18n + product UX)

New in v3.0 (see CHANGELOG.md): `core/models.py` (ModelManager — bundle-first weight
resolution, no implicit downloads, `ModelNotDownloaded`), `core/i18n.py` (`tr()` +
`language` setting, es/en catalog), `core/token_budget.py` (dynamic max_tokens),
`core/sounds.py` (start/done chirps), `ui/model_download.py` (cancelable download),
`ui/toast.py` (in-app error toast). `config.APP_VERSION` is the single version source
(sflow.spec + the Hub's About line read it).

```
sflow/
├── main.py                      # Tray + controller (regular + command-mode flows)
├── config.py                    # Constants + runtime settings (settings.json)
├── sflow.spec                   # PyInstaller spec
├── build.sh                     # icns → PyInstaller → sign
├── ui/
│   ├── pill_widget.py           # NSPanel + Liquid Glass (NSVisualEffectView)
│   ├── audio_visualizer.py      # FFT + spring physics 60Hz
│   ├── theme.py                 # Design system: tokens + central QSS (light+dark)
│   ├── components.py            # page_title, Switch, primary/secondary/ghost_button
│   ├── onboarding_wizard.py     # First-run: mic + Accessibility + Input Monitoring + key
│   └── hub_window.py            # Hub: historial + diccionario + SettingsPage (todos los toggles)
├── core/
│   ├── recorder.py              # sounddevice capture
│   ├── transcriber.py           # Router (backend → commands → LLM cleanup)
│   ├── transcriber_groq.py      # Groq Whisper Large v3 Turbo
│   ├── transcriber_local.py     # parakeet-mlx (optional, offline, Apple Silicon)
│   ├── llm_cleanup.py           # Groq Llama 3.1 8B instant — filler removal + tone
│   ├── context.py               # NSWorkspace frontmost app → tone profile
│   ├── dictionary.py            # Personal vocab → Whisper prompt hint
│   ├── smart_commands.py        # "nueva línea" → \n, "coma" → ", ", etc.
│   ├── command_mode.py          # Select+speak+LLM transform flow
│   ├── hotkey.py                # 4 modes (hold, double-tap, command, mouse)
│   ├── permissions.py           # TCC probes (AX / CGPreflightListenEvent) — None = unknown
│   ├── onboarding.py            # Which steps to show; api_key_required(); mic_ok()
│   ├── error_messages.py        # Exception → code → actionable Spanish toast
│   ├── dictation_actions.py     # Trailing "press enter" → strip + press Return
│   └── paste.py                 # Focus save/restore + CGEvent paste (clipboard fallback)
├── db/database.py               # SQLite history (model column tracks backend used)
└── ~/Library/Application Support/SFlow/
    ├── .env                     # GROQ_API_KEY
    ├── settings.json            # User toggles (generated on save)
    ├── dictionary.txt           # Personal vocabulary (one term per line)
    └── transcriptions.db        # History
```

## Hotkeys (v3.0)

| Combo | Mode |
|---|---|
| Ctrl+Alt hold | Regular recording |
| Double-tap Ctrl, tap again to stop | Hands-free |
| Ctrl+Shift hold | **Command Mode** — transforms selected text via LLM (**opt-in**: `command_mode_enabled`, default off) |
| Mouse button (middle/Mouse4/Mouse5) | Regular recording (opt-in, Settings) |
| Cmd+Shift+H | Open Hub (history + dictionary + settings) |
| Cmd+Ctrl+V | Paste Last Transcript (Wispr Flow convention) |
| Trailing "press enter" / "dale enter" | Auto-press Enter after paste |

## Architecture & Data Flow (v2)

### Regular transcription
```
Hotkey Press (pynput thread)
  → [QueuedConnection] → save_frontmost_app() + recorder.start()
  → pill.set_state(RECORDING) → FFT visualizer at 60fps

Hotkey Release
  → [QueuedConnection] → recorder.stop()
  → pill.set_state(PROCESSING)
  → background Thread: Transcriber.transcribe(wav)
      → backend = GroqTranscriber OR LocalTranscriber (setting-driven)
      → vocabulary = dictionary.as_whisper_prompt()  (Whisper `prompt=` hint)
      → raw = backend.transcribe(wav, vocabulary)
      → raw = smart_commands.apply(raw)              (regex pass)
      → tone = context.tone_for_active_app()
      → final = llm_cleanup.clean(raw, tone)         (Llama 3.1 8B instant, ~150ms)
      → (final, model_id)
  → [QueuedConnection] → paste_text() + db.insert(model=model_id)
      → DONE (check verde) — or STATE_DONE_CLOUD (check ámbar, 1600ms) when
        _was_cloud_fallback(model_id): the user picked a LOCAL engine but the
        router transcribed in the cloud. The audio left the device, so the
        fallback is never silent.
      → paste raises → ERROR + toast (never a green check on a failed paste)
```

### Command Mode (opt-in — `command_mode_enabled`, default False)
`core/hotkey.py` reads the setting at press time, so toggling it takes effect
immediately — no restart. It stays off by default because it uploads the audio
**and the current selection** to the cloud.
```
Ctrl+Shift Press
  → save_frontmost_app() + copy_selection() (Cmd+C → clipboard diff)
  → recorder.start() + pill.RECORDING

Release
  → recorder.stop() + PROCESSING
  → GroqTranscriber (raw STT, no cleanup) → voice_command
  → CommandModeHandler.transform(voice, selection) → Llama transforms text
  → paste_text(result) → replaces selection
```

## Critical Implementation Details

### 1. Qt Signal Threading (MUST use QueuedConnection)
pynput emits signals from its own thread. Both QObjects live in the main thread, so Qt's `AutoConnection` incorrectly chooses `DirectConnection`. But since `emit()` comes from pynput's thread, UI modifications happen on the wrong thread — undefined behavior on macOS. **Always use explicit `Qt.ConnectionType.QueuedConnection`.**

### 2. macOS Floating Window (MUST use PyObjC)
Qt's `WindowDoesNotAcceptFocus` flag doesn't work properly on macOS. The pill must use native Cocoa APIs via PyObjC to float without stealing focus:
```python
import AppKit, objc
from ctypes import c_void_p

ns_view = objc.objc_object(c_void_p=c_void_p(widget.winId().__int__()))
ns_window = ns_view.window()
ns_window.setLevel_(AppKit.NSFloatingWindowLevel)
ns_window.setStyleMask_(ns_window.styleMask() | AppKit.NSWindowStyleMaskNonactivatingPanel)
ns_window.setHidesOnDeactivate_(False)
ns_window.setCollectionBehavior_(
    AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
    | AppKit.NSWindowCollectionBehaviorStationary
    | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
)
```
This is the same approach used by Spotlight and Wispr Flow itself.

### 3. Auto-Paste (`core/paste.py` — CGEvent by default, clipboard as fallback)
**Never pyautogui**: it is unreliable on macOS when modifier keys were recently
released (and every hotkey here ends with a modifier release).

Two backends, chosen by the `paste_backend` setting (Hub → Ajustes):

1. **`"keystroke"` (DEFAULT)** — `_type_via_cgevent()` synthesizes Unicode keyboard
   events via `CGEventKeyboardSetUnicodeString` + `CGEventPost`, in 20-char chunks
   (larger events get dropped by some apps). The clipboard is **never touched**.
2. **`"clipboard"` (FALLBACK)** — `_paste_via_clipboard()`: NSPasteboard write →
   Cmd+V via AppleScript → restore the user's clipboard 0.5s later. Also used
   automatically when CGEvent is unavailable (`_type_via_cgevent` returns False).

**Focus: the keystroke path deliberately does NOT restore it.** SFlow runs as an
accessory app and the pill is a NonactivatingPanel, so the target app is *already*
frontmost — activating it was a redundant app-switch (the flash), and if the user
switched windows during the ~950ms transcription it yanked the focus back and typed
into the old app. Only `_paste_via_clipboard()` calls `_restore_focus()`, because
its Cmd+V goes through System Events and needs the app active.

**Why keystroke is the default:**
- It doesn't clobber the user's clipboard (the fallback's restore leaves a ~0.5s
  window where another listener could read the transcript).
- **The transcript is never interpolated into AppleScript.** Only the frontmost
  *app name* ever reaches `osascript`, and it goes through `_as_literal()`.
  Dictated text — arbitrary, user-spoken, possibly `" & do shell script "…` —
  cannot reach an AppleScript literal by construction. That's an injection vector
  eliminated by design, not by escaping.

### 4. Audio Pipeline (thread-safe)
sounddevice callback runs in audio thread — NEVER touch Qt widgets from it. Use `queue.Queue` as bridge:
- Callback → puts audio chunks in queue
- QTimer on main thread → polls queue → updates visualizer

### 5. Short Recording Filter
Recordings under 0.3 seconds are accidental taps — skip transcription and return to idle.

### 6. Bundle vs Dev Mode (config.py)
`config.py` detects `sys.frozen` to switch between dev and .app bundle:
- **Dev mode**: assets and data live in the project root directory
- **Bundle mode**: read-only assets (logo) come from `sys._MEIPASS`, writable data (DB, .env) goes to `~/Library/Application Support/SFlow/`

### 7. Desktop App Features (main.py)
- **System Tray**: QSystemTrayIcon in menu bar — "Abrir Hub (⌘⇧H)", "Iniciar con macOS" toggle,
  "Reiniciar SFlow", quit. Also the delivery vehicle for error toasts (`SFlowApp.notify`).
- **Onboarding wizard** (`ui/onboarding_wizard.py`): runs from `_run_onboarding_if_needed()`.
  Steps are planned by `core/onboarding.plan_steps()` — granted permissions are skipped, and
  the API key step only appears when `api_key_required()` says so. Replaced the old
  FirstRunDialog + `_ensure_accessibility()`.
- **Launch at Login**: Creates/removes a LaunchAgent plist in `~/Library/LaunchAgents/`
- **Hide from Dock**: `NSApplicationActivationPolicyAccessory` via PyObjC (MUST be set AFTER
  the onboarding wizard — it needs focus to be usable)

### 8. Building the .app (IMPORTANT)
- Use `ditto` (not `cp -r`) to copy .app to /Applications — `cp -r` corrupts bundle metadata causing segfaults
- The .icns is auto-generated from logo.png by build.sh if missing
- Ad-hoc signing (`codesign --force --deep --sign -`) is sufficient for personal use
- Remove quarantine after install: `xattr -cr /Applications/SFlow.app`

### 9. Critical: ad-hoc rebuild → silent Accessibility revocation

**Symptom:** After `ditto` of a rebuilt bundle, dictation works (transcription
saves to DB, log shows `paste ok`) but the text never appears in the target
app. Keystrokes are being blocked by the OS silently.

**Root cause:** Each `pyinstaller` run produces a new binary hash. Ad-hoc
signatures change per-build. macOS's TCC database tracks Accessibility
permission by binary hash → it silently revokes trust when the hash changes.
CGEventPost succeeds (no error) but the OS drops the event before it reaches
other apps. The running process (if any) also keeps executing the old
in-memory code while its on-disk binary mismatches, compounding confusion.

**Fix (operational):**
1. Use `install.sh`, NOT `build.sh` + manual `ditto`. It:
   - Builds + dittos
   - Kills any running SFlow (`pgrep -f /Applications/SFlow.app`)
   - Launches fresh instance via `open -n`
   - Opens System Settings → Privacy & Security → Accessibility
2. In the Accessibility panel: remove SFlow (-), add it back (+) pointing at
   /Applications/SFlow.app. Repeat in Input Monitoring.
3. Confirm with a short dictation — text should appear in the frontmost app.

**Fix (permanent, $99/yr):** Enroll in Apple Developer Program and sign with
a Developer ID certificate. Persistent team identifier → TCC preserves trust
across rebuilds. Not worth it for personal use; accept the manual re-approve.

**Detection in code:** `main._run_onboarding_if_needed()` catches this at startup.
`core/permissions.snapshot()` probes Accessibility + Input Monitoring; when either
reads `False`, `onboarding.needs_onboarding()` reopens the wizard and
`plan_steps()` narrows it to just the revoked step — the rescue flow and the
first-run flow are the same machinery. The step polls `AXIsProcessTrusted` live
and flips to "Concedido ✓" the moment you re-add SFlow, so you don't have to
guess whether it took.

This covers the "user rebuilt and the new process can't paste" case, but NOT the
"old process still running with now-invalidated binary" case — that one requires
killing the process, which is what `install.sh` does.

(Superseded: `_ensure_accessibility()` + its QMessageBox. It only ever checked
Accessibility — never Input Monitoring — and returned `True` when its import
failed, so a broken probe looked exactly like a granted permission. The probes in
`core/permissions.py` return `None` for "unknown" and the step is shown anyway.)

## Customization

### Hotkeys
Edit `core/hotkey.py`:
- **Hold mode (push-to-talk)**: Currently Ctrl+Alt. Change the `_ctrl_held`/`_alt_held` checks
  in `_on_press`. (Ctrl+**Shift** is Command Mode — a different branch in the same method.)
- **Hands-free mode**: Currently double-tap Ctrl within 400ms. Change `DOUBLE_TAP_INTERVAL` in config.py.

### UI Dimensions
Edit `config.py`:
- `PILL_WIDTH_IDLE` (34) — width when just showing logo
- `PILL_WIDTH_RECORDING` (120) — width during recording with bars
- `PILL_WIDTH_STATUS` (52) — width for checkmark/spinner/error
- `PILL_HEIGHT` (34) — height of pill
- `PILL_MARGIN_BOTTOM` (14) — distance from bottom of screen

### Audio
Edit `config.py`:
- `SAMPLE_RATE` (16000) — 16kHz is optimal for speech
- `NUM_BARS` (8) — number of visualizer bars
- `BAR_GAIN` (6.0) — sensitivity of bars
- `BAR_DECAY` (0.80) — how quickly bars fall

## Building from Scratch

If you want to rebuild this project from scratch using Claude, copy the `PRP.md` file and give it to Claude with the instruction: "Build this project following the PRP phases. Execute all phases sequentially, validating each one before moving to the next."

The PRP contains all the architectural decisions, gotchas, and anti-patterns discovered during development. It serves as a complete blueprint.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Pill doesn't appear | Check Accessibility permissions for your terminal |
| Pill appears but steals focus | Verify PyObjC is installed: `python3 -c "import AppKit"` |
| Audio not captured | Check Microphone permissions + verify portaudio: `brew list portaudio` |
| Paste doesn't work | Grant Accessibility permission to terminal; check `save_frontmost_app` |
| Ctrl+C doesn't kill the process | This is handled by `signal.signal(signal.SIGINT, signal.SIG_DFL)` in main.py |
| Short taps trigger transcription | Adjust the 0.3s threshold in `main.py` `_on_hotkey_released` |
| .app crashes on launch (segfault) | Was copied with `cp -r` instead of `ditto`. Reinstall with `ditto` |
| .app blocked by macOS | Run `xattr -cr /Applications/SFlow.app` to remove quarantine |
| Onboarding wizard invisible | Bug if NSApplicationActivationPolicyAccessory is set before the wizard. Already fixed |
| Hotkey does nothing at all | Input Monitoring revoked — pynput goes deaf without raising. The wizard's step re-grants it |
| Transcription hangs forever | API timeout is 10s. Check your GROQ_API_KEY is valid |

## Auto-Blindaje log — full audit (2026-07-15)

> SaaS Factory principle: *error occurs → fix → DOCUMENT → never recurs.* A 4-agent
> audit (backend, security, UX-vs-Wispr, stability) ran against the whole app. Fixes
> landed on `feat/visual-refactor`; the rest is triaged below.

### Fixed (hardening committed)
- **Privacy:** stopped logging transcript **content** (`main.py` logged `text[:60]` to
  `sflow.log` — dictations can hold passwords/2FA). Log length only. `sflow.log` now
  rotates at ~1 MB (was unbounded).
- **AppleScript injection:** the frontmost-app name is interpolated into `osascript`
  (`paste.py`, `clipboard.py` — the latter since deleted as dead code). A maliciously-named
  `.app` could inject AppleScript → now escaped/stripped via `_as_literal`.
- **Secrets:** `FirstRunDialog` (since replaced by the wizard) writes the key to the **Keychain** (primary) and the
  `.env` fallback as **0600** (was world-readable 0644). Command Mode reads the key via
  `secrets.get_key` (Keychain-first), not `os.getenv` — it silently no-op'd for
  Keychain-only users.
- **Audio retention:** `prune_old_audio_paths(7d)` existed but had **zero callers** →
  now runs on launch and unlinks the WAVs.
- **SQLite leak:** `with sqlite3.connect(...) as conn` commits but never **closes** →
  wrapped all of `db/` in `contextlib.closing`.
- **Reliability:** lock on `Transcriber._backends` (warm raced first dictation → double
  model load); Groq fallback when a local engine fails **at runtime** (e.g. HF download
  drop), not just on import; `.content or ""` guards in command_mode/transform (None →
  crash → silent no-op); prune timestamp format matches SQLite's `CURRENT_TIMESTAMP`.
- **Dead hotkeys:** Command Mode (Ctrl+Shift), Cmd+Shift+H (Hub), Cmd+Ctrl+V (paste last)
  had `main.py` handlers that were **never connected** → wired in `hotkey.py` +
  `SFlowApp`, covered by `tests/test_hotkey.py`. Also fixed the README, which mislabeled
  push-to-talk as Ctrl+Shift (it is **Ctrl+Alt**).
- **Cleanup on quit:** `app.aboutToQuit` → stop the pynput listener + audio stream.
- **Tests:** 19 → **42** (router fallback, pipeline order, hotkey state machine, smart
  commands, dictionary learner, snippets, transform bounds, hallucination filter).

### Deferred UX bets (see ROADMAP "Post-audit backlog")
~~Permission-onboarding wizard~~, ~~optional API key for local-only users~~, idle
discoverability / coach mark, real-time transcription preview, ~~informative error
surfacing~~, configurable hotkey, persist pill drag position, live full Hub re-skin on
theme change, WCAG contrast on faint tokens, Hub keyboard/focus a11y, history filters.
(Struck items shipped in the Onboarding milestone below.)

## Milestone "Onboarding & Confianza" (2026-07-17, `feat/onboarding`)

> Same principle: *the app must never fail silently.* Three of the app's failure modes
> were invisible by construction. Tests 42 → **179**.

### The silent failures that got fixed
- **Input Monitoring was never requested.** It's the permission pynput needs, and without
  it the listener never fires — `core/hotkey.py` doesn't raise and `listener.running` still
  reads `True`, so the app looks healthy while being completely deaf. Now a wizard step,
  via `CGRequestListenEventAccess` (the preflight never prompts).
- **A failed paste flashed a green checkmark.** `_on_transcription_done` caught the
  exception, logged it, and set `STATE_DONE` anyway. Now ERROR + a toast saying the text
  is in the history. `_on_command_done` had no try/except at all.
- **Every error was the same red X.** The message reached the slot and was discarded.
  Now `core/error_messages.py` maps it to actionable copy on a tray toast.
- **The app refused to start without a `gsk_` key** it doesn't need — the default engine is
  on-device. `onboarding.api_key_required()` gates the key step; otherwise "Continuar sin
  conexión". It also read `os.getenv`, ignoring the Keychain where the app puts the key.

### Gotchas worth remembering
- **Probes must fail SAFE.** The old `_ensure_accessibility()` returned `True` when its
  import failed → a broken framework was indistinguishable from a granted permission.
  Everything in `core/permissions.py` returns `None` for "couldn't ask", and
  `plan_steps()` shows the step anyway. Never treat unknown as granted.
- **`CGPreflightListenEventAccess`, not `IOHIDCheckAccess`** — the latter isn't exposed on
  `Quartz.CoreGraphics`. Needs no new dependency.
- **Don't add AVFoundation for the mic check.** Opening a real stream triggers the same TCC
  prompt AND proves the device produces signal — a muted/dead/wrong mic reports
  "authorized". Saves a fragile `collect_all` on a big framework.
- **Wizard side effects belong in `on_enter` (fired from `showEvent`), never `__init__`** —
  otherwise `scripts/preview_surfaces.py` opens a mic stream and prompts for TCC just by
  rendering a PNG.
- **`AudioVisualizer` paints hardcoded white bars** (built for the dark pill) → invisible on
  the cream light theme. The wizard nests it in a dark `#vizStage` frame instead of
  restyling it.
- **Qt QSS has no `letter-spacing`** — tracking needs `QFont.setLetterSpacing` in Python
  (see `ui/components.page_title`).
- **`pyobjc-framework-ApplicationServices` was only a transitive dep** of Quartz while
  `main.py` imported it directly. Now pinned in requirements.txt.
- **Onboarding is never a gate.** If the wizard raises it's logged and the app starts —
  and it does *not* record `onboarding_seen_version`, so a one-off failure can't
  permanently skip onboarding.
