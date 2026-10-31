from tink_agent import setup_checks


def test_mic_status_maps_raw_values():
    assert setup_checks.mic_status(query_fn=lambda: 3) == "authorized"
    assert setup_checks.mic_status(query_fn=lambda: 2) == "denied"
    assert setup_checks.mic_status(query_fn=lambda: 1) == "restricted"
    assert setup_checks.mic_status(query_fn=lambda: 0) == "undetermined"
    assert setup_checks.mic_status(query_fn=lambda: 99) == "undetermined"


def test_accessibility_trusted_reflects_query():
    assert setup_checks.accessibility_trusted(query_fn=lambda: True) is True
    assert setup_checks.accessibility_trusted(query_fn=lambda: False) is False


def test_request_mic_invokes_request_fn():
    calls = []
    setup_checks.request_mic(callback="cb",
                             request_fn=lambda mt, cb: calls.append((mt, cb)))
    assert calls == [("soun", "cb")]


def test_request_accessibility_invokes_prompt_fn():
    calls = []
    setup_checks.request_accessibility(prompt_fn=lambda: calls.append(1))
    assert calls == [1]


from pathlib import Path

from tink_agent.config import Config
from tink_agent.audio import DeviceNotFound

REPO = Path(__file__).resolve().parent.parent


def test_tingdisk_path():
    assert setup_checks.tingdisk_path("/Volumes", "TINGDISK") == "/Volumes/TINGDISK"


def test_is_tingdisk_mounted_uses_exists_fn():
    assert setup_checks.is_tingdisk_mounted(exists_fn=lambda p: True) is True
    assert setup_checks.is_tingdisk_mounted(exists_fn=lambda p: False) is False


def test_audio_present_true_when_resolved():
    assert setup_checks.audio_present(Config(), resolve_fn=lambda name: 5) is True


def test_audio_present_false_on_devicenotfound():
    def boom(name):
        raise DeviceNotFound("nope")
    assert setup_checks.audio_present(Config(), resolve_fn=boom) is False


def test_copy_then_files_match(tmp_path):
    tingdisk = tmp_path / "TINGDISK"
    tingdisk.mkdir()
    assert setup_checks.files_match(REPO, tingdisk) is False
    setup_checks.copy_device_config(REPO, tingdisk)
    assert (tingdisk / "config.json").exists()
    assert (tingdisk / "1.wav").exists()          # root, where config.json looks
    assert (tingdisk / "4.wav").exists()
    assert not (tingdisk / "samples").exists()
    assert setup_checks.files_match(REPO, tingdisk) is True


def test_files_match_false_on_size_diff(tmp_path):
    tingdisk = tmp_path / "TINGDISK"
    tingdisk.mkdir()
    setup_checks.copy_device_config(REPO, tingdisk)
    (tingdisk / "config.json").write_text("x")  # wrong size
    assert setup_checks.files_match(REPO, tingdisk) is False


def test_find_device_disk_prefers_ting_then_fx():
    present = {"/V/FX MIC DISK"}
    assert setup_checks.find_device_disk("/V", exists_fn=present.__contains__) == \
        ("/V/FX MIC DISK", "FX MIC")
    present.add("/V/TINGDISK")
    assert setup_checks.find_device_disk("/V", exists_fn=present.__contains__) == \
        ("/V/TINGDISK", "Ting")
    assert setup_checks.find_device_disk("/V", exists_fn=lambda p: False) == (None, None)


def test_bundled_config_references_root_samples():
    import json
    cfg = json.loads((Path(REPO) / "ting-config" / "config.json").read_text())
    assert sorted(s["file"] for s in cfg["samples"]) == ["1.wav", "2.wav", "3.wav", "4.wav"]
