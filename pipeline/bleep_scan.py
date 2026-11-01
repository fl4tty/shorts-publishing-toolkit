"""Find swear words in each short's clip audio and store bleep times in shorts.json.

Run through make_shorts.py (`python make_shorts.py scan [ID ...]`), which launches
this with Python 3.12 because faster-whisper doesn't install on 3.15 yet.
Bleep times are written per short as "bleeps": [{"start", "end", "word"}], in
seconds from the start of the *rendered short's own timeline* - i.e. already
offset past any earlier clips in a montage. Review or edit them before rendering.

Works on both short styles:
  - continuous: one "start"/"duration" cut from "source" (or the config's).
  - montage ("clips"): each clip scanned in its own source window, image clips
    skipped (they carry no audio), and each clip's bleep times shifted by the
    sum of the durations of every clip before it, matching how render_short
    concatenates clip audio into one continuous "[ma]" track.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel

KIT = Path(__file__).resolve().parent
CONFIG = Path(os.environ.get("SHORTS_CONFIG", KIT / "shorts.json"))
PAD = 0.06
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

SWEARS = re.compile(
    r"^(mother)?f+u+c+k\w*|^fuckin\w*|^(bull)?shit\w*|^bitch\w*|^ass(hole)?s?$|^dick(head)?s?$"
    r"|^pussy|^cunt\w*|^nigg\w*|^cock(sucker)?s?$|^bastards?$"
    r"|^mierda$|^co[nñ]o$|^cabr[oó]n\w*|^put[ao]s?$|^pendej\w*|^carajo$|^joder$|^ching\w*",
    re.IGNORECASE,
)


def censor(word):
    return word[0] + "*" * (len(word) - 1)


def to_seconds(ts):
    secs = 0.0
    for part in str(ts).split(":"):
        secs = secs * 60 + float(part)
    return secs


def is_image(source):
    return Path(str(source)).suffix.lower() in IMAGE_EXTS


def scan_window(model, source, start, duration):
    """Transcribe one [start, start+duration) window of `source` and return
    swear hits as {"start", "end", "word"} in seconds from the window's own 0."""
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "clip.wav"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-ss", str(start), "-t", str(duration), "-i", str(source),
                        "-vn", "-ac", "1", "-ar", "16000", str(wav)], check=True)
        # pass raw samples: the installed PyAV is too new for faster-whisper's file decoder
        with wave.open(str(wav), "rb") as w:
            samples = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
        segments, _ = model.transcribe(samples, language="en", word_timestamps=True,
                                       condition_on_previous_text=False)
        hits = []
        for seg in segments:
            for w in seg.words or []:
                word = re.sub(r"[^\w'ñó-]", "", w.word.strip()).strip("'-")
                if word and SWEARS.search(word):
                    hits.append({"start": round(max(0.0, w.start - PAD), 2),
                                 "end": round(w.end + PAD, 2),
                                 "word": censor(word)})
        return hits


def scan_continuous(model, cfg, short):
    start = to_seconds(short["start"])
    duration = float(short.get("duration", 60)) + 2
    source = short.get("source", cfg["source"])
    return scan_window(model, source, start, duration)


def scan_clips(model, cfg, short):
    bleeps = []
    offset = 0.0
    for c in short["clips"]:
        dur = float(c["duration"])
        src = c.get("source", short.get("source", cfg["source"]))
        if not is_image(src):
            for hit in scan_window(model, src, to_seconds(c["start"]), dur):
                bleeps.append({"start": round(hit["start"] + offset, 2),
                               "end": round(hit["end"] + offset, 2),
                               "word": hit["word"]})
        offset += dur
    return bleeps


def main():
    cfg = json.load(open(CONFIG, encoding="utf-8-sig"))
    ids = set(sys.argv[1:])
    model = WhisperModel(cfg.get("whisper_model", "small"), device="cpu", compute_type="int8")
    for short in cfg["shorts"]:
        if ids and short["id"] not in ids:
            continue
        if "clips" in short:
            bleeps = scan_clips(model, cfg, short)
        else:
            bleeps = scan_continuous(model, cfg, short)
        short["bleeps"] = bleeps
        found = ", ".join(f"{b['word']} @ {b['start']:.1f}s" for b in bleeps) or "none"
        print(f"[scan] {short['id']}: {len(bleeps)} bleep(s) - {found}", flush=True)
    json.dump(cfg, open(CONFIG, "w", encoding="utf-8"), indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
