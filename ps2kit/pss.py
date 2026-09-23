"""Sony PSS movies: split into an MPEG-2 video stream and a WAV.

    python -m ps2kit.pss MOVIE.PSS --video out.m2v --audio out.wav
    python -m ps2kit.pss MOVIE.PSS --info

A PSS is an MPEG-2 program stream. Video is the ordinary 0xE0 stream, which
ffmpeg reads directly. Audio lives in private_stream_1 (0xBD): each packet's
payload starts with a 4-byte substream header, observed as `FF A0 00 00`
(the second byte is the substream id, 0xA0 for the first audio track), then
the track itself begins with an `SShd` header and an `SSbd` body:

    SShd  u32 size (0x18)  u32 type  u32 rate  u32 channels  u32 interleave
          u32 loop_start  u32 loop_end
    SSbd  u32 size, then data, `interleave` bytes per channel in turn

type 0x01 is signed 16-bit little-endian PCM, 0x10 is SPU ADPCM.
"""
import argparse
import struct
from array import array

from . import adpcm


def packets(data):
    """Yield (stream_id, payload) for every PES packet in a program stream."""
    i, n = 0, len(data)
    while True:
        i = data.find(b"\x00\x00\x01", i)
        if i < 0 or i + 4 > n:
            return
        sid = data[i + 3]
        if sid == 0xBA:                               # pack header
            if data[i + 4] >> 6 == 1:                 # MPEG-2
                i += 14 + (data[i + 13] & 7)
            else:
                i += 12
            continue
        if sid == 0xB9:                               # end code
            return
        if sid < 0xBB:
            i += 3
            continue
        length = struct.unpack_from(">H", data, i + 4)[0]
        body = data[i + 6:i + 6 + length]
        if sid in (0xBD,) or 0xC0 <= sid <= 0xEF:
            if body and body[0] >> 6 == 2:            # MPEG-2 PES header
                body = body[3 + body[2]:]
            yield sid, body
        i += 6 + length


def split(data, audio_sub=0xA0):
    video, audio = bytearray(), bytearray()
    for sid, body in packets(data):
        if sid == 0xE0:
            video += body
        elif sid == 0xBD and len(body) > 4 and body[1] == audio_sub:
            audio += body[4:]
    return bytes(video), bytes(audio)


def parse_audio(track):
    """Return (header dict, body bytes) for an SShd/SSbd track."""
    if track[:4] != b"SShd":
        raise ValueError("no SShd header")
    size, typ, rate, ch, il, ls, le = struct.unpack_from("<7I", track, 4)
    body_at = 8 + size
    if track[body_at:body_at + 4] != b"SSbd":
        raise ValueError("no SSbd body")
    hdr = dict(type=typ, rate=rate, channels=ch, interleave=il,
               loop_start=ls, loop_end=le)
    return hdr, track[body_at + 8:]


def audio_to_channels(hdr, body):
    ch, il = hdr["channels"], hdr["interleave"]
    parts = adpcm.deinterleave(body, ch, il) if ch > 1 else [body]
    if hdr["type"] == 0x01:
        return [array("h", p[:len(p) & ~1]) for p in parts]
    if hdr["type"] == 0x10:
        return [adpcm.decode(p) for p in parts]
    raise ValueError("unknown SShd audio type %#x" % hdr["type"])


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pss")
    ap.add_argument("--video")
    ap.add_argument("--audio")
    ap.add_argument("--info", action="store_true")
    a = ap.parse_args()
    video, track = split(open(a.pss, "rb").read())
    hdr, body = parse_audio(track) if track else (None, b"")
    if a.info:
        print("video %d bytes" % len(video))
        print("audio %s, %d bytes" % (hdr, len(body)))
    if a.video:
        open(a.video, "wb").write(video)
    if a.audio and hdr:
        adpcm.write_wav(a.audio, audio_to_channels(hdr, body), hdr["rate"])


if __name__ == "__main__":
    main()
