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
import json
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
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


# --- transcript cleanup ----------------------------------------------------

_FILLER = re.compile(r"(?<![\w'])(?:u+m+|u+h+m*|e+r+m+|h+m+)(?![\w'])[,.]?\s*", re.I)
_ELLIPSIS = re.compile(r"\s*(?:\.{2,}|…+)\s*")
_CJK = re.compile(r"[\u3000-\u30ff\u3400-\u9fff\uff00-\uffef]")


def _ellipsis_sub(m: re.Match) -> str:
    s, i, j = m.string, m.start(), m.end()
    before, after = s[:i].rstrip(), s[j:]
    if not before or not after:
        return ""                                  # leading / trailing
    if _CJK.match(before[-1]) or _CJK.match(after[0]):
        return ""                                  # 我想……然后 -> 我想然后
    if after[0].isupper():
        return ". "                                # trailed off, new sentence
    return " "                                     # mid-sentence pause


def clean_transcript(text: str) -> str:
    """Remove dictation artifacts: ellipses where the speaker paused to think,
    and filler words (um, uh). Pauses are not meaningful in dictated text."""
    t = _FILLER.sub("", text)
    t = _ELLIPSIS.sub(_ellipsis_sub, t)
    t = re.sub(r"\s+([,.!?;:])", r"\1", t)        # no space before punctuation
    t = re.sub(r"([,.!?;:])(?:\s*[,.;:])+", r"\1", t)  # ", ." -> ","
    t = re.sub(r"\s{2,}", " ", t).strip()
    t = t.lstrip(",.;: ").rstrip(",;: ")
    return t[:1].upper() + t[1:] if t[:1].islower() and text[:1].isupper() else t


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
BACKEND_ORDER = ["local-server", "macwhisper", "whisper-cpp", "openai-whisper", "custom"]
BACKEND_LABELS = ({"local-server": "Local server (fastest)"}
                  | {k: v[0] for k, v in PRESETS.items()}
                  | {"custom": "Custom (edit config)"})


def make_transcriber(config):
    """The transcriber for config.stt_backend."""
    if (getattr(config, "stt_backend", "") or "") == "local-server":
        return ServerTranscriber(config.stt_server_url, config.stt_server_engine,
                                 config.stt_language, config.stt_prompt)
    cmd, mode = resolve_stt(config)
    return Transcriber(cmd, mode)


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

class ServerTranscriber:
    """POSTs raw 16-bit PCM to a local dictation-server, which keeps its model
    loaded in memory: no process launch or temp file per utterance."""

    needs_warm = False  # the server keeps itself warm

    def __init__(self, url, engine="", language="", prompt="",
                 opener=urllib.request.urlopen):
        self.url = url.rstrip("/")
        self.engine = engine
        self.language = language
        self.prompt = prompt
        self._open = opener
        self.last_error: str | None = None

    def transcribe(self, samples: np.ndarray, sample_rate: int) -> str:
        self.last_error = None
        q = {"sample_rate": sample_rate}
        if self.engine:
            q["engine"] = self.engine
        if self.language:
            q["language"] = self.language
        if self.prompt:
            q["prompt"] = self.prompt
        body = np.asarray(samples, dtype=np.int16).reshape(-1).tobytes()
        req = urllib.request.Request(
            f"{self.url}/transcribe?{urllib.parse.urlencode(q)}", data=body,
            method="POST", headers={"Content-Type": "application/octet-stream"})
        try:
            with self._open(req, timeout=60) as r:
                return (json.load(r).get("text") or "").strip()
        except urllib.error.HTTPError as e:
            self.last_error = f"dictation server: {e.read().decode(errors='replace')[:200]}"
        except Exception as e:  # noqa: BLE001
            self.last_error = f"dictation server not reachable at {self.url} ({e})"
        return ""


class Transcriber:
    needs_warm = True

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
