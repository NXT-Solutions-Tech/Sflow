# Security notes

SFlow handles microphone input and optional cloud AI providers. Treat local runtime data and API credentials as sensitive.

## Credential rules

- Never commit `.env`, API keys, tokens or exported Keychain values.
- Prefer the macOS Keychain storage implemented in `core/secrets.py`.
- Use test doubles for providers and keyring access in tests.
- Revoke a credential immediately if it appears in a commit or log.

## Data handling

- Local transcription modes can keep audio off cloud providers.
- Runtime databases, dictionaries, recordings and logs are ignored by Git.
- Review provider settings before enabling Groq or OpenRouter cleanup.

## Release checklist

Before making the repository public, scan the current tree and Git history, review third-party model and asset licenses, and test the packaged app on a clean macOS environment.
