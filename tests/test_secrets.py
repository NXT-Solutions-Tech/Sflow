"""Keychain-or-env secrets (keyring mocked — never touches the real macOS Keychain)."""
import core.secrets as S


class FakeKeyring:
    def __init__(self):
        self.store = {}

    def get_password(self, service, name):
        return self.store.get((service, name))

    def set_password(self, service, name, value):
        self.store[(service, name)] = value

    def delete_password(self, service, name):
        self.store.pop((service, name), None)


def test_keychain_roundtrip(monkeypatch):
    monkeypatch.setattr(S, "keyring", FakeKeyring())
    assert S.set_key("K", "v1") is True
    assert S.get_key("K") == "v1"
    assert S.key_source("K") == "keychain"
    S.set_key("K", "")            # empty clears
    assert S.get_key("K") == ""
    assert S.key_source("K") == "none"


def test_env_fallback_when_no_keychain(monkeypatch):
    monkeypatch.setattr(S, "keyring", None)
    monkeypatch.setenv("MYKEY", "fromenv")
    assert S.get_key("MYKEY") == "fromenv"
    assert S.key_source("MYKEY") == "env"
    monkeypatch.delenv("MYKEY", raising=False)
    assert S.get_key("MYKEY") == ""
    assert S.key_source("MYKEY") == "none"
