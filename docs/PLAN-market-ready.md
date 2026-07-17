# SFlow → lista para mercado: plan por fases

## Context

Segunda gran iteración sobre SFlow. La primera cerró los "controles que mentían" (Command Mode
inerte, Focus Mode placebo, fallback nube silencioso, WAVs huérfanos, gate de la key) y dejó
221 tests verdes en `feat/onboarding`. Ahora el objetivo es **producto comercial sin errores**:
backend, UX/UI, base de datos, onboarding, lenguaje de diseño, menu bar, mejoras de LLM y —
la pieza central — **que la app corra 100% offline out-of-the-box**.

Tres auditorías frescas (backend/empaquetado, UX/UI/diseño, backlogs/LLM/market) produjeron el
inventario verificado con archivo:línea que alimenta este plan.

**Decisiones ya tomadas por Martin:**
1. **Bundlear Parakeet** (~600MB, app ~1.1GB) como motor offline garantizado; Whisper Turbo
   como **descarga in-app** con progreso.
2. **Cleanup LLM local** con `mlx-lm` + modelo pequeño 4-bit (Qwen2.5-1.5B-Instruct-4bit),
   como **descarga opcional** — no bundleado.
3. **Sin firma Developer ID** esta iteración (sigue ad-hoc + xattr). Notarización y
   auto-update (Sparkle) quedan diferidos explícitamente.
4. **i18n ES+EN** siguiendo el idioma del sistema, con override en Ajustes.

Al terminar: commit por fase, **push a origin** (fork `NXT-Solutions-Tech/Sflow`) y aviso.
Rama de trabajo: **`feat/market-ready`** desde `feat/onboarding` (y push también de
`feat/onboarding`, que lleva 25 commits sin subir).

---

## Diagnóstico en una línea

El motor es sólido (privacidad, fail-open, 221 tests); lo que falta para mercado es que la
**promesa offline sea verdadera** (hoy el primer dictado descarga 1.6GB de HF sin UI), que el
**feedback sea garantizado** (hoy: X roja 1.2s + notificación que macOS puede tragar), y
**consistencia** (tema a medias al cambiarlo en vivo, ES/EN mezclados, menu bar mínimo).

---

## F1 — Robustez y quick wins (paralelizable, todo S)

Correcciones pequeñas verificadas por las auditorías. Archivos disjuntos → workflow paralelo.

| Fix | Archivos |
|---|---|
| DB corrupta → renombrar `.corrupt-<ts>` + recrear + toast (hoy: crash al arranque, [database.py:29](db/database.py#L29) sin try, excepthook no cubre `__init__`) | `db/database.py`, `main.py`, `core/error_messages.py` |
| `PRAGMA journal_mode=WAL` + `busy_timeout` (hoy: "database is locked" posible con retry concurrente) | `db/database.py`, `db/snippets.py` |
| `max_tokens` dinámico según longitud (hoy 1500 fijo **trunca dictados de 5+ min en silencio**) | `core/llm_cleanup.py:147`, `core/transform.py:58`, `core/command_mode.py:140` |
| Timeout Groq STT escalado por tamaño del WAV (hoy 10s fijo pierde dictados largos en red lenta) | `core/transcriber_groq.py:46` |
| `recorder.stop()` con try; `status` de error → log + reabrir en el próximo start; **cap de grabación** (auto-stop hands-free a N min con toast) | `core/recorder.py`, `main.py`, `config.py` |
| Perms 0600 al crear DB/dictionary; rotación de `hotkey.log` (reusar patrón de `core/logger.py`); `paste_last_transcript` restaura clipboard (reusar `_paste_via_clipboard`) | `db/database.py`, `core/dictionary.py`, `core/hotkey.py:23`, `core/paste.py:231` |
| Key fuera de `os.environ`: `.env` se parsea a dict interno de `core/secrets`, sin `load_dotenv` global ni `os.environ[...]=` (hoy todo subproceso hereda la key, incluidos los workers spawn de numba) | `config.py:27`, `core/secrets.py`, `core/onboarding.py:135` |
| Settings: quitar huérfanos `llm_model` / `history_hotkey_enabled` y legacy de defaults; **implementar** los sonidos `sound_on_start/done` (afplay en thread, sonidos de sistema) — hoy el toggle existe y no suena nada | `config.py`, `main.py` |

**Gate F1:** suite completa verde + test nuevo por cada fix (DB corrupta se recupera, WAL activo,
max_tokens escala, cap de grabación, clipboard restaurado, key ausente de `os.environ` en
subprocesos).

## F2 — Offline real: gestor de modelos, Parakeet bundleado, LLM local

La fase de mayor valor. Hoy `sflow.spec` bundlea el *código* MLX pero **ningún peso**;
`from_pretrained(repo_id)` descarga 1.6-2.4GB síncronamente dentro del worker con la pill en
PROCESSING — la app "parece colgada". Y si no hay red: mensajes de error falsos
([error_messages.py:52-67](core/error_messages.py#L52-L67) culpa a la key o sugiere "cambia a
local" cuando ya estás en local).

1. **`core/models.py` (nuevo) — ModelManager**: catálogo {parakeet-v3, whisper-turbo,
   qwen2.5-1.5b-cleanup} con repo_id/tamaño/tipo; `is_available()` (bundle → caché HF con
   `local_files_only` → no); `download(progress_cb)` con `huggingface_hub.snapshot_download`
   (ya es dep transitiva); `resolve_path()` bundle-first (`sys._MEIPASS/models/...`).
2. **Transcribers nunca descargan implícitamente**: `transcriber_local.py:79` /
   `transcriber_parakeet.py:39` reciben path del ModelManager; si falta →
   `ModelNotDownloaded` → nuevo `CODE_MODEL_MISSING` con mensaje veraz ("descárgalo en
   Ajustes → Modelo"). `warm_active()` ([main.py:231](main.py#L231)) solo calienta si
   `is_available()` — hoy dispara la descarga en silencio.
3. **Router local-first**: motor elegido no disponible → fallback a **Parakeet bundleado**
   (sigue local, sin pill ámbar); Groq solo al final y solo con key. `DONE_CLOUD` queda para
   el caso real de nube.
4. **UI de descarga** (`ui/model_download.py`, nuevo): QProgressBar cancelable en thread;
   integrada en (a) Ajustes → Modelo (botón "Descargar" por modelo ausente) y (b) un step
   opcional del wizard tras la key ("Parakeet ✓ incluido · Whisper Turbo, mejor precisión —
   Descargar 1.6GB / Después"). Reusar el patrón de steps de `ui/onboarding_wizard.py`.
5. **Cleanup LLM local**: `mlx-lm` a requirements + spec (`collect_all`); provider `"local"`
   en `LLMCleanup` (mismos prompts `_BASE_RULES`/`_MEDIUM_RULES`, lazy-load con lock — patrón
   `Transcriber._backends`); combo de proveedor en Ajustes gana "Local (offline)". Fail-open
   intacto.
6. **Command Mode privado**: [main.py:541](main.py#L541) deja de forzar `groq_raw` → usa
   `self.transcriber` (STT local ~950ms). La transformación usa el provider LLM configurado
   (local si está descargado). Actualizar el copy del switch (ya no sube el audio; sigue
   opt-in).
7. **Bundle**: `build.sh` prepara `models/parakeet-v3` (descarga/verifica snapshot antes de
   PyInstaller); `sflow.spec` lo añade como `Tree(...)`. App esperada ~1.1GB.

**Gate F2:** tests de ModelManager (HF mockeado) + router local-first + provider local
(modelo mockeado); `HF_HUB_OFFLINE=1 python main.py --selftest-stt` pasa con Parakeet;
elegir Whisper sin descargar → `CODE_MODEL_MISSING` (no "falta la key").

**Riesgos:** peso del `Tree` de 600MB en PyInstaller (staging dir en build.sh, build más
lento); `mlx-lm` en el spec (collect_all de `mlx_lm` + tokenizers); verificar que Qwen 4-bit
sigue el prompt conservador (si no, probar Llama-3.2-1B/3B-Instruct-4bit y fijar el elegido).

## F3 — i18n ES+EN

Hoy la UI mezcla idiomas por todas partes (sidebar "Home/Insights/Snippets/Transforms" vs
"Historial/Diccionario/Ajustes", tab "System", combos, tooltip del tray en EN, wizard y
errores en ES).

1. **`core/i18n.py` (nuevo)**: catálogo `{key: {"es": ..., "en": ...}}`, `tr(key, **fmt)`,
   idioma = setting `"language"` (`auto`/`es`/`en`; auto = `QLocale.system()`).
2. **Barrido de copy**: `ui/hub_window.py` (el grueso), `ui/onboarding_wizard.py`,
   `core/error_messages.py` (los 12 códigos → keys), tray en `main.py`, transforms default en
   `config.py`. La pill no tiene texto.
3. Selector de idioma en Ajustes. Aplicación en caliente llega con el rebuild de F4; hasta
   entonces, "se aplica al reabrir el Hub".

**Gate F3:** test de completitud del catálogo (toda key existe en ambos idiomas, sin huérfanas
— falla el build si falta una); instanciación headless con `language=en` y `=es` produce los
strings correctos.

## F4 — UX de producto: re-theme vivo, toast propio, menu bar, pill, a11y

1. **Re-theme en vivo por rebuild**: hoy `_apply_theme_live()`
   ([hub_window.py:887](ui/hub_window.py#L887)) deja el Hub mitad claro/mitad oscuro porque
   todas las páginas congelan `C.*` en el constructor. Solución: `rebuild_pages()` (destruir
   con `deleteLater` + reconstruir, preservando página activa y búsqueda) — sirve también
   para el cambio de idioma en caliente. Convierte un L en un M.
2. **Toast in-app** (`ui/toast.py`, nuevo): panel non-activating (reusar
   `_setup_native_macos` de la pill), auto-dismiss, cola; `main.notify()` lo usa primero y
   `tray.showMessage` queda de refuerzo. Cierra el hallazgo "el único feedback garantizado es
   una X de 1.2s".
3. **DONE_CLOUD visible de verdad**: glyph de nube (Lucide ya está en `ui/icons.py`) en vez
   del mismo check con otro color, + toast informativo la primera vez por sesión. Es un
   evento de privacidad; hoy son 4px de diferencia de matiz.
4. **Menu bar de producto** ([main.py:164](main.py#L164)): status vivo conectado a los
   estados de la pill ("Grabando…/Procesando…/Activo/Pausado"), acción **Pausar SFlow**
   (flag en `HotkeyListener` que ignora hotkeys), submenú **Modelo** (radio con
   disponible/descargado), **Pegar último dictado** (reusa `_on_paste_last`), icono con
   punto rojo mientras graba, cheat-sheet de atajos.
5. **Pill**: persistir posición de drag (setting `pill_pos`, guardar en release, restaurar
   en `_position_on_screen`).
6. **WCAG**: subir `text_faint` a ≥4.5:1 en [theme.py:57,77](ui/theme.py#L57) (dark y light).
7. **Wizard**: `onboarding_seen_version` **solo en `accept()`** (hoy [main.py:120](main.py#L120)
   lo escribe aunque cierres a la mitad → sin rescate); mic al `permissions.snapshot()` vía
   `AVCaptureDevice.authorizationStatusForMediaType_` (añadir `pyobjc-framework-AVFoundation`);
   pantalla final de resumen + hotkeys.
8. **A11y mínimo viable**: `accessibleName` en botones de solo-icono, `:focus` rings en el
   QSS global, `tabOrder` en Ajustes.
9. **Historial**: filtros por app/modelo (SELECT DISTINCT) + rango de fecha (hoy/7d/30d/todo).
10. **Marca**: estados vacíos con icono + CTA; Instrument Serif en títulos de sección
    (rol QSS `title` ya existe y casi no se usa).

**Gate F4:** suite + tests headless de rebuild (no crashea, preserva estado) y de la pausa de
hotkeys; `scripts/preview_surfaces.py` regenerado para revisión visual; smoke on-device tuyo.

## F5 — Identidad, versionado, docs

- `config.APP_VERSION = "3.0.0"` como única fuente (spec y About la leen); hoy el spec dice
  1.0.0 y los docs v2.6. `CHANGELOG.md` nuevo.
- README reescrito usuario-first (badges veraces — hoy dice "STT: Groq" y el default es
  local), sección dev separada. LICENSE: conservar el copyright MIT de upstream (obligatorio)
  + línea propia. `HTTP-Referer` ([llm_cleanup.py:164](core/llm_cleanup.py#L164)) → fork.
- CLAUDE.md: quitar la tabla de benchmark marcada SUPERSEDED, documentar `core/models.py`,
  `core/i18n.py`, `ui/toast.py`; corregir el docstring mentiroso de HubWindow
  ("non-activating"); PRP.md viejo: nota de que Flask fue retirado.
- ROADMAP: registrar esta iteración; backlog explícito de diferidos.
- `verify.sh`: pytest + `--selftest-stt` en un solo comando.

**Gate F5:** grep sin referencias muertas ni versiones viejas; catálogo i18n completo.

## F6 — Cierre: build, commits, push

1. Suite completa + `py_compile` de todo.
2. `bash build.sh` → .app con Parakeet dentro (~1.1GB) + `--selftest-stt` sobre el binario.
3. Commits temáticos por fase (hechos al cerrar cada fase, no al final).
4. `git push origin feat/onboarding` (los 25 commits pendientes) + `git push origin
   feat/market-ready`.
5. Aviso final: resumen, tamaño del bundle, y qué probar on-device (el push-to-talk, el
   wizard con mic real — recordar que quedó pendiente de validar tras el crash de ayer).

## Diferido explícito (registrado en ROADMAP, no en esta iteración)

Firma Developer ID + notarización + DMG + Sparkle (decisión tuya: sin firma por ahora — nota:
sin esto **no se puede distribuir** a otros Macs; cada build sigue rompiendo Accessibility en
tu máquina) · streaming STT / preview en vivo (la mayor palanca "premium", L) ·
`raw_text`/`enhanced_text` + undo-AI · FTS5 para búsqueda · telemetría opt-in · hotkey
push-to-talk configurable · per-app enhance prompts.

## Verificación end-to-end (al cierre)

- `HF_HUB_OFFLINE=1` + Wi-Fi off: dictar con Parakeet → texto pegado. Elegir Whisper sin
  descargar → toast claro de "modelo no descargado", nunca "falta la key".
- Descargar Whisper desde Ajustes → barra de progreso → dictar con Whisper.
- Activar cleanup local (Qwen descargado) → dictado con muletillas sale limpio sin red.
- Cambiar tema claro↔oscuro con el Hub abierto → re-skin completo, sin mitades.
- Cambiar idioma a EN → Hub y wizard en inglés al reabrir.
- Menu bar: Pausar → Ctrl+Alt no graba; Reanudar → sí. Icono con punto rojo al grabar.
- Cerrar el wizard a la mitad → reaparece al siguiente arranque.
- `pytest` verde, `sflow.log` sin crecer, build `--selftest-stt` PASS.
