from __future__ import annotations

import asyncio
import csv
import io
import sys
import edge_tts
from pathlib import Path
from pydub import AudioSegment

sys.stdout.reconfigure(encoding="utf-8")


# ===========================================================================
# SHARED CONFIGURATION (Applies to BOTH Normal Mode and Dialog Mode)
# ===========================================================================

BASE_DIR   = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"

# Adaptive silence: pause after each play = segment_duration × SILENCE_RATIO
SILENCE_RATIO  = 0.7
MIN_SILENCE_MS = 1000   # minimum pause in milliseconds

# Final MP3 output settings (normalized for universal player compatibility)
OUTPUT_SAMPLE_RATE = 44100   # Hz  (standard CD quality)
OUTPUT_CHANNELS    = 2       # 1=mono, 2=stereo
OUTPUT_BITRATE     = "128k"  # MP3 bitrate

# Choose which mode to run (True = Dialog Mode, False = Normal Mode)
DIALOG_MODE = True


# ===========================================================================
# NORMAL MODE CONFIGURATION
# ===========================================================================

# ---------------------------------------------------------------------------
# CSV_DATA — paste your normal CSV content here
#
# Headers must be exactly "dutch" or "persian" (case-insensitive).
# Column numbers are positional: left=col1, next=col2, etc.
# Duplicate headers are fine: dutch, persian, dutch  → col1, col2, col3
# ---------------------------------------------------------------------------
CSV_DATA = """
dutch,persian,dutch
het huis,خانه,Dit is een mooi huis.
de fiets,دوچرخه,Ik ga met de fiets naar de universiteit.
het boek,کتاب,Ik lees een interessant boek.
""".strip()

# Available TTS voices (used in normal mode via SEGMENT_ORDER)
VOICES = {
    ("dutch",   "male"):   "nl-NL-MaartenNeural",
    ("dutch",   "female"): "nl-NL-FennaNeural",
    ("persian", "male"):   "fa-IR-FaridNeural",
    ("persian", "female"): "fa-IR-DilaraNeural",
}

# ---------------------------------------------------------------------------
# SEGMENT_ORDER — used in normal mode only (ignored in dialog mode).
#
# Each entry is a tuple:  (column_index, gender, repeats)
#   column_index : 1-based column position in the CSV  (1, 2, 3, ...)
#   gender       : "male" or "female"
#   repeats      : how many times to play this segment
# ---------------------------------------------------------------------------
SEGMENT_ORDER = [
    (1, "male",   2),
    (2, "female", 1),
    (3, "male",   2),
]


# ===========================================================================
# DIALOG MODE CONFIGURATION
# ===========================================================================

# How many times every dialog sentence is repeated.
DIALOG_REPEATS = 1

# Voices mapped to speakers by row:
#   Row 1 = speaker "a"
#   Row 2 = speaker "b"
#   Row 3 = speaker "c", etc.
DIALOG_VOICES = {
    "a": "nl-NL-MaartenNeural",   # speaker A (Row 1) — male
    "b": "nl-NL-FennaNeural",     # speaker B (Row 2) — female
    "c": "nl-NL-ColetteNeural",   # speaker C (Row 3) — female
}

# ---------------------------------------------------------------------------
# DIALOG_CSV_DATA — used only when DIALOG_MODE = True.
#
# - No headers needed!
# - Each ROW is one natural turn in the conversation (a, then b, then a, then b...).
# - Start each row with the speaker label (e.g. "a:" or "b:").
# - That label determines the voice and is NOT spoken.
# - If a speaker says multiple sentences in one turn, separate them with commas.
# ---------------------------------------------------------------------------
DIALOG_CSV_DATA = """
a: Hallo! Goedemorgen,Hoe gaat het met je?
b: Goedemorgen! Goed dank je,En hoe is het met jou?
a: Prima! Het zonnetje schijnt,Wat zijn je plannen voor vandaag?
b: Ik ga zo naar de bibliotheek,Ik moet studeren voor een examen Nederlands.
a: Wat goed van je! Veel succes met studeren.
b: Dank je wel! Wat ga jij eigenlijk doen?
a: Ik ga even naar de markt,Ik moet verse groenten en fruit halen.
b: Klinkt leuk! Koop ook lekkere stroopwafels voor me!
a: Haha zal ik zeker doen! Tot vanmiddag dan.
b: Tot vanmiddag! Fijne dag nog!
""".strip()


# ===========================================================================
# CSV loading
# ===========================================================================

def load_normal_csv() -> tuple[list[str], list[list[str]]]:
    """Return (headers, data_rows) for normal mode."""
    reader    = csv.reader(io.StringIO(CSV_DATA))
    all_rows  = list(reader)
    if not all_rows:
        raise ValueError("CSV_DATA is empty.")

    headers   = [h.strip().lower() for h in all_rows[0]]
    data_rows = [r for r in all_rows[1:] if any(c.strip() for c in r)]

    allowed = {"dutch", "persian"}
    bad = [h for h in headers if h not in allowed]
    if bad:
        raise ValueError(
            f"Invalid header(s): {bad}. Headers must be 'dutch' or 'persian' only."
        )
    return headers, data_rows


def load_dialog_csv() -> list[tuple[str, list[str]]]:
    """Return list of (speaker_id, sentences) for each speaker row.
    The first cell of each row must start with 'a:' or 'b:' or 'c:', etc.
    The speaker label is stripped so it is not spoken.
    """
    reader = csv.reader(io.StringIO(DIALOG_CSV_DATA))
    speaker_rows = []

    for row in reader:
        clean_cells = [c.strip() for c in row if c.strip()]
        if not clean_cells:
            continue

        first_cell = clean_cells[0]
        if ":" in first_cell:
            prefix, first_text = first_cell.split(":", 1)
            speaker_id = prefix.strip().lower()
            clean_cells[0] = first_text.strip()
        else:
            raise ValueError(
                f"Row must start with a speaker label like 'a:' or 'b:'. Got: '{first_cell}'"
            )

        sentences = [c for c in clean_cells if c]
        speaker_rows.append((speaker_id, sentences))

    if not speaker_rows:
        raise ValueError("DIALOG_CSV_DATA is empty.")

    return speaker_rows


# ===========================================================================
# Audio helpers
# ===========================================================================

async def make_audio(text: str, voice: str, filepath: Path) -> None:
    """Synthesize text to speech and save to filepath."""
    await edge_tts.Communicate(text, voice).save(str(filepath))


def adaptive_silence(segment: AudioSegment) -> AudioSegment:
    """Return silence whose duration scales with the segment's length."""
    ms = max(MIN_SILENCE_MS, int(len(segment) * SILENCE_RATIO))
    return AudioSegment.silent(duration=ms)


def normalize_and_export(audio: AudioSegment, path: Path) -> None:
    """Remove any stale file, normalize audio settings, and export as MP3."""
    if path.exists():
        path.unlink()
        print(f"  Removed stale: {path.name}")
    audio = audio.set_frame_rate(OUTPUT_SAMPLE_RATE).set_channels(OUTPUT_CHANNELS)
    audio.export(str(path), format="mp3", bitrate=OUTPUT_BITRATE)


# ===========================================================================
# Order validation (normal mode only)
# ===========================================================================

def validate_order(headers: list[str]) -> None:
    """Check that every SEGMENT_ORDER entry references a valid column."""
    for col_1based, gender, repeats in SEGMENT_ORDER:
        idx = col_1based - 1
        if idx < 0 or idx >= len(headers):
            raise ValueError(
                f"SEGMENT_ORDER references col{col_1based}, but CSV only has "
                f"{len(headers)} column(s)."
            )
        lang = headers[idx]
        if gender not in ("male", "female"):
            raise ValueError(
                f"Gender must be 'male' or 'female', got '{gender}'."
            )
        if (lang, gender) not in VOICES:
            raise ValueError(
                f"No voice configured for lang='{lang}', gender='{gender}'."
            )


# ===========================================================================
# Normal mode builder
# ===========================================================================

async def build_row_normal(
    row_index: int,
    cells:     list[str],
    headers:   list[str],
    tmp_dir:   Path,
) -> AudioSegment:
    """Normal mode: assemble audio per SEGMENT_ORDER."""
    cache: dict[tuple[int, str], AudioSegment] = {}

    for col_1based, gender, repeats in SEGMENT_ORDER:
        col_idx = col_1based - 1
        key     = (col_idx, gender)
        if key in cache:
            continue

        lang  = headers[col_idx]
        text  = cells[col_idx].strip() if col_idx < len(cells) else ""
        voice = VOICES[(lang, gender)]
        path  = tmp_dir / f"row{row_index:03d}_col{col_1based}_{gender}.mp3"

        print(f"  [TTS] col{col_1based} {lang} ({gender}, ×{repeats}): {text}")
        await make_audio(text, voice, path)
        cache[key] = AudioSegment.from_mp3(str(path))

    result = AudioSegment.empty()
    for col_1based, gender, repeats in SEGMENT_ORDER:
        seg   = cache[(col_1based - 1, gender)]
        pause = adaptive_silence(seg)
        for _ in range(repeats):
            result += seg + pause

    return result


# ===========================================================================
# Dialog mode builder
# ===========================================================================

async def build_dialog_turn(
    turn_index: int,
    speaker_id: str,
    text: str,
    tmp_dir: Path,
) -> AudioSegment:
    """Build audio for a single sentence spoken by speaker_id."""
    if speaker_id not in DIALOG_VOICES:
        raise ValueError(
            f"Speaker '{speaker_id}' not found in DIALOG_VOICES. "
            f"Configured speakers: {list(DIALOG_VOICES.keys())}"
        )

    voice = DIALOG_VOICES[speaker_id]
    path  = tmp_dir / f"turn{turn_index:03d}_{speaker_id}.mp3"

    print(f"  [TTS] turn {turn_index:02d} | speaker '{speaker_id}' (×{DIALOG_REPEATS}): {text}")
    await make_audio(text, voice, path)
    seg   = AudioSegment.from_mp3(str(path))
    pause = adaptive_silence(seg)

    result = AudioSegment.empty()
    for _ in range(DIALOG_REPEATS):
        result += seg + pause

    return result


# ===========================================================================
# Lesson builder
# ===========================================================================

async def build_lesson() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp_dir = OUTPUT_DIR / "_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    if DIALOG_MODE:
        speaker_rows = load_dialog_csv()

        print("=" * 60)
        print("Mode: DIALOG")
        print("Speakers & Sentences:")
        max_turns = 0
        for speaker_id, sentences in speaker_rows:
            voice_name = DIALOG_VOICES.get(speaker_id, "UNKNOWN")
            print(f"  Speaker '{speaker_id}' ({voice_name}): {len(sentences)} sentence(s)")
            if len(sentences) > max_turns:
                max_turns = len(sentences)

        print(f"Total speaker rows: {len(speaker_rows)}")
        print(f"Repeats per sentence: ×{DIALOG_REPEATS}")
        print("=" * 60)

        all_segments: list[AudioSegment] = []
        turn_counter = 1

        # Process row by row: all sentences of Row 1 (speaker a), then Row 2 (speaker b), etc.
        for row_idx, (speaker_id, sentences) in enumerate(speaker_rows, start=1):
            print(f"\nRow {row_idx}/{len(speaker_rows)} (Speaker '{speaker_id}'):")
            row_audio = AudioSegment.empty()

            for s_idx, text in enumerate(sentences, start=1):
                turn_seg = await build_dialog_turn(
                    turn_counter, speaker_id, text, tmp_dir
                )
                row_audio += turn_seg
                turn_counter += 1

            all_segments.append(row_audio)
            out_path = OUTPUT_DIR / f"{row_idx:03d}.mp3"
            normalize_and_export(row_audio, out_path)
            print(f"  Saved row: {out_path.name} ({out_path.stat().st_size // 1024} KB)")

    else:
        headers, data_rows = load_normal_csv()
        validate_order(headers)

        print("=" * 60)
        print("Mode: NORMAL")
        print("CSV columns:")
        for i, lang in enumerate(headers, 1):
            print(f"  col{i} = {lang}")

        print("\nPlayback order:")
        for col_1based, gender, repeats in SEGMENT_ORDER:
            lang = headers[col_1based - 1]
            print(f"  col{col_1based} ({lang:7s})  |  {gender:6s}  |  ×{repeats}")

        print(f"\nRows to process: {len(data_rows)}")
        print("=" * 60)

        all_segments: list[AudioSegment] = []

        for i, cells in enumerate(data_rows, start=1):
            preview = cells[0].strip() if cells else f"row {i}"
            print(f"\nRow {i}/{len(data_rows)}: {preview}")

            segment = await build_row_normal(i, cells, headers, tmp_dir)
            all_segments.append(segment)

            out_path = OUTPUT_DIR / f"{i:03d}.mp3"
            normalize_and_export(segment, out_path)
            print(f"  Saved: {out_path.name}  ({out_path.stat().st_size // 1024} KB)")

    # --- Full lesson ---
    print("\n" + "=" * 60)
    print("Building full lesson file...")
    full_lesson = sum(all_segments, AudioSegment.empty())

    full_path = OUTPUT_DIR / "full_lesson.mp3"
    normalize_and_export(full_lesson, full_path)
    print(f"Full lesson: {full_path}")
    print(f"Duration   : {len(full_lesson) / 1000:.1f}s")
    print("=" * 60)
    print("Done!")


asyncio.run(build_lesson())