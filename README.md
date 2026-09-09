# SFlow

> A macOS voice-to-text desktop application with local speech-to-text, optional LLM cleanup, and a privacy-conscious runtime design.

SFlow is a Python/PyQt6 macOS application that turns speech into text in any focused app. It combines global hotkeys, a floating recording UI, selectable transcription backends, optional AI cleanup, system-wide paste, and a local SQLite history.

The repository is currently private while the project is being reviewed for licensing, dependency and release readiness. The code and documentation are still useful as a technical case study: they show how I prototype AI-assisted desktop software and make model-backed behavior testable and fail-safe.

## What an AI or technical reviewer can verify

- Python desktop architecture split into `core/`, `ui/`, `db/` and `web/` modules.
- Selectable transcription engines: local Whisper/parakeet on Apple Silicon, with Groq Whisper as a cloud fallback.
- Optional LLM cleanup through Groq or OpenRouter, with a raw-text fallback when a provider is unavailable.
- macOS Keychain-first credential storage with environment-variable fallback; secret values are never logged.
- SQLite persistence for transcription history and usage insights.
- Tests covering configuration migrations, substitutions, cleanup-provider dispatch, failure behavior, database migrations, insights and secret storage.
- Build scripts and a PyInstaller specification for packaging a self-contained `.app` bundle.

## AI-assisted processing pipeline

```text
global hotkey
    -> audio recorder
    -> local Whisper/parakeet OR Groq Whisper
    -> vocabulary hints and smart commands
    -> optional LLM cleanup with tone-aware prompts
    -> paste into the previously focused app
    -> SQLite history with model and usage metadata
```

The design keeps AI as an optional processing layer instead of making the application unusable when a network provider, API key or model is unavailable.

## Project structure

```text
main.py                    # tray application and orchestration
config.py                  # runtime settings and model selection
core/                      # recording, transcription, AI cleanup and paste flows
db/                        # SQLite history and insights
ui/                        # PyQt6 hub, settings and recording pill
web/                       # local history dashboard
tests/                     # isolated unit tests; no real keys or user data
build.sh / install.sh      # macOS packaging and installation helpers
```

## Run locally

Requirements:

- macOS 15+
- Python 3.12 (the local MLX stack is not targeted at Python 3.14)
- Homebrew and `portaudio`
- A Groq API key only if cloud transcription or cleanup is selected

```bash
brew install portaudio
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Add keys only to the local .env file.
python3 main.py
```

Run the isolated tests with:

```bash
pip install -r requirements-dev.txt
pytest -q
```

Build the macOS application with:

```bash
bash build.sh
```

## Privacy and credential handling

- `.env`, runtime databases, dictionaries, audio recordings and logs are ignored by Git.
- API keys are stored in the macOS Keychain when available and are never returned by the status helpers.
- Local transcription modes can avoid sending audio to a cloud provider.
- Tests mock the keyring and providers; they do not touch the real Keychain or user history.

## Current status

The core product loop and the main AI/desktop flows are implemented. Remaining release work is packaging validation, dependency review, documentation polish and an explicit decision about public visibility. This repository should not be read as a claim that every dependency or packaged model is production-ready for every Mac.

## Attribution and scope

This repository is the current NXT-Solutions-Tech SFlow iteration. It evolved from an existing voice-dictation codebase; commit history and file-level attribution remain the source of truth for individual contributions. The repository carries an MIT license whose current copyright notice names Daniel Carreon; preserve that notice and review attribution before any public release. The project is presented here as evidence of hands-on AI application development, desktop integration and engineering judgment—not as a claim that every upstream component was written from scratch.

## Related work

- [Martin Vega portfolio](https://martinvega.dev)
- [NXT-Solutions-Tech GitHub organization](https://github.com/NXT-Solutions-Tech)
