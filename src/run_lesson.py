# -*- coding: utf-8 -*-
"""Run google_shadowing_app (or edge_tts_shadowing_app) with LESSON_DATA and SPEAKERS read from files,
so the main app file does not have to be edited for every lesson.

Usage:
    python src/run_lesson.py <lesson_data.txt> <speakers.txt> <output_name> [--engine google|edge]

    lesson_data.txt : the LESSON_DATA text (what goes between the triple quotes)
    speakers.txt    : a 'SPEAKERS = {...}' block
    output_name     : name of the final MP3 (a date-time stamp is appended)
    --engine        : google (default) = google_shadowing_app.py: Dutch/English/German with Google Chirp 3 HD,
                      Persian with Edge-TTS; edge = edge_tts_shadowing_app.py: every language with Edge-TTS (free)

A lesson longer than MAX_PART_MINUTES is saved as parts of about equal length instead of one file
(cut between two rows): <output_name>_part1of3_<stamp>.mp3, ...

Next to every MP3 a JSON file with the same name is saved: the start and end time of every spoken segment and its
text, so another program (the phone and watch app) can show the text that is being spoken.
"""
import ast
import asyncio
import importlib
import json
import math
import re
import sys
from pathlib import Path

import google_shadowing_app as app  # replaced in main() when --engine edge is given

MAX_PART_MINUTES = 30
ENGINES = {"google": "google_shadowing_app", "edge": "edge_tts_shadowing_app"}


def load_speakers(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return ast.literal_eval(text.split("=", 1)[1].strip())


def write_timeline(path: Path, row_numbers, row_times) -> None:
    """Save <mp3 name>.json: every spoken segment of the given rows with its time in this MP3 file."""
    lesson = app.parse_lesson_lines(app.LESSON_DATA)
    segments, t = [], 0
    for r in row_numbers:
        times = row_times[r]
        if len(times) != len(lesson[r]):
            raise RuntimeError(f"row {r + 1}: {len(times)} timed segments but {len(lesson[r])} in LESSON_DATA")
        for (tag, text), (speech_ms, pause_ms) in zip(lesson[r], times):
            lang, _, repeats, _ = app.resolve_speaker(tag)
            for _ in range(repeats):
                segments.append({"start": round(t / 1000, 3), "speech_end": round((t + speech_ms) / 1000, 3),
                                 "end": round((t + speech_ms + pause_ms) / 1000, 3),
                                 "row": r + 1, "tag": tag, "lang": lang, "text": text})
                t += speech_ms + pause_ms
    data = {"audio": path.name, "duration": round(t / 1000, 3), "segments": segments}
    json_path = path.with_suffix(".json")
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  Timeline: {len(segments)} segments -> {json_path.name}")


def split_export(name: str):
    """Wrap app.normalize_and_export: keep the row audio, save a long full lesson as parts, and save the
    timeline JSON of every final MP3. The times are taken from the real audio (app.adaptive_silence is
    called once for every segment with the spoken audio, so its length and the pause length are known)."""
    export = app.normalize_and_export
    silence = app.adaptive_silence
    rows, row_times, pending = [], [], []

    def timed_silence(segment, ratio):
        pause = silence(segment, ratio)
        pending.append((len(segment), len(pause)))
        return pause

    def wrapped(audio, path):
        if re.fullmatch(r"\d{3}\.mp3", path.name):
            rows.append(audio)
            row_times.append(pending[:])
            pending.clear()
            return export(audio, path)
        total = len(audio)
        n = math.ceil(total / (MAX_PART_MINUTES * 60000))
        if n <= 1 or len(rows) < n:
            export(audio, path)
            return write_timeline(path, range(len(rows)), row_times)
        # cut at the row boundary closest to k * total / n
        ends, t = [], 0
        for r in rows:
            t += len(r)
            ends.append(t)
        cuts = [min(range(len(ends)), key=lambda i: abs(ends[i] - k * total / n)) + 1 for k in range(1, n)]
        bounds = [0] + sorted(set(cuts)) + [len(rows)]
        stamp = path.name[len(name):]
        for k in range(len(bounds) - 1):
            part = sum(rows[bounds[k]:bounds[k + 1]], app.AudioSegment.empty())
            part_path = path.with_name(f"{name}_part{k + 1}of{len(bounds) - 1}{stamp}")
            export(part, part_path)
            write_timeline(part_path, range(bounds[k], bounds[k + 1]), row_times)
            print(f"  Part {k + 1}: rows {bounds[k] + 1}-{bounds[k + 1]}, {len(part) / 60000:.1f} mins -> {part_path.name}")

    app.normalize_and_export = wrapped
    app.adaptive_silence = timed_silence


def main() -> None:
    global app
    args = sys.argv[1:]
    engine = "google"
    if "--engine" in args:
        i = args.index("--engine")
        engine = args[i + 1] if i + 1 < len(args) else ""
        del args[i:i + 2]
    if len(args) != 3 or engine not in ENGINES:
        print(__doc__)
        sys.exit(1)
    app = importlib.import_module(ENGINES[engine])
    data_path, speakers_path, name = Path(args[0]), Path(args[1]), args[2]
    app.LESSON_DATA = data_path.read_text(encoding="utf-8").strip()
    app.SPEAKERS = load_speakers(speakers_path)
    app.OUTPUT_NAME = name
    split_export(name)
    asyncio.run(app.build_lesson())


if __name__ == "__main__":
    main()
