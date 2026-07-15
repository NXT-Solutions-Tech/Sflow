# SFlow — Visual/UI Refactor Prompt

> Paste this whole file into a fresh SFlow chat (or say: "read VISUAL_REFACTOR_PROMPT.md and
> execute it"). It contains the full current-state recon so the new session starts grounded.

---

You are doing a **complete visual/UI refactor** of **SFlow**, a macOS **PyQt6** voice-dictation
app (Wispr Flow alternative) at `/Users/martinvega/Developer/01-projects/Sflow`. This is a
**design-language overhaul only — no behavior/logic changes**. Every feature (local STT,
Auto Cleanup levels, dictionary/substitutions, snippets, transforms, insights, Keychain,
hotkeys, the non-focus-stealing floating pill) must keep working exactly as-is.

Work on a branch `feat/visual-refactor`, commit per phase, and **validate each surface in
BOTH light and dark** by rendering it offscreen with `widget.grab()` to a PNG and reviewing
it (the repo's venv + `QT_QPA_PLATFORM=offscreen` is the pattern already used here; stub
`PillWidget._setup_native_macos` and `QMessageBox.information/question` in headless tests).

## North-star direction (decided)

- **Aesthetic: Wispr Flow.** Light, warm, elegant, spacious. **Serif display titles** + clean
  sans for UI/body. Generous whitespace, soft cards, restrained color. Premium, calm.
- **Themes: BOTH light + dark**, following macOS system appearance, with a manual override
  in Settings (`theme`: `auto | light | dark`). Light is the primary/hero look (warm cream);
  dark is a refined complement.
- **Icons: Lucide** line icons, **bundled as SVG** and rendered via `PyQt6.QtSvg` — replace
  ALL emoji. Offline only, no CDN.
- **Retire the Flask web dashboard** — the native Hub already supersedes it.

## Hard constraints (PyQt6 + offline + macOS)

- **PyQt6 QSS is a CSS subset**: no flexbox, no `box-shadow`, no CSS transitions, limited
  selectors. Do elevation with borders/background layering; do animation with
  `QPropertyAnimation`; do switches with styled `::indicator` or a small custom `QWidget`.
- **100% offline**: bundle fonts and all Lucide SVGs as repo assets and add them to
  `sflow.spec` `datas`. **No CDN / no Google Fonts / no `cdn.tailwindcss.com`** (removing the
  web dashboard eliminates the only CDN dependency — keep it that way).
- **Preserve the crown jewel**: the pill and Hub are native non-activating NSPanels that must
  never steal focus. Don't change window flags / `_setup_native_macos`.
- Add `PyQt6.QtSvg` (and `QtSvgWidgets` if needed) to `sflow.spec` hiddenimports.

---

## CURRENT STATE (recon already done — build on these exact facts)

**One dark-only palette**, `class C:` in `ui/hub_window.py:30-42`:
`BG #0f0f0f · BG_ALT #1a1a1a · BG_HOVER #222222 · BG_CARD #181818 · BG_INPUT #202020 ·
TEXT #e8e8e8 · TEXT_DIM #8a8a8a · TEXT_FAINT #555555 · ACCENT #5a9fff · DIVIDER #2a2a2a ·
OK #50d278 · ERR #ff4646`. No light mode, no `QPalette`, no theme toggle.

**Three competing accent identities to unify into ONE**: Hub blue `#5a9fff`; web/brand
purple `#8c50dc` + orange `#ffa028` (the actual logo colors); pill/visualizer monochrome
white. Plus **three near-but-different reds** (`#ff4646`, `#FF3B30`, `rgb(255,70,70)`) and an
un-tokenized hover blue `#4a8fef` hardcoded 5× (`hub_window.py:127,529,647,958,1249`).

**Icons are all emoji-as-text or QPainter shapes — zero SVG/QtSvg in the repo.** Sidebar nav
`hub_window.py:1411-1417`: 🏠 Home · 📊 Insights · 🕐 Historial · 📖 Diccionario · ✨ Snippets ·
🪄 Transforms · ⚙️ Ajustes. Other glyphs: `⋮` card menu (:230), `🔍` search (:339), `↻` refresh
(:352), `✕` snippet delete (:706), `⌥` transform badge (:1212), `👋` Home greeting (:1282).
Pill status (checkmark/spinner/error) + RedDot are QPainter vector shapes (`pill_widget.py:306-334`,
`red_dot_indicator.py:95-101`). Only real asset: `logo_small.png`.

**Styling is 100% inline, duplicated per-widget** — no `app.setStyleSheet`, no shared QSS
constants. The primary/secondary button + input QSS blocks are copy-pasted across ~7 pages
with radius drift (3/4/5/6/8/10/12px) and padding drift. `SidebarButton` (`:160-186`) sets
the icon+label as a single string (`f"{icon}   {label}"`, 3 spaces). Checkboxes are used
where **switch toggles** would read better.

**Typography**: no font loading (`QFontDatabase.addApplicationFont` unused). System default
font sized via QSS only (11/12/13/14/15/16/22/26/28px; weights 500/600/700). Only explicit
faces: `Helvetica Neue` on sidebar buttons (`:167`), `SF Mono` on the dictionary editor (`:504`).

**Layout**: Hub `880×620`; sidebar `190px` (`#1a1a1a`, right divider); pages margins
`(28,22,28,22)`. Pill: `config.py` `PILL_*` (idle 34 / recording 112 / status 52, height 34,
radius 17, opacity 0.90), 20 white FFT bars in `ui/audio_visualizer.py`.

**Divergent / off-brand surfaces:**

- `web/server.py` — Flask dashboard: **CDN Tailwind + Google Fonts Inter**, bg `#0a0a0a`,
  purple `#8c50dc`+orange `#ffa028` wordmark, expandable table duplicating the Hub's
  `HistoryPage`. **Stale footer** "SFlow · Ctrl+Shift para grabar · Groq Whisper" (both halves
  wrong now). Wired at `main.py:179-181` (tray item) and started at `main.py:539`.
- `FirstRunDialog` (`main.py:83-119`) — **completely unstyled default-gray Qt dialog**; it's
  the **first impression** and the single most off-brand screen.
- **All `QMessageBox`** alerts (`main.py:67,110`; `hub_window.py:146,456,551,654,662,989,1031,1040`)
  — unstyled native.
- Tray menu (`main.py:159-208`) — native macOS menu (conventional; leave native or lightly touch).
- **Cohesive already** (match after re-tokenizing): `EditTranscriptDialog` (`hub_window.py:69`),
  `TranscriptionCard`/HistoryPage, and all Hub pages consume the `C` tokens.

---

## What to build

### Phase 1 — Theme foundation (do first)

- Create `ui/theme.py`: **semantic design tokens for light + dark** (replace `class C`).
  Groups: `bg / surface / surface_elevated`, `text / text_secondary / text_faint`,
  `border / divider`, **one `accent`** (+ `accent_hover`, `accent_subtle`), `success / warning /
  error` (collapse the 3 reds into one), plus warm neutrals for the Wispr **cream** light bg.
  Provide `tokens(scheme) -> dict` and a `qss(scheme) -> str` global stylesheet builder.
  **Recommended accent:** consolidate to the brand **purple `#8c50dc`** (it's the logo color),
  used sparingly; keep orange `#ffa028` only as a rare highlight. Confirm final hues by eye in
  both themes.
- **Central global stylesheet**: `app.setStyleSheet(theme.qss(scheme))` in `main.py`, keyed by
  `objectName`/widget class, so pages stop inlining/duplicating QSS. Migrate the ~7 duplicated
  button/input blocks to classes (e.g. `QPushButton#primary`, `QPushButton#secondary`,
  `QLineEdit`, `QComboBox`, `Card`, etc.). Standardize radius to a small scale (e.g. 8 / 12 /
  full) and one spacing scale.
- **Theme switching**: detect system light/dark (`QApplication.styleHints().colorScheme()` on
  Qt 6.5+, and react to its `colorSchemeChanged`), honor the `theme` setting
  (`auto/light/dark`), and re-apply `theme.qss(...)` live. Add the toggle to Settings → System.
- **Fonts (bundled, offline)**: add an `assets/fonts/` dir and load via `addApplicationFont`.
  Wispr look = **serif display** (recommend **Fraunces** or **Instrument Serif** — warm,
  elegant) for page/section titles + a **UI sans** (recommend **Inter**) for body/controls.
  Define a type scale (display/title/heading/body/caption) and apply via the central QSS.
  Add the font files to `sflow.spec` `datas`.

### Phase 2 — Icon system (Lucide)

- Add `PyQt6.QtSvg`. Vendor the needed **Lucide** SVGs into `assets/icons/` (offline).
- Helper `ui/icons.py`: `icon(name, color=None, size=18) -> QIcon` that loads the SVG, recolors
  stroke to the current token (`currentColor` swap or `QPainter` tint), and caches. Provide a
  `lucide` name map. Replace **every** emoji: nav (home, bar-chart-3, history/clock, book-open,
  sparkles, wand-2, settings), `⋮`→more-vertical, `🔍`→search, `↻`→refresh-cw, `✕`→x,
  `⌥`→keyboard/command badge, `👋`→(drop or sun/hand). Rework `SidebarButton` to a real
  **icon + label** layout (QIcon on the button, not text glyph).
- Pill status (check/spinner/error) + RedDot: keep crisp QPainter but **recolor to the single
  success/error tokens**. Optionally swap check/x for Lucide.

### Phase 3 — Component library (token-driven, both themes)

Buttons (primary/secondary/ghost/icon), Input, Textarea, **Select/Combo** (custom caret),
**Switch toggle** (replace the checkbox look), Card, Tab (keep the underline style, re-tokened),
ListRow, StatCard, Badge, Menu, Dialog shell, ScrollBar, Tooltip. All from the central QSS.

### Phase 4 — Migrate every surface

- **Hub** (all pages: Home, Insights, Historial, Diccionario, Snippets, Transforms, Settings):
  serif titles, Lucide sidebar, switch toggles, unified cards, cream light bg / refined dark.
- **FirstRunDialog** (`main.py:83`): fully theme it — this is the first impression; make it a
  showcase of the new system.
- **All `QMessageBox`**: theme via the global QSS (or wrap in a small themed dialog helper).
- **Floating pill + visualizer**: it floats over arbitrary apps, so keep it a **refined dark/
  glass in BOTH themes** (don't make it cream); give the bars a subtle single-accent tint or
  keep tasteful monochrome — decide by eye. Align its black + status colors to tokens.
- **RedDot**: single error token.
- **Tray menu/icon**: keep native; ensure the icon renders crisply.

### Phase 5 — Retire the web dashboard

- Remove the tray "Dashboard web" item and the `start_web_server()` call (`main.py:179-181, 539`),
  and delete/unwire `web/server.py` + its spec entry. Remove the now-dead port logic. (The Hub's
  Historial fully covers it.) Grep for and fix the **stale copy** ("Groq Whisper", "Ctrl+Shift")
  anywhere it survives.

### Phase 6 — Validation

- For each surface, render **light + dark** previews via `widget.grab()` → PNG and review for
  consistency (one accent, one red, serif titles, Lucide icons, aligned radii/spacing).
- Confirm no CDN/network dependency remains; `bash build.sh` still bundles fonts + icons + QtSvg.
- On-device: run `python3 main.py`, toggle system light/dark, verify every screen + the pill,
  and that all features still work (visual-only refactor).

## Deliverable

A cohesive, token-driven **light+dark** design system (one accent, one red, serif+sans type,
Lucide icons, central QSS), applied to every surface, with the web dashboard retired — SFlow
looking like a premium Wispr-Flow-class product in both themes, fully offline, no behavior
changes.
