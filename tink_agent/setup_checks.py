"""Pure-logic checks/actions behind the 'Set up TINK' onboarding window.

Every effectful call takes an injectable *_fn so the whole module is testable
with no hardware, permissions, or AppKit. The AppKit window (onboarding.py)
delegates here.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from .audio import resolve_device, DeviceNotFound

_MIC_MEDIA_TYPE = "soun"  # AVMediaTypeAudio four-char code
_MIC_STATUS = {0: "undetermined", 1: "restricted", 2: "denied", 3: "authorized"}


def mic_status(query_fn=None) -> str:
    """Microphone authorization: authorized|denied|undetermined|restricted."""
    if query_fn is None:
        import Quartz
        query_fn = lambda: Quartz.AVCaptureDevice.authorizationStatusForMediaType_(  # noqa: E731
            _MIC_MEDIA_TYPE)
    return _MIC_STATUS.get(int(query_fn()), "undetermined")


def request_mic(callback=None, request_fn=None) -> None:
    """Trigger the OS microphone-permission prompt (no-op if already decided)."""
    if request_fn is None:
        import Quartz
        request_fn = Quartz.AVCaptureDevice.requestAccessForMediaType_completionHandler_
    request_fn(_MIC_MEDIA_TYPE, callback or (lambda granted: None))


def accessibility_trusted(query_fn=None) -> bool:
    """True if this process is trusted for Accessibility (keystroke synthesis)."""
    if query_fn is None:
        import ApplicationServices
        query_fn = ApplicationServices.AXIsProcessTrusted
    return bool(query_fn())


def request_accessibility(prompt_fn=None) -> None:
    """Surface the OS Accessibility prompt directing the user to System Settings."""
    if prompt_fn is None:
        import ApplicationServices as A

        def prompt_fn():
            A.AXIsProcessTrustedWithOptions({A.kAXTrustedCheckOptionPrompt: True})
    prompt_fn()


_SAMPLE_NAMES = ("1.wav", "2.wav", "3.wav", "4.wav")

# EP-2350 variants and the USB volume each mounts. Both read the same
# config.json schema and the same root-level 1.wav..4.wav overrides.
DEVICE_DISKS = (
    ("TINGDISK", "Ting"),
    ("FX MIC DISK", "FX MIC"),
)


def tingdisk_path(volumes="/Volumes", name="TINGDISK") -> str:
    return os.path.join(volumes, name)


def find_device_disk(volumes="/Volumes", exists_fn=os.path.isdir):
    """(path, model label) of the first mounted mic volume, or (None, None)."""
    for name, label in DEVICE_DISKS:
        path = os.path.join(volumes, name)
        if exists_fn(path):
            return path, label
    return None, None


def is_tingdisk_mounted(path=None, exists_fn=os.path.isdir) -> bool:
    if path is not None:
        return bool(exists_fn(path))
    return find_device_disk(exists_fn=exists_fn)[0] is not None


def audio_present(config, resolve_fn=None) -> bool:
    resolve_fn = resolve_fn or resolve_device
    try:
        resolve_fn(config.device_name)
        return True
    except DeviceNotFound:
        return False


def device_config_sources(repo_root):
    """Repo-side files to copy onto the mic: config.json + samples/1..4.wav."""
    base = Path(repo_root) / "ting-config"
    return [base / "config.json"] + [base / "samples" / n for n in _SAMPLE_NAMES]


def _dest_for(src, repo_root, tingdisk):
    # Everything lands at the volume root: config.json refers to "1.wav".."4.wav"
    # and the firmware looks for sample overrides there, not in samples/.
    return Path(tingdisk) / Path(src).name


def copy_device_config(repo_root, tingdisk) -> None:
    """Copy config + samples onto the mic's volume root."""
    for src in device_config_sources(repo_root):
        shutil.copy2(str(src), str(_dest_for(src, repo_root, tingdisk)))


def files_match(repo_root, tingdisk) -> bool:
    """True if every source exists on TINK with a matching byte size."""
    for src in device_config_sources(repo_root):
        dst = _dest_for(src, repo_root, tingdisk)
        if not dst.exists() or dst.stat().st_size != src.stat().st_size:
            return False
    return True
