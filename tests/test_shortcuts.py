import pytest
from tink_agent.actions import (
    ActionRouter, action_label, format_keys, normalize_keys, parse_keys,
)
from tests.test_actions import FakeKeyboard, FakeKey


class ShortcutKey(FakeKey):
    alt = "ALT"
    f12 = "F12"
    page_down = "PAGE_DOWN"


class ShortcutKeyboard(FakeKeyboard):
    Key = ShortcutKey


def test_parse_single_chord_orders_modifiers():
    assert parse_keys("cmd+shift+k") == [(("shift", "cmd"), "k")]


def test_parse_aliases_and_case():
    assert parse_keys("Command+Option+Return") == [(("alt", "cmd"), "enter")]
    assert parse_keys("control+ESC") == [(("ctrl",), "esc")]


def test_parse_sequence_of_chords():
    assert parse_keys("esc esc") == [((), "esc"), ((), "esc")]
    assert parse_keys("ctrl+a k") == [(("ctrl",), "a"), ((), "k")]


def test_parse_punctuation_and_plus_key():
    assert parse_keys("cmd+,") == [(("cmd",), ",")]
    assert parse_keys("cmd++") == [(("cmd",), "+")]
    assert parse_keys("cmd+plus") == [(("cmd",), "+")]


def test_parse_function_and_named_keys():
    assert parse_keys("f12 pagedown") == [((), "f12"), ((), "page_down")]


@pytest.mark.parametrize("bad", ["", "   ", "hyper+k", "cmd+banana", "cmd+"])
def test_parse_rejects_bad_specs(bad):
    if bad == "cmd+":  # trailing + is the plus key, so this one is valid
        assert parse_keys(bad) == [(("cmd",), "+")]
        return
    with pytest.raises(ValueError):
        parse_keys(bad)


def test_format_uses_mac_glyph_order():
    assert format_keys("cmd+shift+k") == "⇧⌘K"
    assert format_keys("ctrl+alt+shift+cmd+f12") == "⌃⌥⇧⌘F12"
    assert format_keys("esc esc") == "⎋ ⎋"


def test_normalize_round_trips():
    assert normalize_keys("Command+Shift+K") == "shift+cmd+k"
    assert normalize_keys("cmd++") == "cmd+plus"
    assert parse_keys(normalize_keys("cmd++")) == parse_keys("cmd++")


def test_action_label_for_shortcut():
    assert action_label("keys:cmd+shift+k") == "Shortcut ⇧⌘K"
    assert action_label("keys:hyper+k") == "keys:hyper+k"   # invalid → raw id


def test_fire_shortcut_presses_mods_around_key():
    kb = ShortcutKeyboard()
    r = ActionRouter({1: "keys:cmd+shift+k"}, keyboard=kb)
    assert r.fire_slot(1) == "keys:cmd+shift+k"
    assert kb.events == [
        ("press", "SHIFT"), ("press", "CMD"),
        ("press", "k"), ("release", "k"),
        ("release", "CMD"), ("release", "SHIFT"),
    ]


def test_fire_shortcut_sequence_and_named_keys():
    kb = ShortcutKeyboard()
    ActionRouter({1: "keys:alt+f12 pagedown"}, keyboard=kb).fire_slot(1)
    assert kb.events == [
        ("press", "ALT"), ("press", "F12"), ("release", "F12"), ("release", "ALT"),
        ("press", "PAGE_DOWN"), ("release", "PAGE_DOWN"),
    ]


def test_invalid_shortcut_is_captured_not_raised():
    kb = ShortcutKeyboard()
    r = ActionRouter({1: "keys:hyper+k"}, keyboard=kb)
    r.fire_slot(1)
    assert kb.events == []
    assert "hyper" in (r.last_error or "")


def test_spec_from_keycode_with_modifiers():
    from tink_agent.actions import spec_from_keycode
    cmd, shift, ctrl, alt = 1 << 20, 1 << 17, 1 << 18, 1 << 19
    assert spec_from_keycode(40, cmd | shift) == "shift+cmd+k"
    assert spec_from_keycode(53, 0) == "esc"
    assert spec_from_keycode(111, ctrl | alt) == "ctrl+alt+f12"
    assert spec_from_keycode(43, cmd) == "cmd+,"
    assert spec_from_keycode(999, cmd) is None
    # every recordable chord must parse back
    for code in (0, 18, 36, 49, 117, 126):
        parse_keys(spec_from_keycode(code, cmd | shift))
