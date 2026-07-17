# SFlow — /goal runbook (market-ready plan)

Run one `/goal` per phase, in a fresh Claude Code session, in **auto mode** + **Opus**.
Between phases: read the diff, confirm the gate, then paste the next goal.
The evaluator only sees what Claude prints — every condition below ends with a
**print-this** clause so the goal can actually be verified.

## Session setup (once)

1. Save the plan as `docs/PLAN-market-ready.md` in the repo and commit it.
2. New terminal → `cd` into the repo → `claude` (fresh session). Accept the trust dialog.
3. `/model opus`
4. Shift+Tab until the status line shows **auto** mode.
5. Confirm `/goal` is available (Claude Code v2.1.139+). `/goal` alone shows live status;
   `/goal clear` stops it.

Rules baked into every condition: work only on the named phase, commit that phase when its
gate is green, do not push, and stop after the turn cap even if unfinished.

---

## F1 — Robustness & quick wins

```
/goal Working only on F1 from docs/PLAN-market-ready.md: every listed fix is implemented,
each with a new passing test — corrupt-DB recovery (rename + recreate), WAL + busy_timeout,
dynamic max_tokens, size-scaled Groq timeout, recorder.stop() guarded + recording cap,
0600 perms on db/dictionary, hotkey.log rotation, clipboard restored on paste-last, key
absent from os.environ in subprocesses, orphan settings removed, start/done sounds actually
play. Run the full suite and PRINT the final pytest summary line showing 0 failures. Commit
F1 when green. Do not push. Stop after 45 turns.
```

## F2 — Offline real (split into four goals; do NOT run as one)

**F2a — ModelManager + honest errors**
```
/goal Working only on F2 step 1-3 from docs/PLAN-market-ready.md: core/models.py exists with
a ModelManager (catalog, is_available() using local_files_only, download(progress_cb) via
huggingface_hub, resolve_path() bundle-first). Transcribers receive a path and never download
implicitly; a missing local model raises ModelNotDownloaded mapped to a new CODE_MODEL_MISSING
message (not the false "missing key"). warm_active() only warms when is_available(). Unit
tests for ModelManager (HF mocked) and the local-first router pass — PRINT the pytest summary.
Commit when green. Do not push. Stop after 45 turns.
```

**F2b — Download UI**
```
/goal Working only on F2 step 4 from docs/PLAN-market-ready.md: ui/model_download.py adds a
cancelable QProgressBar download flow, integrated into Settings→Model and an optional wizard
step. Selecting Whisper while it is not downloaded surfaces CODE_MODEL_MISSING, never a key
error. Headless tests pass — PRINT the pytest summary. Commit when green. Do not push. Stop
after 35 turns.
```

**F2c — Local LLM cleanup + private Command Mode**
```
/goal Working only on F2 steps 5-6 from docs/PLAN-market-ready.md: mlx-lm is in requirements
and the spec; LLMCleanup gains a provider "local" (same prompts, lazy-load with lock);
Command Mode uses self.transcriber (local STT) instead of forcing groq_raw. Tests with a
mocked local model pass and fail-open is intact — PRINT the pytest summary. Commit when green.
Do not push. Stop after 35 turns.
```

**F2d — Bundle Parakeet (run supervised; touches the build)**
```
/goal Working only on F2 step 7 from docs/PLAN-market-ready.md: build.sh stages
models/parakeet-v3 and sflow.spec bundles it as a Tree. Then run
`HF_HUB_OFFLINE=1 python main.py --selftest-stt` and PRINT its full output showing PASS with
Parakeet. Commit when green. Do not push. Stop after 25 turns.
```

## F3 — i18n ES+EN

```
/goal Working only on F3 from docs/PLAN-market-ready.md: core/i18n.py exists with tr() and a
"language" setting (auto/es/en); all UI copy (hub_window, onboarding_wizard, the 12 error
codes, tray, default transforms) routes through it. A catalog-completeness test (every key
present in both es and en, no orphans, build fails if one is missing) passes, and
instantiating the Hub headless with language=en and language=es yields the correct strings.
PRINT the pytest summary. Commit when green. Do not push. Stop after 45 turns.
```

## F4 — Product UX (headless parts as a goal; visual review is yours)

The evaluator can't see the on-device smoke test. This goal covers only the
test-verifiable parts; do the visual pass yourself after it clears.
```
/goal Working only on the test-verifiable parts of F4 from docs/PLAN-market-ready.md:
rebuild_pages() replaces in-place restyling (headless test: no crash, preserves active page
and search); ui/toast.py exists and main.notify() uses it first; DONE_CLOUD uses a distinct
cloud glyph; menu bar has live status + Pause (hotkey-ignore flag, tested) + Model submenu +
paste-last; pill position persists (setting round-trip test); text_faint is >=4.5:1 in both
themes; wizard writes onboarding_seen_version only on accept() (test); mic added to
permissions.snapshot(); history filters by app/model/date. PRINT the pytest summary and the
rebuild/pause test results. Commit when green. Do not push. Stop after 50 turns.
```

## F5 — Identity, versioning, docs

```
/goal Working only on F5 from docs/PLAN-market-ready.md: config.APP_VERSION is the single
version source (spec and About read it); CHANGELOG.md exists; README is rewritten user-first
with truthful badges; dead references are gone. PRINT grep output proving no stale version
strings (1.0.0 / v2.x) and no "STT: Groq" default badge remain, and PRINT the pytest summary.
Commit when green. Do not push. Stop after 30 turns.
```

## F6 — Build & push (SUPERVISED — not a hands-off goal)

Do this one yourself, watching:
1. `pytest` green + `python -m py_compile` across the tree.
2. `bash build.sh` → `.app` (~1.1GB) → `--selftest-stt` PASS on the binary.
3. Review the per-phase commits.
4. `git push origin feat/onboarding` (the 25 pending) and `git push origin feat/market-ready`.
5. Confirm on-device: push-to-talk, wizard with a real mic (still unvalidated after
   yesterday's crash), offline dictation with Parakeet.

---

## Notes

- After each goal clears, `git diff`/review before the next phase. A cleared goal means the
  evaluator was satisfied by the transcript — not that you've seen the code.
- Auto mode has a circuit breaker (3 consecutive or 20 total blocked actions → back to
  manual). If a goal stalls there, it's telling you something needs a human.
- If a goal runs long with no output, that's expected — Opus may work many turns before it
  prints the verifiable result. Check `/goal` for turns/tokens spent.
- Anything visual or on-device (F4 look, F2d build behavior, F6 push) the evaluator cannot
  confirm. Keep those supervised.
```
