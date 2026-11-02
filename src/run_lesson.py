# -*- coding: utf-8 -*-
"""Run google_shadowing_app with LESSON_DATA and SPEAKERS read from files,
so the main app file does not have to be edited for every lesson.

Usage:
    python src/run_lesson.py <lesson_data.txt> <speakers.txt> <output_name>

    lesson_data.txt : the LESSON_DATA text (what goes between the triple quotes)
    speakers.txt    : a 'SPEAKERS = {...}' block
    output_name     : name of the final MP3 (a date-time stamp is appended)
"""
import ast
import asyncio
import sys
from pathlib import Path

import google_shadowing_app as app


def load_speakers(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return ast.literal_eval(text.split("=", 1)[1].strip())


def main() -> None:
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    data_path, speakers_path, name = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    app.LESSON_DATA = data_path.read_text(encoding="utf-8").strip()
    app.SPEAKERS = load_speakers(speakers_path)
    app.OUTPUT_NAME = name
    asyncio.run(app.build_lesson())


if __name__ == "__main__":
    main()
