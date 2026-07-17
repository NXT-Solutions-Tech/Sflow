"""HotkeyListener state-machine tests — drive _on_press/_on_release with
stubbed pynput keys (no Qt loop, no global listener) and assert the right
signals fire. Guards the intricate double-tap purity logic and the newly-wired
Command Mode / Cmd+Shift+H / Cmd+Ctrl+V hotkeys against regressions."""
import pytest
from pynput import keyboard

import config
from core.hotkey import HotkeyListener

K = keyboard.Key


def _char(c):
    return keyboard.KeyCode.from_char(c)


@pytest.fixture
def hk():
    h = HotkeyListener()
    events = []
    for sig in ("pressed", "released", "command_pressed", "command_released",
                "hands_free_started", "hands_free_stopped", "hub_requested",
                "paste_last_requested", "transform_triggered"):
        getattr(h, sig).connect(lambda *a, s=sig: events.append(s))
    h._events = events
    return h


def test_ctrl_alt_hold_is_regular_recording(hk):
    hk._on_press(K.ctrl_l)
    hk._on_press(K.alt_l)
    assert "pressed" in hk._events
    assert "command_pressed" not in hk._events
    hk._on_release(K.alt_l)
    assert "released" in hk._events


def test_ctrl_shift_hold_is_command_mode(hk):
    config.set_setting("command_mode_enabled", True)
    hk._on_press(K.ctrl_l)
    hk._on_press(K.shift_l)
    assert hk._events == ["command_pressed"]     # not "pressed"
    hk._on_release(K.shift_l)
    assert "command_released" in hk._events
    assert "pressed" not in hk._events            # never confused with regular


def test_command_mode_off_by_default(hk):
    # It uploads audio + the current selection to the cloud → must be opt-in.
    assert config.get_setting("command_mode_enabled") is False
    hk._on_press(K.ctrl_l)
    hk._on_press(K.shift_l)
    assert hk._events == []


def test_command_mode_toggle_applies_without_restart(hk):
    """The Hub writes the setting live; the listener must honour it on the very
    next keypress — no relaunch. Guards the toggle that used to be inert."""
    config.set_setting("command_mode_enabled", True)
    hk._on_press(K.ctrl_l); hk._on_press(K.shift_l)
    assert "command_pressed" in hk._events
    hk._on_release(K.shift_l); hk._on_release(K.ctrl_l)

    hk._events.clear()
    config.set_setting("command_mode_enabled", False)
    hk._on_press(K.ctrl_l); hk._on_press(K.shift_l)
    assert hk._events == []


def test_double_tap_ctrl_starts_hands_free(hk):
    hk._on_press(K.ctrl_l); hk._on_release(K.ctrl_l)
    hk._on_press(K.ctrl_l); hk._on_release(K.ctrl_l)
    assert "hands_free_started" in hk._events


def test_ctrl_plus_letter_does_not_trigger_hands_free(hk):
    # Ctrl+C contaminates the tap → must NOT count toward double-tap
    hk._on_press(K.ctrl_l); hk._on_press(_char("c")); hk._on_release(_char("c")); hk._on_release(K.ctrl_l)
    hk._on_press(K.ctrl_l); hk._on_release(K.ctrl_l)
    assert "hands_free_started" not in hk._events


def test_cmd_shift_h_opens_hub(hk):
    hk._on_press(K.cmd_l)
    hk._on_press(K.shift_l)
    hk._on_press(_char("h"))
    assert "hub_requested" in hk._events


def test_cmd_ctrl_v_pastes_last(hk):
    hk._on_press(K.cmd_l)
    hk._on_press(K.ctrl_l)
    hk._on_press(_char("v"))
    assert "paste_last_requested" in hk._events
