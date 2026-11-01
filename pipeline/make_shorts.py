"""Build vertical YouTube Shorts from a source video plus voiceover.

Usage:
    python make_shorts.py voices              list installed Windows TTS voices
    python make_shorts.py scan [ID ...]       find swear words in the clips, save bleep times
    python make_shorts.py tts [ID ...]        generate voiceover WAVs from shorts.json
    python make_shorts.py render [ID ...]     render finished MP4s into output/
    python make_shorts.py all [ID ...]        tts + render
    python make_shorts.py sheets [NAME ...]   contact sheets (timestamped frame grids)
                                              for the "sheets" list in the config

Add  --config FILE.json  to use a config other than shorts.json, e.g.
    python make_shorts.py --config shorts_characters.json sheets

Edit shorts.json first: set "source" to your video and each short's "start".
To use your own recorded voiceover, drop a WAV at vo/<id>_<n>.wav (n = 1, 2, ...)
and skip the tts step for that short.

Montage shorts: instead of "start"/"duration", a short can have a "clips" list.
Each clip is {"source", "start", "duration", "name", "role", "crop_x", "layout"};
the clips are cut together in order and each gets its own name card.

Image clips: give a clip a "source" ending in .jpg/.jpeg/.png/.webp and drop
"start" - it's held for "duration" seconds with a slow Ken Burns zoom instead of
a video crop, silent (no audio of its own). "crop_x"/"crop_y" (0-1) pick which
part of the image fills the vertical frame if its aspect ratio doesn't match.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import wave
from pathlib import Path

KIT = Path(__file__).resolve().parent
CONFIG = Path(os.environ.get("SHORTS_CONFIG", KIT / "shorts.json"))
if "--config" in sys.argv:
    _i = sys.argv.index("--config")
    if _i + 1 >= len(sys.argv):
        sys.exit("--config needs a file name")
    CONFIG = Path(sys.argv[_i + 1])
    del sys.argv[_i:_i + 2]
if not CONFIG.is_absolute() and not CONFIG.exists():
    CONFIG = KIT / CONFIG
VO_DIR = KIT / "vo"
WORK_DIR = KIT / "work"
OUT_DIR = KIT / "output"
FONT = Path(r"C:\Windows\Fonts\arialbd.ttf")

W, H = 1080, 1920
WORDS_PER_CAPTION = 4
SEGMENT_GAP = 0.3
STEREO = "aresample=48000,aformat=channel_layouts=stereo"


def load_config():
    with open(CONFIG, encoding="utf-8-sig") as f:
        return json.load(f)


def pick(shorts, ids):
    if not ids:
        return shorts
    chosen = [s for s in shorts if s["id"] in ids]
    missing = set(ids) - {s["id"] for s in chosen}
    if missing:
        sys.exit(f"Unknown short id(s): {', '.join(sorted(missing))}")
    return chosen


def to_seconds(ts):
    if isinstance(ts, (int, float)):
        return float(ts)
    secs = 0.0
    for part in str(ts).split(":"):
        secs = secs * 60 + float(part)
    return secs


def srt_time(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def wav_duration(path):
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def vo_path(short, n):
    return VO_DIR / f"{short['id']}_{n}.wav"


def run(cmd, **kw):
    print("  $", " ".join(str(c) for c in cmd[:6]), "..." if len(cmd) > 6 else "")
    subprocess.run(cmd, check=True, **kw)


# --- TTS ---------------------------------------------------------------------

def cmd_voices(cfg):
    if cfg.get("engine") == "edge":
        run([sys.executable, "-m", "edge_tts", "--list-voices"])
        return
    run(["powershell", "-NoProfile", "-Command",
         "Add-Type -AssemblyName System.Speech;"
         "(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices()"
         " | ForEach-Object { $_.VoiceInfo.Name }"])


def tts_windows(cfg, text_file, out):
    run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(KIT / "tts.ps1"),
         "-TextFile", str(text_file),
         "-OutFile", str(out),
         "-Voice", cfg.get("voice", ""),
         "-Rate", str(cfg.get("rate", 0))])


def tts_edge(cfg, text_file, out):
    """Microsoft neural voices via edge-tts (online); converted to WAV for rendering."""
    mp3 = out.with_suffix(".mp3")
    run([sys.executable, "-m", "edge_tts",
         "--voice", cfg.get("edge_voice", "en-US-AndrewNeural"),
         f"--rate={cfg.get('edge_rate', '+0%')}",
         f"--pitch={cfg.get('edge_pitch', '+0Hz')}",
         "--file", str(text_file),
         "--write-media", str(mp3)])
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(mp3),
         "-ar", "48000", "-ac", "1", str(out)])
    mp3.unlink()


def cmd_tts(cfg, shorts):
    VO_DIR.mkdir(exist_ok=True)
    WORK_DIR.mkdir(exist_ok=True)
    engine = tts_edge if cfg.get("engine") == "edge" else tts_windows
    voice_keys = ("edge_voice", "edge_rate", "edge_pitch", "voice", "rate")
    for short in shorts:
        print(f"[tts] {short['id']}")
        # a short can override any global voice setting
        short_cfg = {**cfg, **{k: short[k] for k in voice_keys if k in short}}
        for n, seg in enumerate(short["vo"], 1):
            text_file = WORK_DIR / f"{short['id']}_{n}.txt"
            text_file.write_text(seg["text"], encoding="utf-8")
            engine(short_cfg, text_file, vo_path(short, n))


# --- Contact sheets ------------------------------------------------------------

def cmd_sheets(cfg, names):
    """Tile frames from each "sheets" entry into labelled JPG grids in work/sheets/.

    Entry: {"name", "source", "start", "end", "step", "cols", "rows", "fast"}.
    Each frame is stamped with its time in the source video (HH:MM:SS.mmm).
    "fast": true decodes keyframes only - much quicker on long 4K files,
    but timestamps land on the nearest keyframe.
    """
    sheets = cfg.get("sheets", [])
    if names:
        sheets = [s for s in sheets if s["name"] in names]
    if not sheets:
        sys.exit(f"No matching \"sheets\" entries in {CONFIG.name}")
    out_dir = WORK_DIR / "sheets"
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FONT, out_dir / "font.ttf")
    for sh in sheets:
        source = Path(sh.get("source", cfg.get("source", "")))
        if not source.exists():
            sys.exit(f"Source video not found: {source}")
        start = to_seconds(sh.get("start", 0))
        end = to_seconds(sh["end"])
        step = float(sh.get("step", 2))
        cols, rows = int(sh.get("cols", 5)), int(sh.get("rows", 4))
        for old in out_dir.glob(f"{sh['name']}_*.jpg"):
            old.unlink()
        vf = (f"fps=1/{step},scale=384:-2,"
              f"drawtext=fontfile=font.ttf:text='%{{pts\\:hms\\:{start}}}':fontsize=24:"
              "fontcolor=white:box=1:boxcolor=black@0.75:boxborderw=6:x=6:y=6,"
              f"tile={cols}x{rows}:padding=4:color=black")
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
        if sh.get("fast"):
            cmd += ["-skip_frame", "nokey"]
        cmd += ["-ss", str(start), "-t", f"{end - start:.2f}", "-i", str(source),
                "-an", "-vf", vf, "-q:v", "4", f"{sh['name']}_%02d.jpg"]
        print(f"[sheets] {sh['name']} ({start:.0f}s-{end:.0f}s every {step:g}s)")
        run(cmd, cwd=out_dir)
    print(f"  -> {out_dir}")


# --- Render --------------------------------------------------------------------

def layout_segments(short):
    """Return [(start, duration, text)] with segments pushed apart so none overlap."""
    placed, cursor = [], 0.0
    for n, seg in enumerate(short["vo"], 1):
        path = vo_path(short, n)
        if not path.exists():
            sys.exit(f"Missing voiceover {path.name} - run the tts step or add your own WAV.")
        dur = wav_duration(path)
        start = max(float(seg.get("at", 0)), cursor)
        placed.append((start, dur, seg["text"]))
        cursor = start + dur + SEGMENT_GAP
    return placed


def write_captions(segments, path):
    entries = []
    for start, dur, text in segments:
        words = text.split()
        chunks = [words[i:i + WORDS_PER_CAPTION] for i in range(0, len(words), WORDS_PER_CAPTION)]
        # time each chunk by its share of the segment's characters
        total = sum(len(" ".join(c)) for c in chunks) or 1
        t = start
        for c in chunks:
            line = " ".join(c)
            d = dur * len(line) / total
            entries.append((t, t + d, line))
            t += d
    with open(path, "w", encoding="utf-8") as f:
        for i, (a, b, line) in enumerate(entries, 1):
            f.write(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{line}\n\n")


DEFAULT_LOGO_PATTERN = r"GTA\s*6\b|GTA\s*VI\b"


def logo_windows(segments, pattern, pad_before=0.0, pad_after=0.15, min_dur=0.9):
    """Time windows [(start, end)] where `pattern` is being spoken, estimated the same
    way captions are timed: proportionally by character position within each VO segment.
    """
    windows = []
    for start, dur, text in segments:
        total = len(text) or 1
        for m in pattern.finditer(text):
            a = start + dur * (m.start() / total) - pad_before
            b = start + dur * (m.end() / total) + pad_after
            if b - a < min_dur:
                mid = (a + b) / 2
                a, b = mid - min_dur / 2, mid + min_dur / 2
            windows.append((max(a, 0.0), b))
    return windows


def frame_filter(inp, x_pos, layout, tag):
    """Widescreen -> 1080x1920. Returns a filter chain the caller continues with ','."""
    if layout == "fit":
        # whole widescreen frame centred over a blurred, zoomed copy of itself
        return (
            f"{inp}split[bgsrc{tag}][fgsrc{tag}];"
            f"[bgsrc{tag}]scale=-2:{H},crop={W}:{H},boxblur=30:2,eq=brightness=-0.15[bg{tag}];"
            f"[fgsrc{tag}]scale={W}:-2[fg{tag}];"
            f"[bg{tag}][fg{tag}]overlay=(W-w)/2:(H-h)/2,setsar=1"
        )
    return f"{inp}scale=-2:{H},crop={W}:{H}:(iw-{W})*{x_pos}:0,setsar=1"


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def is_image(source):
    return Path(str(source)).suffix.lower() in IMAGE_EXTS


def image_filter(inp, x_pos, y_pos, duration, zoom_amount=0.12):
    """Still image -> 1080x1920 with a slow Ken Burns zoom, cover-cropped to fill the frame.

    Grows a scale filter (eval=frame) under a fixed-size crop rather than using ffmpeg's
    zoompan, which has a severe performance cliff on longer clips (clocked at 70+ minutes
    for a 31s montage here instead of the ~2s/clip this approach takes).
    """
    cover_w, cover_h = W * 2, H * 2  # extra headroom so the zoomed-in crop stays sharp
    dur = max(float(duration), 0.01)
    return (
        f"{inp}scale=w={cover_w}:h={cover_h}:force_original_aspect_ratio=increase,"
        f"crop={cover_w}:{cover_h}:(iw-{cover_w})*{x_pos}:(ih-{cover_h})*{y_pos},setsar=1,"
        f"scale=w='{cover_w}*(1+{zoom_amount}*t/{dur:.3f})':"
        f"h='{cover_h}*(1+{zoom_amount}*t/{dur:.3f})':eval=frame,"
        f"crop=w={W}:h={H}:x='(iw-{W})/2':y='(ih-{H})/2'"
    )


def render_short(cfg, short):
    def opt(key, default):
        return short.get(key, cfg.get(key, default))

    clips = short.get("clips")
    if clips:
        for c in clips:
            src = Path(c.get("source", short.get("source", cfg["source"])))
            if not src.exists():
                sys.exit(f"Source not found: {src}  (clip {c.get('name', '?')})")
            if "duration" not in c:
                sys.exit(f"Clip {c.get('name', '?')} needs a \"duration\"")
            if "start" not in c and not is_image(src):
                sys.exit(f"Clip {c.get('name', '?')} needs a \"start\" (or use an image source)")
    else:
        source = Path(short.get("source", cfg["source"]))
        if not source.exists():
            sys.exit(f"Source video not found: {source}  (set \"source\" in {CONFIG.name})")

    work = WORK_DIR / short["id"]
    work.mkdir(parents=True, exist_ok=True)
    segments = layout_segments(short)
    vo_end = max(s + d for s, d, _ in segments)
    if clips:
        duration = sum(float(c["duration"]) for c in clips)
        if vo_end > duration:
            sys.exit(f"{short['id']}: voiceover runs to {vo_end:.1f}s but the clips only "
                     f"add up to {duration:.1f}s - lengthen clips or move the VO earlier.")
    else:
        duration = max(float(short.get("duration", 0)), vo_end + 1.0)

    # filter inputs are referenced relative to the work dir to dodge Windows path escaping
    write_captions(segments, work / "captions.srt")
    shutil.copyfile(FONT, work / "font.ttf")
    # newline="\n": drawtext renders a Windows \r as an extra blank line
    (work / "hook.txt").write_text("\n".join(textwrap.wrap(short["hook"], 22)), encoding="utf-8", newline="\n")
    end_text = short.get("end_text")
    if end_text:
        (work / "end.txt").write_text("\n".join(textwrap.wrap(end_text, 22)), encoding="utf-8", newline="\n")

    # pop the GTA 6 logo over the footage whenever the VO says "GTA 6" / "GTA VI"
    logo_path = short.get("logo", cfg.get("logo"))
    logo_wins = []
    if logo_path:
        pattern = re.compile(short.get("logo_pattern", cfg.get("logo_pattern", DEFAULT_LOGO_PATTERN)),
                              re.IGNORECASE)
        logo_wins = logo_windows(segments, pattern)

    x_pos = float(short.get("crop_x", 0.5))
    hook_secs = float(short.get("hook_seconds", duration))
    # hook/end-card look; colours are hex RRGGBB, box_opacity 0 (clear) to 1 (solid)
    text_color = opt("text_color", "FFFFFF").lstrip("#")
    box_opacity = float(opt("box_opacity", 0.65))
    # a light box_color suits darker text colours that would vanish on a dark box
    box_color = opt("box_color", "000000").lstrip("#")
    outline = opt("outline_color", "000000").lstrip("#")
    outline_w = int(opt("outline_width", 3))
    # box_opacity 0 drops the box entirely; lean on a thicker outline/shadow instead
    box = f"box=1:boxcolor=0x{box_color}@{box_opacity}" if box_opacity > 0 else "box=0"
    shadow = ":shadowx=4:shadowy=4:shadowcolor=black@0.6" if opt("text_shadow", False) else ""
    overlay_style = (f"fontcolor=0x{text_color}:borderw={outline_w}:bordercolor=0x{outline}@0.9:"
                     f"{box}{shadow}")
    # the end card can have its own look and position, e.g. to clear a logo behind it
    end_color = short.get("end_text_color", text_color).lstrip("#")
    end_opacity = float(short.get("end_box_opacity", box_opacity))
    end_style = (f"fontcolor=0x{end_color}:borderw=3:bordercolor=black@0.7:"
                 f"box=1:boxcolor=black@{end_opacity}")
    end_y = short.get("end_y", "(h-text_h)/2")

    # --- footage: one continuous clip, or a montage of clips with name cards ---
    inputs, pre = [], []
    if clips:
        name_y = int(opt("name_y", 1200))
        name_size = int(opt("name_size", 84))
        role_size = int(opt("role_size", 46))
        name_color = opt("name_color", text_color).lstrip("#")
        name_outline = opt("name_outline_color", outline).lstrip("#")
        name_style = (f"fontcolor=0x{name_color}:borderw={max(outline_w, 5)}:"
                      f"bordercolor=0x{name_outline}@0.9{shadow}")
        role_style = ("fontcolor=white:borderw=4:bordercolor=black@0.9:"
                      "shadowx=3:shadowy=3:shadowcolor=black@0.6")
        pairs = []
        for i, c in enumerate(clips):
            d = float(c["duration"])
            src = c.get("source", short.get("source", cfg["source"]))
            clip_is_image = is_image(src)
            if clip_is_image:
                inputs += ["-framerate", "30", "-loop", "1", "-t", f"{d:.2f}", "-i", str(src)]
                chain = image_filter(f"[{i}:v]", float(c.get("crop_x", x_pos)),
                                     float(c.get("crop_y", 0.5)), d)
            else:
                inputs += ["-ss", str(to_seconds(c["start"])), "-t", f"{d:.2f}", "-i", str(src)]
                chain = frame_filter(f"[{i}:v]", float(c.get("crop_x", x_pos)),
                                     c.get("layout", short.get("layout")), i)
            chain += ",fps=30,format=yuv420p"
            if c.get("name"):
                (work / f"name_{i}.txt").write_text(c["name"], encoding="utf-8", newline="\n")
                # name card pops in a beat after the cut
                chain += (f",drawtext=fontfile=font.ttf:textfile=name_{i}.txt:fontsize={name_size}:"
                          f"{name_style}:x=(w-text_w)/2:y={name_y}:enable='gte(t,0.15)'")
            if c.get("role"):
                (work / f"role_{i}.txt").write_text(
                    "\n".join(textwrap.wrap(c["role"], 30)), encoding="utf-8", newline="\n")
                chain += (f",drawtext=fontfile=font.ttf:textfile=role_{i}.txt:fontsize={role_size}:"
                          f"{role_style}:line_spacing=8:x=(w-text_w)/2:y={name_y + name_size + 18}:"
                          "enable='gte(t,0.25)'")
            pre.append(chain + f"[cv{i}]")
            gain = float(c.get("gain", 1.0))
            if clip_is_image:
                # still images carry no audio of their own - stand in with silence
                pre.append(f"anullsrc=r=48000:cl=stereo:d={d:.3f}[ca{i}]")
            else:
                # apad+atrim: every clip's audio exactly matches its video length
                pre.append(f"[{i}:a]{STEREO},volume={gain},apad,atrim=0:{d:.3f},"
                           f"afade=t=in:d=0.05,afade=t=out:st={max(d - 0.06, 0):.3f}:d=0.06[ca{i}]")
            pairs.append(f"[cv{i}][ca{i}]")
        pre.append("".join(pairs) + f"concat=n={len(clips)}:v=1:a=1[mv][ma]")
        video = "[mv]"
        src_audio = "[ma]"
        n_footage = len(clips)
    else:
        inputs += ["-ss", str(to_seconds(short["start"])), "-t", f"{duration:.2f}", "-i", str(source)]
        video = frame_filter("[0:v]", x_pos, short.get("layout"), "") + ","
        src_audio = "[0:a]"
        n_footage = 1

    # libass lays SRT captions out on a 384x288 grid scaled to the frame, so
    # pixel positions are converted to grid units here.
    # Defaults keep text clear of the YouTube Shorts / Reels / TikTok UI:
    # captions ~760px above the bottom, ~170px in from each side, hook 300px down.
    cap_v = round(float(opt("caption_margin_px", 760)) * 288 / H)
    cap_side = round(float(opt("caption_side_px", 170)) * 384 / W)
    hook_y = int(opt("hook_y", 300))
    overlay_parts = []
    if bool(opt("captions", True)):
        overlay_parts.append(
            "subtitles=captions.srt:force_style='Fontname=Arial,Bold=1,Fontsize=12,"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,"
            f"Shadow=0,Alignment=2,MarginV={cap_v},MarginL={cap_side},MarginR={cap_side}'"
        )
    overlay_parts.append(
        f"drawtext=fontfile=font.ttf:textfile=hook.txt:fontsize=72:{overlay_style}:"
        "line_spacing=12:boxborderw=28:"
        f"x=(w-text_w)/2:y={hook_y}:enable='lt(t,{hook_secs})'"
    )
    video += ",".join(overlay_parts)
    if end_text:
        video += (
            f",drawtext=fontfile=font.ttf:textfile=end.txt:fontsize=84:{end_style}:"
            "line_spacing=12:boxborderw=32:"
            f"x=(w-text_w)/2:y={end_y}:enable='gte(t,{duration - 4:.2f})'"
        )
    logo_filter = None
    if logo_wins:
        video += "[vbase]"
        logo_w = int(opt("logo_width_px", 600))
        logo_y = int(opt("logo_y_px", 520))
        gate = "+".join(f"between(t,{a:.2f},{b:.2f})" for a, b in logo_wins)
        pre.append(f"[LOGO:v]scale={logo_w}:-1,format=rgba[logo]")
        logo_filter = f"[vbase][logo]overlay=x=(W-w)/2:y={logo_y}:enable='{gate}'[vout]"
    else:
        video += "[vout]"

    duck = float(cfg.get("duck_ratio", 8))
    vo_gain = float(cfg.get("vo_gain", 1.6))
    bleeps = short.get("bleeps", [])
    if bleeps:
        # mute the source under each bleep and lay a 1 kHz tone over the gap
        gate = "+".join(f"between(t,{b['start']},{b['end']})" for b in bleeps)
        audio = [
            f"{src_audio}{STEREO},volume=0:enable='{gate}'[src]",
            f"aevalsrc='0.25*sin(2*PI*1000*t)*gt({gate},0)':s=48000:d={duration:.2f},"
            f"{STEREO}[beep]",
        ]
    else:
        audio = [f"{src_audio}{STEREO}[src]"]
    for i, (start, dur, _) in enumerate(segments, 1):
        ms = int(start * 1000)
        # soften the tail so a VO line's end isn't a hard digital cliff against
        # the music bed underneath - the music level itself doesn't change here,
        # this just stops the voice from stopping dead
        fade_d = min(0.35, dur / 2)
        audio.append(
            f"[{n_footage + i - 1}:a]{STEREO},volume={vo_gain},"
            f"afade=t=out:st={max(dur - fade_d, 0):.3f}:d={fade_d:.3f},"
            f"adelay={ms}|{ms}[v{i}]"
        )
    labels = "".join(f"[v{i}]" for i in range(1, len(segments) + 1))
    if len(segments) > 1:
        audio.append(f"{labels}amix=inputs={len(segments)}:normalize=0:duration=longest[vo]")
    else:
        audio.append(f"{labels}anull[vo]")

    # background music bed, ducked under the voiceover same as the source audio
    music_path = short.get("music", cfg.get("music"))
    music_idx = n_footage + len(segments) if music_path else None
    n_vo_splits = 3 if music_path else 2
    audio.append(f"[vo]apad,asplit={n_vo_splits}[vo_key]" + ("[vo_key2]" if music_path else "") + "[vo_mix]")
    # apad: sidechaincompress stops at the shorter input, which would cut the
    # source audio off as soon as the last voiceover segment ends
    duck = float(cfg.get("duck_ratio", 8))
    audio.append(f"[src][vo_key]sidechaincompress=threshold=0.015:ratio={duck}:attack=30:release=500[ducked]")
    mix_inputs = ["[ducked]"]
    if music_path:
        music_start = float(short.get("music_start", cfg.get("music_start", 0)))
        music_gain = float(short.get("music_gain", cfg.get("music_gain", 0.22)))
        music_duck = float(short.get("music_duck_ratio", cfg.get("music_duck_ratio", 4)))
        audio.append(
            f"[{music_idx}:a]{STEREO},atrim=start={music_start:.2f}:end={music_start + duration:.2f},"
            f"asetpts=PTS-STARTPTS,volume={music_gain},afade=t=in:d=1,"
            f"afade=t=out:st={max(duration - 1.5, 0):.2f}:d=1.5[music_src]"
        )
        audio.append(f"[music_src][vo_key2]sidechaincompress=threshold=0.015:"
                      f"ratio={music_duck}:attack=30:release=500[ducked_music]")
        mix_inputs.append("[ducked_music]")
    mix_inputs.append("[vo_mix]")
    if bleeps:
        mix_inputs.append("[beep]")

    # loudnorm evens out every short to the same target loudness without clipping.
    # Two-pass: measure the premix first, then apply a static ("linear") correction.
    # Single-pass "dynamic" loudnorm rides gain in real time, which audibly pumps
    # whenever the mix's energy changes sharply - e.g. a loud VO line cutting out
    # into a quiet music-only bed - so it's only used as a fallback if measuring fails.
    lufs = float(cfg.get("loudness", -12))
    # TP=-2 plus a final limiter leaves headroom for the peaks AAC encoding adds;
    # a short can lower "peak_limit" if its encode still overshoots
    peak = float(short.get("peak_limit", cfg.get("peak_limit", 0.79)))
    premix = (f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:normalize=0:"
              f"duration=first,alimiter=limit=0.95")

    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / f"{short['id']}.mp4"

    def build_cmd(audio_tail, maps, loglevel="error"):
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", loglevel, "-y"] + inputs
        for n in range(1, len(segments) + 1):
            cmd += ["-i", str(vo_path(short, n))]
        if music_path:
            cmd += ["-stream_loop", "-1", "-i", str(music_path)]
        this_pre = pre
        if logo_filter:
            logo_idx = n_footage + len(segments) + (1 if music_path else 0)
            this_pre = [p.replace("[LOGO:v]", f"[{logo_idx}:v]") for p in pre]
            cmd += ["-loop", "1", "-t", f"{duration:.2f}", "-i", str(logo_path)]
        video_steps = [video, logo_filter] if logo_filter else [video]
        cmd += ["-filter_complex", ";".join(this_pre + video_steps + audio + [audio_tail])]
        for m in maps:
            cmd += ["-map", m]
        return cmd

    measure_tail = f"{premix},loudnorm=I={lufs}:TP=-2:LRA=11:print_format=json[measured]"
    # both [vout] and [measured] must be mapped (even to the null muxer) - an
    # unconsumed filter-graph output is a hard ffmpeg error, not just a no-op
    measure_cmd = (build_cmd(measure_tail, ["[vout]", "[measured]"], loglevel="info")
                    + ["-t", f"{duration:.2f}", "-f", "null", "-"])
    measured = None
    try:
        result = subprocess.run(measure_cmd, cwd=work, check=True,
                                 capture_output=True, text=True)
        start, end = result.stderr.rfind("{"), result.stderr.rfind("}")
        if start != -1 and end != -1:
            measured = json.loads(result.stderr[start:end + 1])
    except (subprocess.CalledProcessError, ValueError):
        measured = None

    keys = ("input_i", "input_tp", "input_lra", "input_thresh")
    if measured and all(k in measured for k in keys):
        final_loudnorm = (
            f"loudnorm=I={lufs}:TP=-2:LRA=11:linear=true:"
            f"measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:"
            f"measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
        )
    else:
        print("  ! loudnorm measurement pass failed - falling back to single-pass dynamic normalization")
        final_loudnorm = f"loudnorm=I={lufs}:TP=-2:LRA=11"

    # the micro-fades stop the clip's hard cut points from clicking
    master_tail = (f"{premix},{final_loudnorm},aresample=48000,"
                    f"alimiter=limit={peak}:level=false,"
                    f"afade=t=in:d=0.05,afade=t=out:st={duration - 0.1:.2f}:d=0.1[aout]")
    cmd = build_cmd(master_tail, ["[vout]", "[aout]"]) + [
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-r", "30", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        "-t", f"{duration:.2f}", str(out)]
    print(f"[render] {short['id']} ({duration:.1f}s)")
    run(cmd, cwd=work)
    print(f"  -> {out}")


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "scan":
        # faster-whisper needs Python 3.12; this script itself runs on any version
        return run(["py", "-V:3.12", str(KIT / "bleep_scan.py"), *sys.argv[2:]])
    if len(sys.argv) < 2 or sys.argv[1] not in {"voices", "tts", "render", "all", "sheets"}:
        sys.exit(__doc__)
    action, ids = sys.argv[1], sys.argv[2:]
    cfg = load_config()
    if action == "voices":
        return cmd_voices(cfg)
    if action == "sheets":
        return cmd_sheets(cfg, ids)
    shorts = pick(cfg["shorts"], ids)
    if action in {"tts", "all"}:
        cmd_tts(cfg, shorts)
    if action in {"render", "all"}:
        for short in shorts:
            render_short(cfg, short)


if __name__ == "__main__":
    main()
