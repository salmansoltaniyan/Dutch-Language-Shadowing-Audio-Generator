# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import base64
import os
import re
import shutil
import sys
import time
from pathlib import Path

import edge_tts
import requests
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

# API Key loading: reads directly from google_api_key.txt (in project root) or env var
API_KEY_FILE = BASE_DIR.parent / "google_api_key.txt"
GOOGLE_API_KEY = (
    API_KEY_FILE.read_text(encoding="utf-8").strip()
    if API_KEY_FILE.exists()
    else os.getenv("GOOGLE_API_KEY", "")
)

# Adaptive silence: pause after each play = segment_duration × SILENCE_RATIO
# This is the default; any speaker can override it with its own 'silence_ratio' in SPEAKERS.
SILENCE_RATIO  = 1.6
MIN_SILENCE_MS = 1000   # minimum pause in milliseconds

# Final MP3 output settings (normalized for universal player compatibility)
OUTPUT_SAMPLE_RATE = 44100   # Hz (standard CD quality)
OUTPUT_CHANNELS    = 2       # 1=mono, 2=stereo
OUTPUT_BITRATE     = "192k"  # High quality MP3 bitrate

# Final lesson file name. A date-time stamp is appended on every run
# (e.g. 'full_lesson_google_2026-10-31_14-05-12.mp3'), so previous lessons are never overwritten.
OUTPUT_NAME = "full_lesson_google"

# Clean up individual chunk/row files (001.mp3, 002.mp3, ...) and temp cache at the end.
# True  = Keep ONLY the complete final lesson file, delete all chunks.
# False = Keep all individual row files (001.mp3, 002.mp3, ...) for separate playback.
CLEANUP_CHUNK_FILES = True


# ===========================================================================
# VOICE PRESETS & SPEAKER CONFIGURATION
# ===========================================================================
#
# Supported Languages:
#   - "dutch"   : Powered by Google Cloud Chirp 3: HD
#   - "english" : Powered by Google Cloud Chirp 3: HD
#   - "german"  : Powered by Google Cloud Chirp 3: HD
#   - "persian" : Powered by Microsoft Edge-TTS Neural
#
# Available voice presets for each language:
#   "male1", "male2", "female1", "female2" (or use any exact voice name directly)
# ---------------------------------------------------------------------------

VOICE_PRESETS = {
    "dutch": {
        "male1":   "nl-NL-Chirp3-HD-Fenrir",   # Deep, warm, highly natural (Recommended)
        "male2":   "nl-NL-Chirp3-HD-Algenib",  # Clear, friendly, conversational
        "female1": "nl-NL-Chirp3-HD-Aoede",    # Clear, articulate, educational (Recommended)
        "female2": "nl-NL-Chirp3-HD-Gacrux",   # Warm, gentle, conversational
    },
    "english": {
        "male1":   "en-US-Chirp3-HD-Fenrir",
        "male2":   "en-US-Chirp3-HD-Algenib",
        "female1": "en-US-Chirp3-HD-Aoede",
        "female2": "en-US-Chirp3-HD-Gacrux",
    },
    "german": {
        "male1":   "de-DE-Chirp3-HD-Fenrir",
        "male2":   "de-DE-Chirp3-HD-Algenib",
        "female1": "de-DE-Chirp3-HD-Aoede",
        "female2": "de-DE-Chirp3-HD-Gacrux",
    },
    "persian": {
        "female1": "fa-IR-DilaraNeural",       # Soft, clear, native Persian
        "male1":   "fa-IR-FaridNeural",        # Deep, articulate Persian
        "female2": "fa-IR-DilaraNeural",
        "male2":   "fa-IR-FaridNeural",
    },
}

# ---------------------------------------------------------------------------
# SPEAKERS CONFIGURATION
#
# Configure each tag ('a', 'b', 'c', ...) used in LESSON_DATA.
#
# Parameters:
#   language : "dutch" | "english" | "german" | "persian"
#   voice    : "male1" | "male2" | "female1" | "female2" (or exact voice name)
#   repeats  : how many times this segment is repeated (e.g. 1, 2, 3)
#   speed    : playback speed multiplier (e.g. 0.85, 0.95, 1.0)
#   silence_ratio : (optional) pause after this speaker = segment length × value;
#                   if omitted, the global SILENCE_RATIO is used
# ---------------------------------------------------------------------------

# SPEAKERS = {
#     "a": {
#         "language": "dutch",
#         "voice":    "male1",   # Google Chirp 3: HD Male (Fenrir)
#         "repeats":  1,
#         "speed":    0.95,
#     },
#     "b": {
#         "language": "dutch",
#         "voice":    "female1", # Google Chirp 3: HD Female (Aoede)
#         "repeats": 1,         # Repeated twice for shadowing practice
#         "speed":    0.95,
#     },
#     "c": {
#         "language": "dutch",
#         "voice":    "male2", # Google Chirp 3: HD Male (Algenib)
#         "repeats":  1,         # Repeated twice for shadowing practice
#         "speed":    0.95,
#     },
#     "d": {
#     "language": "dutch",
#     "voice":    "female2", # Google Chirp 3: HD Female (Aoede)
#     "repeats":  1,         # Repeated twice for shadowing practice
#     "speed":    0.95,
#     },
#     "e": {
#         "language": "persian",
#         "voice":    "female1", # Edge-TTS Persian Female (Dilara)
#         "repeats":  1,
#         "speed":    1.1,
#     },
#     "f": {
#     "language": "persian",
#     "voice":    "male1", # Edge-TTS Persian Male (Farid)
#     "repeats":  1,
#     "speed":    1.1,
#     },
#     "g": {
#     "language": "persian",
#     "voice":    "female2", # Edge-TTS Persian Female (Dilara)
#     "repeats":  1,
#     "speed":    1.1,
#     },
#     }
SPEAKERS = {
    "a": {"language": "dutch",   "voice": "male1",   "repeats": 1, "speed": 0.95, "silence_ratio": 1.6},
    "b": {"language": "dutch",   "voice": "female1", "repeats": 1, "speed": 0.95, "silence_ratio": 1.0},
    "e": {"language": "persian", "voice": "female1", "repeats": 1, "speed": 1.1,  "silence_ratio": 0.3},
}
# ===========================================================================
# LESSON DATA (Unified Format)
# ===========================================================================
#
# Format:
# Prefix each phrase/sentence with a speaker label ('a:', 'b:', 'c:', etc.).
# Multiple phrases and speakers can appear in a single row or across lines.
#
# Examples:
#   1. Single row vocabulary + sentence + translation:
#      a: uitstekend b: Het gaat uitstekend met mij. c: عالی
#
#   2. Multiple phrases for the same speaker:
#      a: uitstekend b: ik ben heel blij b: het gaat uitstekend c: عالی
#
#   3. Dialogues across separate rows:
#      a: Heb je het artikel gelezen over echte Hollandse winterkost?
#      b: Ja in de studentenkeukens, wat maken ze deze week?
# ---------------------------------------------------------------------------

LESSON_DATA = """
# Hoofdstuk 9 — Perfectum met zijn (richting, gebeuren, zijn, worden, blijven, stoppen, beginnen)
a: Ik fiets naar huis. b: Ik ben naar huis gefietst. e: با دوچرخه به خانه رفتم.
a: Ik ga naar de makelaar. b: Ik ben naar de makelaar gegaan. e: پیش دلال املاک رفتم.
a: Dorien en Marianne gaan met de fiets naar huis. b: Dorien en Marianne zijn met de fiets naar huis gegaan. e: دورین و ماریان با دوچرخه به خانه رفتند.
a: We gaan met de fiets. b: We zijn met de fiets gegaan. e: با دوچرخه رفتیم.
a: Ga je zaterdag of zondag naar Amsterdam? b: Ben je zaterdag of zondag naar Amsterdam gegaan? e: شنبه یا یکشنبه به آمستردام رفتی؟
a: Hoe laat ga je naar huis? b: Hoe laat ben je gisteren naar huis gegaan? e: دیروز ساعت چند به خانه رفتی؟
a: Sebastian en ik gaan om elf uur naar de makelaar. b: Sebastian en ik zijn om elf uur naar de makelaar gegaan. e: من و سباستین ساعت یازده پیش دلال املاک رفتیم.
a: Gaan jullie met Simona naar de dokter? b: Zijn jullie met Simona naar de dokter gegaan? e: شما با سیمونا پیش دکتر رفتید؟
a: Wat gebeurt er? b: Wat is er gebeurd? e: چه اتفاقی افتاده؟
a: Vanavond ben ik bij de voetbalvereniging. b: Gisteravond ben ik naar de voetbalvereniging geweest. e: دیشب به باشگاه فوتبال رفته بودم.
a: Julia en Martin zijn in België op vakantie. b: Julia en Martin zijn in België op vakantie geweest. e: جولیا و مارتین در بلژیک در تعطیلات بوده‌اند.
a: Waar ben je op vakantie? b: Waar ben je dit jaar op vakantie geweest? e: امسال کجا به تعطیلات رفتی؟
a: Joana is op vakantie in Portugal. b: Joana is dit jaar op vakantie in Portugal geweest. e: یوانا امسال در پرتغال در تعطیلات بوده است.
a: Ik ben in het weekend ziek. b: Ik ben in het weekend ziek geweest. e: آخر هفته مریض بودم.
a: Word je vandaag eenentwintig? b: Ben je gisteren eenentwintig geworden? e: دیروز بیست‌ویک ساله شدی؟
a: Brian wordt vandaag zesendertig. b: Brian is gisteren zesendertig geworden. e: برایان دیروز سی‌وشش ساله شد.
a: Hij blijft tot tweeëntwintig uur. b: Hij is tot tweeëntwintig uur gebleven. e: او تا ساعت بیست‌ودو ماند.
a: Mijn vriend blijft vandaag thuis. b: Mijn vriend is gisteren thuis gebleven. e: دوستم دیروز در خانه ماند.
a: Ik blijf in het weekend thuis. b: Ik ben in het weekend thuis gebleven. e: آخر هفته در خانه ماندم.
a: Ze stopt met de cursus. b: Ze is met de cursus gestopt. e: او دوره را رها کرد.
a: Stop je met de cursus Nederlands? b: Ben je met de cursus Nederlands gestopt? e: دوره‌ی هلندی را رها کردی؟
a: Veronika en Victor stoppen met de cursus. b: Veronika en Victor zijn met de cursus gestopt. e: ورونیکا و ویکتور دوره را رها کردند.
a: We beginnen om negen uur met de cursus. b: We zijn om negen uur met de cursus begonnen. e: ساعت نه دوره را شروع کردیم.
a: We beginnen vandaag met les negen. b: We zijn vandaag met les negen begonnen. e: امروز درس نه را شروع کردیم.
a: Wanneer begint de cursus? b: Wanneer is de cursus begonnen? e: دوره کی شروع شد؟
a: Hoe laat beginnen jullie met de les? b: Hoe laat zijn jullie met de les begonnen? e: ساعت چند درس را شروع کردید؟
a: Wanneer begint dat? b: Wanneer is dat begonnen? e: کی شروع شد؟
a: Wanneer kom je naar Nederland? b: Wanneer ben je naar Nederland gekomen? e: کی به هلند آمدی؟
a: Hoe komt Karen naar de les? b: Hoe is Karen naar de les gekomen? e: کارن چطور به کلاس آمد؟
a: Komt u met de bus? b: Bent u met de bus gekomen? e: با اتوبوس آمده‌اید؟
a: Wij komen naar Nederland. b: Wij zijn een halfjaar geleden naar Nederland gekomen. e: ما شش ماه پیش به هلند آمدیم.

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


def speaker_silence_ratio(tag: str) -> float:
    """Return the speaker's own 'silence_ratio', or the global SILENCE_RATIO if not set."""
    cfg = SPEAKERS.get(tag)
    if isinstance(cfg, dict) and "silence_ratio" in cfg:
        return float(cfg["silence_ratio"])
    return SILENCE_RATIO


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


# ===========================================================================
# TTS Engines (Google Cloud Chirp 3: HD + Microsoft Edge-TTS)
# ===========================================================================

def synthesize_google_tts_sync(text: str, voice_name: str, speed_float: float, filepath: Path) -> None:
    """Synthesize speech using Google Cloud Text-to-Speech REST API."""
    if not GOOGLE_API_KEY:
        raise ValueError(
            "Google API key not found! Please paste your key into 'google_api_key.txt' in the project root."
        )

    # Derive BCP-47 language code from voice name (e.g. 'nl-NL', 'en-US', 'de-DE')
    parts = voice_name.split("-")
    lang_code = f"{parts[0]}-{parts[1]}" if len(parts) >= 2 else "nl-NL"

    url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={GOOGLE_API_KEY}"
    payload = {
        "input": {"text": text},
        "voice": {
            "languageCode": lang_code,
            "name": voice_name,
        },
        "audioConfig": {
            "audioEncoding": "MP3",
            "speakingRate": speed_float,
            "sampleRateHertz": OUTPUT_SAMPLE_RATE,
        },
    }

    resp = requests.post(url, json=payload, timeout=25)
    if resp.status_code != 200:
        raise RuntimeError(f"Google TTS API Error [{resp.status_code}]: {resp.text}")

    data = resp.json()
    audio_content = data.get("audioContent")
    if not audio_content:
        raise ValueError(f"No audioContent in Google TTS response: {resp.text}")

    audio_bytes = base64.b64decode(audio_content)
    filepath.write_bytes(audio_bytes)


async def make_audio(
    text: str,
    language: str,
    voice: str,
    filepath: Path,
    speed: float = 1.0,
    max_retries: int = 3,
) -> None:
    """
    Unified speech synthesizer:
    - If language is Persian (or voice starts with 'fa-'): uses Microsoft Edge-TTS.
    - If language is Dutch, English, German (or voice starts with Google prefix): uses Google Cloud Chirp 3: HD.
    """
    speed_float = parse_speed_to_float(speed)
    rate_str    = parse_speed_to_rate_str(speed)
    is_persian  = language == "persian" or voice.startswith("fa-")

    for attempt in range(1, max_retries + 1):
        try:
            if is_persian:
                await edge_tts.Communicate(text, voice, rate=rate_str).save(str(filepath))
            else:
                await asyncio.to_thread(synthesize_google_tts_sync, text, voice, speed_float, filepath)
            return
        except Exception as e:
            if attempt == max_retries:
                raise e
            wait_time = attempt * 2
            print(f"    [Warning] TTS attempt {attempt} failed ({e}). Retrying in {wait_time}s...")
            await asyncio.sleep(wait_time)


def adaptive_silence(segment: AudioSegment, ratio: float) -> AudioSegment:
    """Return silence whose duration scales with the segment's length."""
    ms = max(MIN_SILENCE_MS, int(len(segment) * ratio))
    return AudioSegment.silent(duration=ms)


def normalize_and_export(audio: AudioSegment, path: Path) -> None:
    """Normalize audio settings and export as MP3."""
    if path.exists():
        path.unlink()
    audio = audio.set_frame_rate(OUTPUT_SAMPLE_RATE).set_channels(OUTPUT_CHANNELS)
    audio.export(str(path), format="mp3", bitrate=OUTPUT_BITRATE)


def unique_output_path(directory: Path, name: str) -> Path:
    """Return '<name>_<date-time>.mp3' in directory, never an existing file."""
    stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    path = directory / f"{name}_{stamp}.mp3"
    counter = 2
    while path.exists():
        path = directory / f"{name}_{stamp}_{counter}.mp3"
        counter += 1
    return path


def clean_previous_outputs(directory: Path) -> None:
    """Clean up leftover row files (001.mp3, ...) and temporary cache at startup.
    Final lesson files are kept."""
    if not directory.exists():
        return
    removed_count = 0
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
    for sub in [directory / "_google_tmp", directory / "_tmp", directory / "_google_cache", directory / "_gemini_tmp"]:
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

    tmp_dir = OUTPUT_DIR / "_google_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # 2. Check API key
    if not GOOGLE_API_KEY:
        print("\n[ERROR] Google API key was not found!")
        print("Please paste your API key into 'google_api_key.txt' in the project root folder.")
        return

    # 3. Parse input data
    rows = parse_lesson_lines(LESSON_DATA)
    if not rows:
        print("[ERROR] LESSON_DATA is empty or no valid lines were found.")
        return

    print("=" * 65)
    print("      Language Shadowing App (Unified Google Chirp 3: HD + Edge-TTS)")
    print("=" * 65)
    print("Configured Speakers:")
    for tag, cfg in SPEAKERS.items():
        lang, voice, repeats, speed = resolve_speaker(tag)
        provider = "Edge-TTS" if lang == "persian" else "Google Chirp"
        print(f"  [{tag}] -> {lang.title():7s} | {voice} (×{repeats}, speed={speed}x, silence={speaker_silence_ratio(tag)}) [{provider}]")

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
            provider  = "Edge" if lang == "persian" else "Google"

            print(f"  [{tag}] {lang} ({provider}) ×{repeats} (speed={speed_val}x): {text}")

            cache_key = (text, voice, speed_val)
            if cache_key in global_cache:
                seg = global_cache[cache_key]
            else:
                speed_tag = f"_{int(speed_val * 100)}" if speed_val != 1.0 else ""
                clean_name = "".join(c if c.isalnum() else "_" for c in text)[:20]
                chunk_file = tmp_dir / f"r{row_idx:03d}_s{seg_idx}_{tag}_{clean_name}{speed_tag}.mp3"

                if not (chunk_file.exists() and chunk_file.stat().st_size > 0):
                    await make_audio(text, lang, voice, chunk_file, speed=speed_val)
                    await asyncio.sleep(0.15)
                seg = AudioSegment.from_mp3(str(chunk_file))
                global_cache[cache_key] = seg

            pause = adaptive_silence(seg, speaker_silence_ratio(tag))
            for _ in range(repeats):
                row_audio += seg + pause

        all_segments.append(row_audio)

        out_path = OUTPUT_DIR / f"{row_idx:03d}.mp3"
        normalize_and_export(row_audio, out_path)
        generated_row_files.append(out_path)
        print(f"  -> Saved row: {out_path.name} ({out_path.stat().st_size // 1024} KB)")

    # 4. Export combined full lesson MP3
    print("\n" + "=" * 65)
    print("Building full combined lesson file...")
    full_lesson = sum(all_segments, AudioSegment.empty())

    full_path = unique_output_path(OUTPUT_DIR, OUTPUT_NAME)
    normalize_and_export(full_lesson, full_path)
    total_time = time.time() - start_time
    total_duration_sec = len(full_lesson) / 1000.0

    print("=" * 65)
    print(f"[SUCCESS] Full lesson exported in {total_time:.1f}s!")
    print(f"  Output path: {full_path.resolve()}")
    print(f"  Duration   : {total_duration_sec:.1f}s ({total_duration_sec / 60:.1f} mins)")
    print("=" * 65)

    # 5. Cleanup chunk files if enabled
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
        print(f"[Cleanup] Only final lesson files remain (new: '{full_path.name}').")

    print("\nAll tasks completed successfully!")


if __name__ == "__main__":
    asyncio.run(build_lesson())
