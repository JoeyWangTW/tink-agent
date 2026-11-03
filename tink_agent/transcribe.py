"""Speech-to-text via an external CLI (open command template).

Any tool that takes an audio file and emits text works. The command is a list of
tokens with placeholders substituted per utterance:
  {file}        -> the temp WAV we write
  {output}      -> a temp .txt path (use with output_mode="file")
  {output_dir}  -> a temp dir (use with output_mode="dir"; we read the .txt it writes)

output_mode controls how the transcript is read:
  "last_line" -> last non-empty stdout line (MacWhisper prints a status line first)
  "all"       -> all non-empty stdout lines joined (tools that stream to stdout)
  "file"      -> read the {output} file
  "dir"       -> read the .txt written into {output_dir}

Built-in presets live in PRESETS; "custom" uses config.stt_command/stt_output.
"""
from __future__ import annotations
import subprocess
import tempfile
import wave
from pathlib import Path
import numpy as np


def write_wav(samples: np.ndarray, path, sample_rate: int) -> None:
    samples = np.asarray(samples, dtype=np.int16).reshape(-1)
    w = wave.open(str(path), "wb")
    try:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(samples.tobytes())
    finally:
        w.close()


# --- backend presets -------------------------------------------------------

def _macwhisper(config):
    # Speaker detection is wasted work on one dictating voice (~0.15 s a run).
    cmd = [config.mw_binary, "transcribe", "--no-speakers", "{file}"]
    if config.stt_model:
        cmd += ["--model", config.stt_model]
    # mw wraps long transcripts across several lines; keep them all.
    return cmd, "all"


def _whisper_cpp(config):
    # whisper.cpp's CLI prints clean text to stdout with -nt (no timestamps).
    return ["whisper-cli", "-f", "{file}", "-nt"], "all"


def _openai_whisper(config):
    return ["whisper", "{file}", "--model", (config.stt_model or "base"),
            "--output_format", "txt", "--output_dir", "{output_dir}"], "dir"


# name -> (label, builder(config) -> (command, output_mode))
PRESETS = {
    "macwhisper": ("MacWhisper", _macwhisper),
    "whisper-cpp": ("whisper.cpp", _whisper_cpp),
    "openai-whisper": ("openai-whisper", _openai_whisper),
}
BACKEND_ORDER = ["macwhisper", "whisper-cpp", "openai-whisper", "custom"]
BACKEND_LABELS = {k: v[0] for k, v in PRESETS.items()} | {"custom": "Custom (edit config)"}


def resolve_stt(config):
    """Return (command_list, output_mode) for the configured backend."""
    backend = (getattr(config, "stt_backend", "") or "macwhisper")
    if backend == "custom":
        cmd = list(config.stt_command) if config.stt_command \
            else [config.mw_binary, "transcribe", "{file}"]
        return cmd, (config.stt_output or "last_line")
    builder = PRESETS.get(backend, PRESETS["macwhisper"])[1]
    return builder(config)


# --- the transcriber -------------------------------------------------------

class Transcriber:
    def __init__(self, command, output_mode="last_line", runner=subprocess.run):
        self.command = list(command)
        self.output_mode = output_mode
        self._runner = runner
        self.last_error: str | None = None

    @staticmethod
    def _subst(tok, wav, outfile, outdir):
        return (tok.replace("{file}", str(wav))
                   .replace("{output_dir}", str(outdir))
                   .replace("{output}", str(outfile)))

    def transcribe(self, samples: np.ndarray, sample_rate: int) -> str:
        self.last_error = None
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            wav = d / "utt.wav"
            write_wav(samples, wav, sample_rate)
            outfile = d / "out.txt"
            cmd = [self._subst(t, wav, outfile, d) for t in self.command]
            try:
                res = self._runner(cmd, capture_output=True, text=True, timeout=120)
            except Exception as e:  # noqa: BLE001
                self.last_error = str(e)
                return ""
            if res.returncode != 0:
                self.last_error = (res.stderr or res.stdout or "stt failed").strip()
                return ""
            return self._parse(res.stdout or "", outfile, d)

    def _parse(self, stdout: str, outfile: Path, outdir: Path) -> str:
        mode = self.output_mode
        if mode == "file":
            return outfile.read_text(encoding="utf-8", errors="replace").strip() \
                if outfile.exists() else ""
        if mode == "dir":
            txts = [p for p in sorted(outdir.glob("*.txt")) if p != outfile]
            return txts[-1].read_text(encoding="utf-8", errors="replace").strip() \
                if txts else ""
        lines = [ln.strip() for ln in stdout.splitlines() if ln.strip()]
        lines = [ln for ln in lines if not ln.lower().startswith("transcribing")]
        if mode == "all":
            return " ".join(lines).strip()
        return lines[-1] if lines else ""  # last_line
