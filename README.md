# Shorts publishing toolkit

A small, self-contained pipeline for turning a long-form video into vertical
shorts with voiceover, then publishing them to YouTube, TikTok, and Instagram
through each platform's own official API — no third-party scheduler in the
middle. Built while running a fan commentary channel for a game's marketing
countdown, then pulled out into its own repo since none of it is specific to
that use case.

## Layout

- **`pipeline/`** — `make_shorts.py` renders vertical MP4s from a source
  video plus a JSON config (one entry per short: source clip, start time,
  duration, name-card text, optional montage/image-clip layouts, and an
  optional `"outro": true` follow/subscribe card over the last couple
  seconds — needs `pip install pillow`). `bleep_scan.py` finds swear words
  in a clip and saves bleep timestamps; `tts.ps1` generates voiceover WAVs
  with Windows' built-in TTS voices. See `pipeline/examples/*.json` for
  config shapes to copy from.
- **`publish/`** — scripts that log into YouTube, TikTok, and Instagram and
  post a rendered short directly, plus `publish_all.py` to drive all three
  from one CLI. Each platform's setup is genuinely different (OAuth flow,
  review/audit requirements, video-hosting requirements) — see
  [`publish/README.md`](publish/README.md) for the full walkthrough,
  including the non-obvious gotchas each one hit during setup.
- **`branding/`** — one-off scripts used to generate/color-grade a channel
  avatar (`make_avatar.py`, `grade_avatar.py`, `grade_avatar2.py`) and a
  channel banner (`make_banner.py`). These are closer to worked examples than
  a general tool — `grade_avatar.py`'s background-recolor heuristic in
  particular was tuned against one specific source photo's lighting, so
  expect to re-tune the color stops and masking thresholds for your own.

## Quick start

1. `pipeline/` — write a `shorts.json` (see `pipeline/examples/`), run
   `python make_shorts.py all` to get MP4s in `pipeline/output/`.
2. `publish/` — follow [`publish/README.md`](publish/README.md) to set up
   OAuth for whichever platforms you want, then
   `python publish_all.py <video_id> --platforms youtube,tiktok,instagram`.

Nothing here talks to any paid or third-party service — only each platform's
own developer APIs — so the only ongoing cost is your own hosting for the
public video URLs Instagram's API requires (a free GitHub Pages repo works
fine; see the "Public video hosting" section of `publish/README.md`).
