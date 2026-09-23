"""SPU ADPCM ("PS-ADPCM", "VAG") decoding.

    python -m ps2kit.adpcm in.bin out.wav --rate 48000 [--offset N --size N]
    python -m ps2kit.adpcm in.bin out.wav --channels 2 --interleave 0x400

Each 16-byte frame holds 28 samples: byte 0 is (filter << 4) | shift, byte 1
the loop flags (1 end, 2 loop, 4 loop start), then 14 bytes of nibbles, low
nibble first. The decoder is plain Python, fast enough for per-track work.
"""
import argparse
import struct
import wave
from array import array

FILTERS = ((0, 0), (60, 0), (115, -52), (98, -55), (122, -60))


class Decoder:
    """Stateful: feed consecutive chunks of one channel."""

    def __init__(self):
        self.s1 = self.s2 = 0

    def decode(self, buf):
        out = array("h")
        s1, s2 = self.s1, self.s2
        for i in range(0, len(buf) - 15, 16):
            head = buf[i]
            shift = head & 15
            f0, f1 = FILTERS[min(head >> 4, 4)]
            if shift > 12:          # invalid on hardware; treat as 9 like Sony does
                shift = 9
            for b in buf[i + 2:i + 16]:
                for n in (b & 15, b >> 4):
                    v = ((n - 16 if n > 7 else n) << 12) >> shift
                    v += (s1 * f0 + s2 * f1) >> 6
                    v = -32768 if v < -32768 else 32767 if v > 32767 else v
                    s2, s1 = s1, v
                    out.append(v)
        self.s1, self.s2 = s1, s2
        return out


def decode(buf):
    return Decoder().decode(buf)


def deinterleave(buf, channels, interleave):
    """Split a block-interleaved stream into per-channel byte strings."""
    parts = [bytearray() for _ in range(channels)]
    step = channels * interleave
    for i in range(0, len(buf) - step + 1, step):
        for c in range(channels):
            parts[c] += buf[i + c * interleave:i + (c + 1) * interleave]
    return [bytes(p) for p in parts]


def _corr(a, b):
    n = min(len(a), len(b))
    if n < 2:
        return 0.0
    ma, mb = sum(a[:n]) / n, sum(b[:n]) / n
    sab = saa = sbb = 0.0
    for x, y in zip(a[:n], b[:n]):
        x -= ma
        y -= mb
        sab += x * y
        saa += x * x
        sbb += y * y
    return sab / (saa * sbb) ** 0.5 if saa and sbb else 0.0


def guess_layout(buf, candidates=(0x100, 0x200, 0x400, 0x800, 0x1000, 0x2000, 0x4000)):
    """Guess whether a headerless stream is interleaved stereo, and how.

    Split at each candidate interleave into L and R, decode both, and compare
    the correlation of L with R at the same time against L with the R block
    before it. True stereo pairs same-time blocks, so the first is clearly
    higher; for mono, or a wrong interleave, the two are about equal.
    Plain L/R correlation is not enough: real stereo can be weakly correlated.

    Returns (interleave or None, {interleave: score}). Feed 128-512 KB.
    """
    scores = {}
    for il in candidates:
        left, right = deinterleave(buf, 2, il)
        if len(left) < 4 * il:
            continue
        l, r = decode(left), decode(right)
        block = il // 16 * 28
        scores[il] = _corr(l, r) - _corr(l[block:], r[:-block])
    best = max(scores, key=scores.get) if scores else None
    return (best if best is not None and scores[best] > 0.15 else None), scores


def write_wav(path, chans, rate):
    """chans: list of array('h'), one per channel."""
    n = min(len(c) for c in chans)
    if len(chans) == 1:
        pcm = chans[0][:n]
    else:
        pcm = array("h", bytes(2 * n * len(chans)))
        for c, samples in enumerate(chans):
            pcm[c::len(chans)] = samples[:n]
    with wave.open(path, "wb") as w:
        w.setnchannels(len(chans))
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("wav")
    ap.add_argument("--rate", type=int, default=48000)
    ap.add_argument("--channels", type=int, default=1)
    ap.add_argument("--interleave", type=lambda x: int(x, 0), default=0x400)
    ap.add_argument("--offset", type=lambda x: int(x, 0), default=0)
    ap.add_argument("--size", type=lambda x: int(x, 0), default=-1)
    a = ap.parse_args()
    with open(a.src, "rb") as f:
        f.seek(a.offset)
        buf = f.read(a.size)
    parts = [buf] if a.channels == 1 else deinterleave(buf, a.channels, a.interleave)
    write_wav(a.wav, [decode(p) for p in parts], a.rate)


if __name__ == "__main__":
    main()
