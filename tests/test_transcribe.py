import subprocess
import numpy as np
from pathlib import Path
from tink_agent.transcribe import Transcriber, write_wav, resolve_stt, BACKEND_ORDER
from tink_agent.config import Config


class FakeRun:
    """Records the command; optionally writes a file the tool would produce."""
    def __init__(self, stdout="", returncode=0, writes=None):
        self.stdout, self.returncode, self.writes = stdout, returncode, writes
        self.calls = []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        if self.writes:
            name, content = self.writes
            wav = next(a for a in cmd if a.endswith("utt.wav"))
            (Path(wav).parent / name).write_text(content, encoding="utf-8")
        return subprocess.CompletedProcess(cmd, self.returncode, self.stdout, "")


def _samples():
    return (np.random.default_rng(0).standard_normal(8000) * 1000).astype(np.int16)


def test_last_line_strips_status_line():
    fake = FakeRun(stdout="Transcribing x.wav...\nhello world\n")
    t = Transcriber(["/bin/mw", "transcribe", "{file}"], "last_line", runner=fake)
    assert t.transcribe(_samples(), 16000) == "hello world"
    assert "transcribe" in fake.calls[0]
    assert any(a.endswith("utt.wav") for a in fake.calls[0])  # {file} substituted


def test_all_joins_stdout_lines():
    fake = FakeRun(stdout="first line\nsecond line\n")
    t = Transcriber(["whisper-cli", "-f", "{file}", "-nt"], "all", runner=fake)
    assert t.transcribe(_samples(), 16000) == "first line second line"


def test_file_mode_reads_output_file():
    fake = FakeRun(writes=("out.txt", "from a file\n"))
    t = Transcriber(["tool", "{file}", "-o", "{output}"], "file", runner=fake)
    assert t.transcribe(_samples(), 16000) == "from a file"


def test_dir_mode_reads_written_txt():
    fake = FakeRun(writes=("utt.txt", "dir mode text\n"))
    t = Transcriber(["whisper", "{file}", "--output_dir", "{output_dir}"], "dir",
                    runner=fake)
    assert t.transcribe(_samples(), 16000) == "dir mode text"


def test_failure_sets_error():
    fake = FakeRun(stdout="", returncode=1)
    t = Transcriber(["x", "{file}"], "last_line", runner=fake)
    assert t.transcribe(_samples(), 16000) == ""
    assert t.last_error is not None


def test_write_wav_roundtrip(tmp_path):
    import wave
    p = tmp_path / "o.wav"
    write_wav(_samples(), p, 16000)
    w = wave.open(str(p), "rb")
    assert w.getframerate() == 16000 and w.getnchannels() == 1 and w.getsampwidth() == 2


# --- backend resolution ---

def test_resolve_macwhisper_default():
    cmd, mode = resolve_stt(Config())
    assert cmd[:2] == ["/Applications/MacWhisper.app/Contents/MacOS/mw", "transcribe"]
    assert "{file}" in cmd and mode == "all"


def test_resolve_macwhisper_includes_model():
    cmd, _ = resolve_stt(Config(stt_model="whisperkit:base"))
    assert "--model" in cmd and "whisperkit:base" in cmd


def test_resolve_whisper_cpp_and_openai():
    cmd, mode = resolve_stt(Config(stt_backend="whisper-cpp"))
    assert cmd[0] == "whisper-cli" and mode == "all"
    cmd, mode = resolve_stt(Config(stt_backend="openai-whisper"))
    assert cmd[0] == "whisper" and mode == "dir"


def test_resolve_custom_uses_config_command():
    cmd, mode = resolve_stt(Config(stt_backend="custom",
                                   stt_command=["mytool", "{file}", "-x"],
                                   stt_output="all"))
    assert cmd == ["mytool", "{file}", "-x"] and mode == "all"


def test_custom_in_backend_order():
    assert BACKEND_ORDER[-1] == "custom"


def test_server_transcriber_posts_pcm_and_reads_text():
    import io, json
    import numpy as np
    from tink_agent.transcribe import ServerTranscriber
    seen = {}

    def opener(req, timeout):
        seen["url"], seen["body"] = req.full_url, req.data
        return io.BytesIO(json.dumps({"text": " hello there "}).encode())

    t = ServerTranscriber("http://127.0.0.1:8766/", "whisper", "zh", opener=opener)
    out = t.transcribe(np.array([1, -2, 3], dtype=np.int16), 16000)
    assert out == "hello there" and t.last_error is None
    assert seen["url"].startswith("http://127.0.0.1:8766/transcribe?")
    assert "engine=whisper" in seen["url"] and "language=zh" in seen["url"]
    assert seen["body"] == np.array([1, -2, 3], dtype=np.int16).tobytes()


def test_server_transcriber_reports_unreachable():
    import numpy as np
    from tink_agent.transcribe import ServerTranscriber

    def opener(req, timeout):
        raise OSError("connection refused")

    t = ServerTranscriber("http://127.0.0.1:1", opener=opener)
    assert t.transcribe(np.zeros(10, dtype=np.int16), 16000) == ""
    assert "not reachable" in t.last_error


def test_clean_transcript_removes_pause_ellipses_and_fillers():
    from tink_agent.transcribe import clean_transcript as c
    assert c("So I want to... refactor the panel...") == "So I want to refactor the panel"
    assert c("Okay… So then we run it.") == "Okay. So then we run it."
    assert c("Um, so I think, uh, we should... maybe ship it.") == "So I think, we should maybe ship it."
    assert c("...and then the tests") == "and then the tests"
    assert c("我想……然后运行测试。") == "我想然后运行测试。"
    assert c("Run the tests.") == "Run the tests."
    assert c("The umbrella is humid, uhh, hmm.") == "The umbrella is humid"
