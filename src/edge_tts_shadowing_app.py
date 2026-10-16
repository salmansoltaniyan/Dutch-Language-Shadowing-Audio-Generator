from __future__ import annotations

import asyncio
import os
import re
import shutil
import sys
import time
from pathlib import Path

import edge_tts
from pydub import AudioSegment

# Ensure UTF-8 output encoding on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ===========================================================================
# SHARED SETTINGS & PATHS
# ===========================================================================

BASE_DIR   = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"

# Adaptive silence: pause after each play = segment_duration × SILENCE_RATIO
SILENCE_RATIO  = 0.9
MIN_SILENCE_MS = 1000   # minimum pause in milliseconds

# Final MP3 output settings (normalized for universal player compatibility)
OUTPUT_SAMPLE_RATE = 44100   # Hz (standard CD quality)
OUTPUT_CHANNELS    = 2       # 1=mono, 2=stereo
OUTPUT_BITRATE     = "192k"  # High quality MP3 bitrate

# Clean up individual chunk/row files (001.mp3, 002.mp3, ...) and temp cache at the end.
# True  = Keep ONLY the complete final lesson file ('full_lesson_edge.mp3'), delete all chunks.
# False = Keep all individual row files (001.mp3, 002.mp3, ...) for separate playback.
CLEANUP_CHUNK_FILES = True


# ===========================================================================
# VOICE PRESETS & SPEAKER CONFIGURATION (Microsoft Edge-TTS Neural)
# ===========================================================================
#
# Supported Languages (All 100% Free via Microsoft Edge-TTS):
#   - "dutch"   : Dutch neural voices (Maarten, Fenna, Colette, Arnaud)
#   - "english" : US English neural voices (Guy, Christopher, Jenny, Aria)
#   - "german"  : German neural voices (Conrad, Killian, Katja, Amala)
#   - "persian" : Persian neural voices (Dilara, Farid)
#
# Available voice presets for each language:
#   "male1", "male2", "female1", "female2" (or specify any exact voice name directly)
# ---------------------------------------------------------------------------

VOICE_PRESETS = {
    "dutch": {
        "male1":   "nl-NL-MaartenNeural",   # Clear, natural standard Dutch male (Recommended)
        "male2":   "nl-BE-ArnaudNeural",    # Flemish / Dutch male
        "female1": "nl-NL-FennaNeural",     # Articulate, clear Dutch female (Recommended)
        "female2": "nl-NL-ColetteNeural",   # Warm, conversational Dutch female
    },
    "english": {
        "male1":   "en-US-GuyNeural",
        "male2":   "en-US-ChristopherNeural",
        "female1": "en-US-JennyNeural",
        "female2": "en-US-AriaNeural",
    },
    "german": {
        "male1":   "de-DE-ConradNeural",
        "male2":   "de-DE-KillianNeural",
        "female1": "de-DE-KatjaNeural",
        "female2": "de-DE-AmalaNeural",
    },
    "persian": {
        "female1": "fa-IR-DilaraNeural",       # Soft, clear, native Persian female (Recommended)
        "male1":   "fa-IR-FaridNeural",        # Deep, articulate Persian male (Recommended)
        "female2": "fa-IR-DilaraNeural",
        "male2":   "fa-IR-FaridNeural",
    },
}

# ---------------------------------------------------------------------------
# SPEAKERS CONFIGURATION
#
# Configure each tag ('a', 'b', 'c', 'd', ...) used in LESSON_DATA.
#
# Parameters:
#   language : "dutch" | "english" | "german" | "persian"
#   voice    : "male1" | "male2" | "female1" | "female2" (or exact voice name)
#   repeats  : how many times this segment is repeated (e.g. 1, 2, 3)
#   speed    : playback speed multiplier (e.g. 0.85, 0.95, 1.0)
# ---------------------------------------------------------------------------

SPEAKERS = {
    "a": {
        "language": "dutch",
        "voice":    "male1",   # Edge-TTS Dutch Male (Maarten)
        "repeats":  1,
        "speed":    0.95,
    },
    "b": {
        "language": "dutch",
        "voice":    "male1",   # Edge-TTS Dutch Male (Maarten)
        "repeats":  2,         # Repeated twice for shadowing practice
        "speed":    0.95,
    },
    "d": {
        "language": "dutch",
        "voice":    "female1", # Edge-TTS Dutch Female (Fenna)
        "repeats":  2,         # Repeated twice for shadowing practice
        "speed":    0.95,
    },
    "c": {
        "language": "persian",
        "voice":    "female1", # Edge-TTS Persian Female (Dilara)
        "repeats":  1,
        "speed":    1.00,
    },
}


# ===========================================================================
# LESSON DATA (Unified Format & AI Prompt)
# ===========================================================================
#
# ---------------------------------------------------------------------------
# AI PROMPT:
# Copy and paste the prompt below into any AI (ChatGPT, Claude, Gemini, etc.)
# along with your vocabulary, notes, or dialogues to automatically format them:
# ---------------------------------------------------------------------------
#
# === COPY FROM HERE ===
# You are an assistant formatting language data for an audio Shadowing app.
# Convert the provided vocabulary/sentences into the following tagged format:
#
# Tag Architecture:
# - 'a:' -> Dutch word, phrase, or Speaker 1 (Dutch / nl-NL)
# - 'b:' -> Dutch example sentence, practice sentence, or Speaker 2 (Dutch / nl-NL)
# - 'c:' -> Persian meaning, explanation, or translation (Persian / fa-IR)
# - Additional tags ('d:', 'e:', etc.) can also be used if defined in SPEAKERS.
# - Multiple tags can be chained on a single line (e.g. a: ... b: ... b: ... c: ...).
#
# Output Constraints:
# 1. Output ONLY plain text lines without any markdown formatting (* or **).
# 2. Do NOT add line numbers (1., 2.), bullet points, or quotes.
# 3. Include natural punctuation (. , ? !) so TTS engines pause appropriately.
#
# Example Output:
# a: uitstekend b: Het gaat uitstekend met mij. c: عالی
# a: fantastisch b: Wij hebben een fantastisch weekend gehad. c: فوق‌العاده
# a: niet zo goed b: Het gaat vandaag niet zo goed met hem. c: نه چندان خوب
# a: Heb je zin om b: Heb je zin om koffie te drinken? c: تمایل داری به
#
# Content to convert:
# [PASTE YOUR RAW VOCABULARY OR DIALOGUE HERE]
# === COPY END ===
# ---------------------------------------------------------------------------

LESSON_DATA = """
b: Ik wil op vakantie! a: een paar dagen naar Parijs gaan d: Zullen we een paar dagen naar Parijs gaan?
b: Dit is een leuk café! a: hier iets drinken d: Zullen we hier iets drinken?
b: Waar zijn Bart en Astrid? a: in de kantine kijken d: Zal ik in de kantine kijken? / Zullen we in de kantine kijken?
b: Ik wil afrekenen. a: de ober roepen d: Zal ik de ober roepen?
b: Wat zeg je? Wat is je naam? a: mijn naam spellen d: Zal ik mijn naam spellen?
b: Hè Hans, lang niet gezien! a: afspraak maken d: Zullen we een afspraak maken?
b: Wat eten we? a: spaghetti maken d: Zullen we spaghetti maken?
b: Edit is jarig. a: een boek geven d: Zullen we een boek geven? / Zal ik een boek geven?
""".strip()


# ===========================================================================
# Parser & Audio Helpers
# ===========================================================================

def parse_lesson_lines(raw_text: str) -> list[list[tuple[str, str]]]:
    """
    Parse unified lesson lines into lists of (speaker_tag, text) segments.
    Example line:
      'a: uitstekend b: ik ben heel blij b: het gaat uitstekend c: عالی'
    Becomes:
      [('a', 'uitstekend'), ('b', 'ik ben heel blij'), ('b', 'het gaat uitstekend'), ('c', 'عالی')]
    """
    parsed_rows = []
    pattern = re.compile(r'(?:^|\s+)([a-zA-Z0-9_]+):\s*')

    for line_idx, raw_line in enumerate(raw_text.strip().splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        matches = list(pattern.finditer(line))
        if not matches:
            continue

        segments: list[tuple[str, str]] = []
        for i, m in enumerate(matches):
            tag = m.group(1).lower()
            start_pos = m.end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(line)
            segment_text = line[start_pos:end_pos].strip()
            if segment_text:
                segments.append((tag, segment_text))

        if segments:
            parsed_rows.append(segments)

    return parsed_rows


def resolve_speaker(tag: str) -> tuple[str, str, int, float]:
    """Return (language, voice_name, repeats, speed) for a given speaker tag."""
    if tag not in SPEAKERS:
        raise ValueError(
            f"Speaker tag '{tag}' not found in SPEAKERS config. Configured tags: {list(SPEAKERS.keys())}"
        )

    cfg = SPEAKERS[tag]
    if isinstance(cfg, (list, tuple)):
        lang = str(cfg[0]).lower()
        v_key = str(cfg[1])
        repeats = int(cfg[2])
        speed = float(cfg[3]) if len(cfg) > 3 else 1.0
    elif isinstance(cfg, dict):
        lang = str(cfg.get("language", "dutch")).lower()
        v_key = str(cfg.get("voice", "male1"))
        repeats = int(cfg.get("repeats", 1))
        speed = float(cfg.get("speed", 1.0))
    else:
        raise ValueError(f"Invalid configuration format for speaker '{tag}': {cfg}")

    # Resolve preset name to exact TTS voice name
    if lang in VOICE_PRESETS and v_key in VOICE_PRESETS[lang]:
        voice_name = VOICE_PRESETS[lang][v_key]
    else:
        voice_name = v_key

    return lang, voice_name, repeats, speed


def parse_speed_to_float(speed: float | int | str = 1.0) -> float:
    """Convert speed input (e.g. 0.85, '0.85x', '-15%') to float multiplier."""
    if isinstance(speed, str):
        s = speed.strip().lower()
        if s.endswith('%'):
            val = float(s[:-1])
            return round(1.0 + (val / 100.0), 2)
        if s.endswith('x'):
            s = s[:-1]
        try:
            return round(float(s), 2)
        except ValueError:
            raise ValueError(f"Invalid speed format: '{speed}'.")
    return round(float(speed), 2)


def parse_speed_to_rate_str(speed: float | int | str = 1.0) -> str:
    """Convert speed input to edge-tts rate string (e.g. '-15%', '+10%')."""
    val = parse_speed_to_float(speed)
    pct = round((val - 1.0) * 100)
    return f"{pct:+d}%"


async def make_audio(
    text: str,
    voice: str,
    filepath: Path,
    speed: float | int | str = 1.0,
    max_retries: int = 3,
) -> None:
    """Synthesize text to speech using Microsoft Edge-TTS with retry mechanism."""
    rate_str = parse_speed_to_rate_str(speed)

    for attempt in range(1, max_retries + 1):
        try:
            await edge_tts.Communicate(text, voice, rate=rate_str).save(str(filepath))
            return
        except Exception as e:
            if attempt == max_retries:
                raise e
            wait_time = attempt * 2
            print(f"    [Warning] Edge-TTS attempt {attempt} failed ({e}). Retrying in {wait_time}s...")
            await asyncio.sleep(wait_time)


def adaptive_silence(segment: AudioSegment) -> AudioSegment:
    """Return silence whose duration scales with the segment's length."""
    ms = max(MIN_SILENCE_MS, int(len(segment) * SILENCE_RATIO))
    return AudioSegment.silent(duration=ms)


def normalize_and_export(audio: AudioSegment, path: Path) -> None:
    """Normalize audio settings and export as MP3."""
    if path.exists():
        path.unlink()
    audio = audio.set_frame_rate(OUTPUT_SAMPLE_RATE).set_channels(OUTPUT_CHANNELS)
    audio.export(str(path), format="mp3", bitrate=OUTPUT_BITRATE)


def clean_previous_outputs(directory: Path) -> None:
    """Clean up previously generated chunk files, full_lesson_edge.mp3, and temporary cache at startup."""
    if not directory.exists():
        return
    removed_count = 0

    # Clean previous full_lesson_edge or old full_lesson files
    for target in [directory / "full_lesson_edge.mp3", directory / "full_lesson.mp3"]:
        if target.exists():
            try:
                target.unlink()
                removed_count += 1
            except Exception:
                pass

    # Clean intermediate row files (001.mp3, 002.mp3, etc.)
    for f in directory.glob("[0-9][0-9][0-9].mp3"):
        try:
            f.unlink()
            removed_count += 1
        except Exception:
            pass

    for f in directory.glob("*.wav"):
        try:
            f.unlink()
            removed_count += 1
        except Exception:
            pass

    for sub in [directory / "_edge_tmp", directory / "_tmp", directory / "_tmp_chunks"]:
        if sub.exists():
            try:
                shutil.rmtree(sub)
                removed_count += 1
            except Exception:
                pass

    if removed_count > 0:
        print(f"[Startup] Cleaned up {removed_count} previously generated file(s)/folder(s).")


# ===========================================================================
# Lesson Builder
# ===========================================================================

async def build_lesson() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Clean up old files from previous runs
    clean_previous_outputs(OUTPUT_DIR)

    tmp_dir = OUTPUT_DIR / "_edge_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # 2. Parse input data
    rows = parse_lesson_lines(LESSON_DATA)
    if not rows:
        print("[ERROR] LESSON_DATA is empty or no valid lines were found.")
        return

    print("=" * 65)
    print("      Language Shadowing App (Unified Microsoft Edge-TTS Neural)")
    print("=" * 65)
    print("Configured Speakers:")
    for tag, cfg in SPEAKERS.items():
        lang, voice, repeats, speed = resolve_speaker(tag)
        print(f"  [{tag}] -> {lang.title():7s} | {voice} (×{repeats}, speed={speed}x) [Edge-TTS]")

    print(f"\nTotal lesson units to process: {len(rows)}")
    print("=" * 65)

    all_segments: list[AudioSegment] = []
    generated_row_files: list[Path] = []
    global_cache: dict[tuple[str, str, float], AudioSegment] = {}

    start_time = time.time()

    for row_idx, segments in enumerate(rows, start=1):
        first_text = segments[0][1] if segments else f"row {row_idx}"
        preview = (first_text[:35] + "...") if len(first_text) > 35 else first_text
        print(f"\nRow {row_idx}/{len(rows)}: {preview}")

        row_audio = AudioSegment.empty()

        for seg_idx, (tag, text) in enumerate(segments, start=1):
            lang, voice, repeats, speed = resolve_speaker(tag)
            speed_val = parse_speed_to_float(speed)

            print(f"  [{tag}] {lang} (Edge-TTS) ×{repeats} (speed={speed_val}x): {text}")

            cache_key = (text, voice, speed_val)
            if cache_key in global_cache:
                seg = global_cache[cache_key]
            else:
                speed_tag = f"_{int(speed_val * 100)}" if speed_val != 1.0 else ""
                clean_name = "".join(c if c.isalnum() else "_" for c in text)[:20]
                chunk_file = tmp_dir / f"r{row_idx:03d}_s{seg_idx}_{tag}_{clean_name}{speed_tag}.mp3"

                if not (chunk_file.exists() and chunk_file.stat().st_size > 0):
                    await make_audio(text, voice, chunk_file, speed=speed_val)
                    await asyncio.sleep(0.1)
                seg = AudioSegment.from_mp3(str(chunk_file))
                global_cache[cache_key] = seg

            pause = adaptive_silence(seg)
            for _ in range(repeats):
                row_audio += seg + pause

        all_segments.append(row_audio)

        out_path = OUTPUT_DIR / f"{row_idx:03d}.mp3"
        normalize_and_export(row_audio, out_path)
        generated_row_files.append(out_path)
        print(f"  -> Saved row: {out_path.name} ({out_path.stat().st_size // 1024} KB)")

    # 3. Export combined full lesson MP3
    print("\n" + "=" * 65)
    print("Building full combined lesson file...")
    full_lesson = sum(all_segments, AudioSegment.empty())

    full_path = OUTPUT_DIR / "full_lesson_edge.mp3"
    normalize_and_export(full_lesson, full_path)
    total_time = time.time() - start_time
    total_duration_sec = len(full_lesson) / 1000.0

    print("=" * 65)
    print(f"[SUCCESS] Full lesson exported in {total_time:.1f}s!")
    print(f"  Output path: {full_path.resolve()}")
    print(f"  Duration   : {total_duration_sec:.1f}s ({total_duration_sec / 60:.1f} mins)")
    print("=" * 65)

    # 4. Cleanup chunk files if enabled
    if CLEANUP_CHUNK_FILES:
        print("\n[Cleanup] Cleaning up individual chunk files...")
        cleaned_count = 0
        for f in generated_row_files:
            try:
                if f.exists():
                    f.unlink()
                    cleaned_count += 1
            except Exception:
                pass
        if tmp_dir.exists():
            try:
                shutil.rmtree(tmp_dir)
            except Exception:
                pass
        print(f"[Cleanup] Removed {cleaned_count} row chunk files and temporary cache.")
        print(f"[Cleanup] Clean directory: only '{full_path.name}' remains.")

    print("\nAll tasks completed successfully!")


if __name__ == "__main__":
    asyncio.run(build_lesson())