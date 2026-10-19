"""Music and sound effects, generated here so every note is ours (no licensing, no downloads).

The music is a short loop per show (pads, a soft pluck arpeggio, bass, kick and hats) tiled to the
Reel's length; it sits well under the voice and ducks further whenever someone is speaking. The
effects follow the animation: a whoosh as each slide arrives, a soft pop as pieces land, a riser
and a bell as a headline number counts up, and a low hit under the very first frame.
"""
import wave

import numpy as np

SR = 44100

# show: (tempo, chords as MIDI notes, how busy). Minor keys for the market shows, a calmer major for lessons.
STYLES = {
    "hot": (104, [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]], 2),         # Am F C G
    "premarket": (98, [[52, 55, 59], [48, 52, 55], [55, 59, 62], [50, 54, 57]], 2),    # Em C G D
    "close": (94, [[54, 57, 61], [50, 54, 57], [57, 61, 64], [52, 56, 59]], 2),        # F#m D A E
    "didyouknow": (88, [[50, 53, 57], [46, 50, 53], [53, 57, 60], [48, 52, 55]], 1),   # Dm Bb F C
    "lesson": (84, [[48, 52, 55], [55, 59, 62], [57, 60, 64], [53, 57, 60]], 0),       # C G Am F
}


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def _t(n):
    return np.arange(n) / SR


def _pad_note(freq, n, rng):
    """A warm pad: a few detuned harmonics with soft roll-off, different phases left and right."""
    t = _t(n)
    out = np.zeros((n, 2))
    for h in range(1, 7):
        for cents in (-6, 6):
            f = freq * h * 2 ** (cents / 1200)
            for ch in range(2):
                out[:, ch] += np.sin(2 * np.pi * f * t + rng.uniform(0, 2 * np.pi)) / h ** 1.7
    return out


def _pluck(freq, n):
    t = _t(n)
    tone = np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(4 * np.pi * freq * t) + 0.1 * np.sin(6 * np.pi * freq * t)
    return tone * np.exp(-t / 0.16) * np.minimum(1, t / 0.004)


def _kick(n):
    t = _t(n)
    phase = 2 * np.pi * (48 * t + 70 * 0.035 * (1 - np.exp(-t / 0.035)))
    return np.sin(phase) * np.exp(-t / 0.22) * np.minimum(1, t / 0.002)


def _hat(n, rng):
    noise = np.diff(rng.standard_normal(n + 1))  # differencing tilts noise toward the highs
    return noise * np.exp(-_t(n) / 0.018)


def _add(buf, sig, at, gain=1.0, pan=0.0):
    """Mix `sig` (mono or stereo) into the looping `buf` at sample `at`, wrapping around the end."""
    if sig.ndim == 1:
        sig = np.stack([sig * (1 - max(pan, 0)), sig * (1 + min(pan, 0))], axis=1)
    at %= len(buf)
    first = min(len(sig), len(buf) - at)
    buf[at:at + first] += sig[:first] * gain
    if len(sig) > first:
        buf[:len(sig) - first] += sig[first:] * gain


def loop(show, seed=7):
    """One four-bar loop for the show, stereo float."""
    bpm, chords, busy = STYLES.get(show, STYLES["hot"])
    rng = np.random.default_rng(seed)
    beat = 60 / bpm
    bar = int(4 * beat * SR)
    full, intro = np.zeros((4 * bar, 2)), np.zeros((4 * bar, 2))
    pump = np.ones(4 * bar)
    xf = int(0.45 * SR)
    for i, chord in enumerate(chords):
        n = bar + xf
        env = np.minimum(1, _t(n) / 0.45) * np.minimum(1, (n - np.arange(n)) / xf)
        pad = sum(_pad_note(hz(m), n, rng) for m in chord) * env[:, None]
        for b in (full, intro):
            _add(b, pad, i * bar, 0.05)
        root = hz(chord[0] - 24)
        bass_t = _t(n)
        bass = (np.sin(2 * np.pi * root * bass_t) + 0.25 * np.sin(4 * np.pi * root * bass_t)) * env
        _add(full, bass, i * bar, 0.22)
        # pluck arpeggio on eighths, an octave up, with an echo on the other side
        pattern = [0, 1, 2, 1, 0, 2, 1, 2]
        for k, p in enumerate(pattern):
            if busy == 0 and k % 2:
                continue
            at = i * bar + int(k * beat / 2 * SR)
            note = _pluck(hz(chord[p] + 12), int(0.6 * SR))
            _add(full, note, at, 0.06, pan=0.35 if k % 2 else -0.35)
            _add(full, note, at + int(0.75 * beat * SR), 0.02, pan=-0.5 if k % 2 else 0.5)
        # drums: kick on 1 and 3 (plus a push before the next bar when busy), hats on the off-beats
        kicks = [0, 2] + ([3.5] if busy == 2 else [])
        for kb in kicks:
            at = i * bar + int(kb * beat * SR)
            _add(full, _kick(int(0.5 * SR)), at, 0.32)
            span = np.arange(int(0.35 * SR))
            idx = (at + span) % len(pump)
            pump[idx] = np.minimum(pump[idx], 1 - 0.45 * np.exp(-span / SR / 0.11))
        if busy:
            for h in range(8):
                at = i * bar + int((h + 0.5) * beat / 2 * SR)
                for b in (full, intro):
                    _add(b, _hat(int(0.08 * SR), rng), at, 0.035 if busy == 2 else 0.02, pan=0.2)
    full *= pump[:, None]  # the pads breathe with the kick
    return full, intro


def music(show, seconds):
    """The show's bed for the whole Reel: one sparse loop as an intro, then the full groove, faded out."""
    full, intro = loop(show)
    n = int(seconds * SR)
    reps = -(-n // len(full)) + 1
    track = np.concatenate([intro] + [full] * reps)[:n]
    fade_in, fade_out = int(0.3 * SR), int(min(2.0, seconds / 4) * SR)
    track[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
    track[-fade_out:] *= np.linspace(1, 0, fade_out)[:, None]
    return np.tanh(track * 1.4) / 1.4


# --- effects ---

def whoosh(n=int(0.42 * SR), seed=3):
    """Air moving right to left, the way Hebrew reads: filtered noise that swells and pans across."""
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(n)
    t = np.linspace(0, 1, n)
    cutoff = 300 + 5200 * np.sin(np.pi * np.minimum(t / 0.75, 1)) ** 2
    a = np.exp(-2 * np.pi * cutoff / SR)
    out, y = np.empty(n), 0.0
    for i in range(n):  # one-pole low-pass with a moving cutoff
        y = (1 - a[i]) * noise[i] + a[i] * y
        out[i] = y
    env = np.sin(np.pi * np.minimum(t / 0.7, 1) / 2) ** 2 * np.minimum(1, (1 - t) / 0.3)
    out *= env / (np.abs(out).max() + 1e-9)
    pan = 0.6 - 1.2 * t
    return np.stack([out * (1 - np.maximum(pan, 0)), out * (1 + np.minimum(pan, 0))], axis=1)


def pop(n=int(0.09 * SR)):
    t = _t(n)
    f = 950 - 380 * t / t[-1]
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.025) * np.minimum(1, t / 0.002)


def riser(seconds):
    n = int(seconds * SR)
    t = _t(n)
    f = 260 * (3.2 ** (t / seconds))
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.3 * np.sin(4 * np.pi * np.cumsum(f) / SR)
    return tone * (t / seconds) ** 2


def ding(n=int(1.4 * SR)):
    t = _t(n)
    return sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t / d)
               for f, a, d in ((1318.5, 1.0, 0.55), (1975.5, 0.5, 0.35), (2637.0, 0.25, 0.2), (659.3, 0.3, 0.8)))


def hit(n=int(1.1 * SR), seed=5):
    """A low impact under the first frame."""
    t = _t(n)
    boom = np.sin(2 * np.pi * (38 * t + 60 * 0.06 * (1 - np.exp(-t / 0.06)))) * np.exp(-t / 0.45)
    noise = np.random.default_rng(seed).standard_normal(n) * np.exp(-t / 0.05) * 0.25
    return (boom + noise) * np.minimum(1, t / 0.003)


def effects(events, seconds):
    """Mix timed events [(seconds, kind, arg)] into one stereo track."""
    buf = np.zeros((int(seconds * SR) + SR, 2))
    sounds = {"whoosh": (whoosh(), 0.16), "pop": (pop(), 0.07), "ding": (ding(), 0.09), "hit": (hit(), 0.5)}
    for at, kind, arg in events:
        i = int(max(at, 0) * SR)
        if kind == "riser":
            sig, gain = riser(arg), 0.035
            sig = sig[int(max(-at, 0) * SR):]  # already part way up when the Reel opens mid-count
        else:
            sig, gain = sounds[kind]
            if kind == "whoosh":  # the whoosh peaks on the cut, so it starts a little before
                i = max(0, i - int(0.28 * SR))
        if sig.ndim == 1:
            sig = np.stack([sig, sig], axis=1)
        end = min(len(buf), i + len(sig))
        buf[i:end] += sig[: end - i] * gain
    return buf[: int(seconds * SR)]


def write_wav(path, stereo):
    pcm = (np.clip(stereo, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
