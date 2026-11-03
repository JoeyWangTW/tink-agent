import numpy as np
from tink_agent.detector import VoiceGate

SR, BLOCK = 16000, 800


def _blocks(rms_level, n):
    rng = np.random.default_rng(0)
    for _ in range(n):
        yield (rng.standard_normal(BLOCK) * rms_level).astype(np.int16)


def _gate():
    return VoiceGate(rms_start=800, rms_end=500, hangover_ms=200,
                     min_utterance_ms=100, sample_rate=SR, block_size=BLOCK)


def test_emits_one_utterance_after_silence():
    g = _gate()
    out = []
    for b in _blocks(20, 5):      # quiet (below start)
        out.append(g.process(b, False))
    for b in _blocks(3000, 10):   # loud speech ~500 ms
        out.append(g.process(b, False))
    for b in _blocks(20, 10):     # trailing silence > hangover
        out.append(g.process(b, False))
    utterances = [o for o in out if o is not None]
    assert len(utterances) == 1
    assert utterances[0].dtype == np.int16
    assert len(utterances[0]) >= BLOCK * 8


def test_tone_blocks_excluded_from_buffer():
    g = _gate()
    out = []
    for b in _blocks(3000, 4):
        out.append(g.process(b, False))          # 4 speech blocks
    for b in _blocks(3000, 4):
        out.append(g.process(b, True))           # 4 tone blocks (excluded)
    for b in _blocks(20, 10):
        out.append(g.process(b, False))
    utt = [o for o in out if o is not None][0]
    assert len(utt) == BLOCK * 4  # only the 4 non-tone speech blocks


def test_short_blip_discarded():
    g = _gate()
    out = []
    for b in _blocks(3000, 1):     # ~50 ms, below min_utterance_ms=100
        out.append(g.process(b, False))
    for b in _blocks(20, 10):
        out.append(g.process(b, False))
    assert all(o is None for o in out)


def test_long_utterance_force_closed_at_cap():
    # block_ms = 1000 * 800 / 16000 = 50 ms; cap_blocks = max(1, int(250/50)) = 5
    # Feed 12 loud blocks with no silence — should force-close at 5 blocks.
    cap_ms = 250
    g = VoiceGate(rms_start=800, rms_end=500, hangover_ms=200,
                  min_utterance_ms=100, sample_rate=SR, block_size=BLOCK,
                  max_utterance_ms=cap_ms)
    out = []
    for b in _blocks(3000, 12):    # 12 continuous loud blocks, never silent
        out.append(g.process(b, False))
    utterances = [o for o in out if o is not None]
    # Must emit at least one utterance (force-flush at cap)
    assert len(utterances) >= 1
    # The first utterance must be bounded to ~cap blocks, not all 12 blocks
    cap_blocks = max(1, int(cap_ms / (1000 * BLOCK / SR)))  # 5
    assert len(utterances[0]) <= cap_blocks * BLOCK


def _release_gate():
    return VoiceGate(rms_start=800, rms_end=500, hangover_ms=1500,
                     min_utterance_ms=100, sample_rate=SR, block_size=BLOCK,
                     release_rms=30, release_ms=150)


def test_released_handle_closes_before_hangover():
    g = _release_gate()
    for b in _blocks(3000, 10):
        assert g.process(b, False) is None
    out = [g.process(b, False) for b in _blocks(4, 3)]   # dead line, 150 ms
    assert out[-1] is not None and all(o is None for o in out[:-1])
    assert len(out[-1]) == BLOCK * 10                     # dead tail trimmed


def test_quiet_pause_while_holding_waits_for_hangover():
    g = _release_gate()
    for b in _blocks(3000, 10):
        g.process(b, False)
    out = [g.process(b, False) for b in _blocks(100, 10)]  # room noise, 500 ms
    assert all(o is None for o in out)
    assert g.active
