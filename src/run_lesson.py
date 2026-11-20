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

Like the apps themselves, every MP3 (also every part) gets its timeline: the start and end time and the text of
every spoken segment, as a JSON file with the same name and inside the MP3 (ID3 tag TXXX:SHADOWING_TIMELINE).
"""
import ast
import asyncio
import importlib
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


def split_export(name: str):
    """Wrap app.normalize_and_export: keep the row audio, and save a long full lesson as parts.
    Every part gets its own timeline (JSON file and tag inside the MP3), made by the app from app.ROW_TIMINGS."""
    export = app.normalize_and_export
    rows = []

    def wrapped(audio, path, timeline=None):
        if re.fullmatch(r"\d{3}\.mp3", path.name):
            rows.append(audio)
            return export(audio, path)
        total = len(audio)
        n = math.ceil(total / (MAX_PART_MINUTES * 60000))
        if n <= 1 or len(rows) < n:
            return export(audio, path, timeline)
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
            export(part, part_path, app.make_timeline(part_path.name, range(bounds[k], bounds[k + 1])))
            print(f"  Part {k + 1}: rows {bounds[k] + 1}-{bounds[k + 1]}, {len(part) / 60000:.1f} mins -> {part_path.name}")

    app.normalize_and_export = wrapped


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
