"""Summarise a bouncekit render so you can check it matches the brief.

Usage (from the repo root):
    uv run python .claude/skills/bouncekit-video/scripts/inspect_video.py \
        out/x_seed42.mp4 [--frames 6] [--at 1.0 ...]

Prints the streams (video/audio), the metadata JSON written beside the MP4 (event
counts, sound triggers, duration) and writes a contact sheet PNG next to the video
(``<stem>_sheet.png``): ``--frames`` frames evenly spread over the video, side by side.
``--at SECONDS`` (repeatable) also saves a frame (540 px wide) at that time
(``<stem>_at<SECONDS>.png``), e.g. to check a hook title shown only in the first seconds.
Open the PNGs with the Read tool to look at them.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def probe(video: Path) -> tuple[float, list[str]]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels",
         "-of", "json", str(video)],
        capture_output=True, text=True, check=True,
    ).stdout
    data = json.loads(out)
    lines = []
    for s in data["streams"]:
        if s["codec_type"] == "video":
            size = f"{s['width']}x{s['height']}"
            lines.append(f"video: {s['codec_name']} {size} @ {s['r_frame_rate']}")
        elif s["codec_type"] == "audio":
            lines.append(f"audio: {s['codec_name']} {s['sample_rate']} Hz x{s['channels']}")
    return float(data["format"]["duration"]), lines


def contact_sheet(video: Path, duration: float, frames: int) -> Path:
    sheet = video.with_name(f"{video.stem}_sheet.png")
    rate = frames / duration
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(video),
         "-vf", f"fps={rate},scale=270:-1,tile={frames}x1", "-frames:v", "1", str(sheet)],
        check=True,
    )
    return sheet


def frame_at(video: Path, seconds: float) -> Path:
    out = video.with_name(f"{video.stem}_at{seconds:g}.png")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", str(seconds), "-i", str(video),
         "-frames:v", "1", "-vf", "scale=540:-1", str(out)],
        check=True,
    )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("video", type=Path)
    parser.add_argument("--frames", type=int, default=6)
    parser.add_argument("--at", type=float, action="append", default=[],
                        help="also save a frame at this time in seconds (repeatable)")
    args = parser.parse_args()
    if not args.video.exists():
        print(f"error: {args.video} not found", file=sys.stderr)
        return 2

    duration, streams = probe(args.video)
    print(f"file: {args.video}  duration: {duration:.2f} s")
    for line in streams:
        print(line)
    if not any(line.startswith("audio") for line in streams):
        print("audio: none (the scene has no A.play rules)")

    meta_path = args.video.with_suffix(".json")
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        events = {k: v for k, v in meta.get("events", {}).items() if v}
        print(f"seed: {meta.get('seed')}  params: {meta.get('params')}")
        print(f"frames: {meta.get('frames')}")
        print(f"events: {events}  sound_triggers: {meta.get('sound_triggers')}")
        print("  (collision = every contact incl. ball-ball; spawn includes split children)")
        print(f"render_seconds: {meta.get('render_seconds')}")

    sheet = contact_sheet(args.video, duration, args.frames)
    print(f"contact sheet: {sheet} ({args.frames} frames, left to right = start to end)")
    for seconds in args.at:
        print(f"frame at {seconds:g} s: {frame_at(args.video, seconds)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
