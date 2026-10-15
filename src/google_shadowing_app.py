from __future__ import annotations

import asyncio
import base64
import csv
import io
import os
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
# SHARED CONFIGURATION (Applies to BOTH Normal Mode and Dialog Mode)
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
SILENCE_RATIO  = 0.9
MIN_SILENCE_MS = 1000   # minimum pause in milliseconds

# Final MP3 output settings (normalized for universal player compatibility)
OUTPUT_SAMPLE_RATE = 44100   # Hz (standard CD quality)
OUTPUT_CHANNELS    = 2       # 1=mono, 2=stereo
OUTPUT_BITRATE     = "192k"  # High quality MP3 bitrate

# Choose which mode to run (True = Dialog Mode, False = Normal Mode)
DIALOG_MODE = False

# Clean up individual chunk/row files (001.mp3, 002.mp3, ...) and temp cache at the end.
# True  = Keep ONLY the complete final lesson file ('full_lesson_google.mp3'), delete all chunks.
# False = Keep all individual row files (001.mp3, 002.mp3, ...) for separate playback.
CLEANUP_CHUNK_FILES = True



# ===========================================================================
# VOICE OPTIONS GUIDE (راهنمای انتخاب صداهای هلندی و فارسی)
# ===========================================================================
# 
# 1. DUTCH VOICES (Google Cloud Text-to-Speech):
# ---------------------------------------------------------------------------
# [A] Chirp 3: HD (Google's latest High-Definition Generative AI voices):
#     - Male:
#         "nl-NL-Chirp3-HD-Fenrir"       (Deep, warm, highly natural - Recommended)
#         "nl-NL-Chirp3-HD-Algenib"      (Clear, friendly, conversational)
#         "nl-NL-Chirp3-HD-Achird"       (Neutral, balanced tone)
#         "nl-NL-Chirp3-HD-Enceladus"    (Firm, professional)
#         "nl-NL-Chirp3-HD-Orus"         (Young adult tone)
#     - Female:
#         "nl-NL-Chirp3-HD-Aoede"        (Clear, bright, articulate - Recommended)
#         "nl-NL-Chirp3-HD-Gacrux"       (Warm, gentle, natural cadence)
#         "nl-NL-Chirp3-HD-Despina"      (Expressive, conversational)
#         "nl-NL-Chirp3-HD-Zephyr"       (Modern, energetic)
#         "nl-NL-Chirp3-HD-Leda"         (Soft, calm)
#
# [B] WaveNet (DeepMind classical neural voices):
#     - Male:   "nl-NL-Wavenet-G"
#     - Female: "nl-NL-Wavenet-F"
#
# [C] Standard (Basic synthesized voices):
#     - Male:   "nl-NL-Standard-G"
#     - Female: "nl-NL-Standard-F"
#
# [D] Belgian Dutch (Flemish / nl-BE) Options:
#     - Male:   "nl-BE-Chirp3-HD-Achird", "nl-BE-Wavenet-D"
#     - Female: "nl-BE-Chirp3-HD-Aoede",  "nl-BE-Wavenet-C"
#
# 2. PERSIAN VOICES (Microsoft Edge-TTS Neural):
# ---------------------------------------------------------------------------
# Note: Google Cloud TTS does not provide standard Persian (fa-IR) voices.
# We seamlessly use Microsoft's ultra-natural Neural voices for Persian:
#     - Female: "fa-IR-DilaraNeural"     (Very natural, calm, pleasant)
#     - Male:   "fa-IR-FaridNeural"      (Deep, clear, native Persian)
# ===========================================================================

# Available TTS voices mapping: (language, gender) -> voice_name
VOICES = {
    ("dutch",   "male"):   "nl-NL-Chirp3-HD-Fenrir",  # Google Chirp 3: HD Male
    ("dutch",   "female"): "nl-NL-Chirp3-HD-Aoede",   # Google Chirp 3: HD Female
    ("persian", "male"):   "fa-IR-FaridNeural",       # Edge-TTS Neural Male
    ("persian", "female"): "fa-IR-DilaraNeural",      # Edge-TTS Neural Female
}


# ===========================================================================
# NORMAL MODE CONFIGURATION
# ===========================================================================

# ---------------------------------------------------------------------------
# CSV format:
# 1. First row (Header) must strictly be: dutch,dutch,persian
# 2. Column 1: The Dutch word or phrase (include article 'de' or 'het' for nouns).
# 3. Column 2: A natural, practical example sentence in Dutch.
# 4. Column 3: Natural Persian translation of word/sentence.
# ---------------------------------------------------------------------------
CSV_DATA = """
dutch,dutch,persian
uitstekend,Ik ben heel blij; het gaat uitstekend.,عالی
fantastisch,De zon schijnt en het feest is fantastisch.,فوق‌العاده
niet zo goed,Ik ben een beetje ziek; het gaat niet zo goed.,نه چندان خوب
Heb je zin om,Heb je honger? Heb je zin om pizza te eten?,میلی داری به
Ga je mee,Ik ga naar de stad; ga je mee?,همراه من می‌آیی
Goed idee,Ja leuk! Dat is een goed idee.,ایده خوب
Dat vind ik niet leuk,Nee stop! Dat vind ik niet leuk.,دوست ندارم
het lokaal,De leraar staat voor de klas in het lokaal.,کلاس
roepen,Hij staat ver weg; ik moet hard roepen.,صدا زدن
spellen,Ik weet niet hoe je dat schrijft; kun je het spellen?,هجی کردن
geven,Morgen is jouw feest en ik wil een cadeau geven.,دادن
de ouders,Mijn vader en moeder zijn mijn ouders.,والدین
de activiteit,Zwemmen en fietsen; welke activiteit vind je leuk?,فعالیت
het moment,Ik kom zo; wacht een moment.,لحظه
nemen,Wil je thee drinken of wil je koffie nemen?,برداشتن
de collega,Wij werken samen in één kantoor; hij is mijn collega.,همکار
automatisch,Je hoeft niet te drukken; de deur gaat automatisch.,خودکار
de diensten,De bank helpt mensen met geld en andere diensten.,خدمات
het Talencentrum,Ik wil Nederlands leren; ik ga naar het Talencentrum.,مرکز زبان
bezoeken,Opa is ziek; wij gaan hem bezoeken.,دیدار کردن
de vraag,Ik weet het antwoord niet; ik stel een vraag.,سؤال
beantwoord,Ik stuur een e-mail en hij heeft beantwoord.,پاسخ داده
raadplegen,Voor meer info moet je de website raadplegen.,مراجعه کردن
ons best doen,Het examen is moeilijk maar wij doen ons best.,تلاش کردن
spoedig,Niet wachten tot morgen; kom zo spoedig mogelijk.,سریع
het secretariaat,Voor jouw studentenkaart ga je naar het secretariaat.,دبیرخانه
de openingstijden,De winkel is open van 9 tot 5; dat zijn de openingstijden.,ساعات کاری
de werkdag,Zaterdag is weekend maar vandaag is een werkdag.,روز کاری
bereikbaar,Mijn telefoon is uit; ik ben niet bereikbaar.,در دسترس
wil je graag doen,Heb je vrije tijd? Wat wil je graag doen?,دوست داری انجام بدی
kom je samen mee,Ik ga niet alleen; kom je samen mee?,همراه من می‌آیی
""".strip()

# ---------------------------------------------------------------------------
# SEGMENT_ORDER — used in normal mode only (ignored in dialog mode).
#
# Each entry is a tuple with 3 or 4 elements:
#   (column_index, gender, repeats[, speed])
#
#   column_index : 1-based column position in the CSV (1, 2, 3, ...)
#   gender       : "male" or "female"
#   repeats      : how many times to play this segment
#   speed        : (Optional) speed multiplier. Default is 1.0 (normal).
#                  Examples: 0.8 (slower), 1.2 (faster), "0.85x", "-15%", etc.
# ---------------------------------------------------------------------------
SEGMENT_ORDER = [
    (1, "male",   1, 0.85),  # Dutch word, male voice, 1 repeat, 0.85x speed
    (2, "male",   2, 0.95),  # Dutch sentence, male voice, 2 repeats (shadowing), 0.95x
    (3, "female", 1, 1.00),  # Persian translation, female voice, 1 repeat, 1.0x speed
]


# ===========================================================================
# DIALOG MODE CONFIGURATION
# ===========================================================================

# How many times every dialog sentence is repeated
DIALOG_REPEATS = 1

# Voices mapped to speakers by row:
#   Speaker 'a' = Google Chirp3-HD Male (Fenrir)
#   Speaker 'b' = Google Chirp3-HD Female (Aoede)
#   Speaker 'c' = Google Chirp3-HD Male (Algenib)
DIALOG_VOICES = {
    "a": "nl-NL-Chirp3-HD-Fenrir",
    "b": "nl-NL-Chirp3-HD-Aoede",
    "c": "nl-NL-Chirp3-HD-Algenib",
}

# ---------------------------------------------------------------------------
# DIALOG_CSV_DATA — used only when DIALOG_MODE = True.
# ---------------------------------------------------------------------------
DIALOG_CSV_DATA = """
a: Heb je het artikel gelezen, over echte Hollandse winterkost?
b: Ja in de studentenkeukens, wat maken ze deze week?
a: Deze week maken ze, stamppot andijvie met spekjes.
b: Klinkt goed, wie is de kok van de avond?
a: Kok van de avond is Tim, een student aan de Hanzehogeschool.
b: Kookt hij alleen, of samen met zijn studiegenoten?
a: Hij kookt samen met Jorik en Willard, op zijn studentenkamer.
b: Houden ze allemaal, van deze warme stamppot?
a: Nee Jorik en Willard, houden niet zo van stamppot.
b: Wat eten zij dan, als hoofdgerecht vanavond?
a: Op hun borden ligt pasta, pasta van gisteren met rookworst.
b: Wat heb je precies nodig, voor dit stamppot recept?
a: Je hebt twee kilo aardappels, en vijfhonderd gram andijvie nodig.
b: Moet er ook vlees in, of is het vegetarisch?
a: Je gebruikt tweehonderdvijftig gram spekjes, en één rookworst.
b: En voor de puree, wat gebruiken we daarvoor?
a: Een beetje boter en melk, en wat peper en zout.
b: Oh we vergeten nog, de tomaten en de kaas.
a: Klopt driehonderd gram kaas, en driehonderd gram cherrytomaten.
b: Hoe begin je, met het maken van dit gerecht?
a: Eerst schil je de aardappels, en kook je ze in twintig minuten gaar.
b: Tim schilt voor de eerste keer, twee kilo aardappels in zijn leven!
a: Dat is inderdaad veel werk, intussen moet je de worst koken.
b: En de rest van de groenten, wat doen we daarmee?
a: Maak de andijvie schoon, en snijd de tomaten in stukjes.
b: Daarna bak je de spekjes, en stamp je de aardappels tot puree.
a: Roer de melk erdoor, en voeg de andijvie en spekjes toe.
b: Breng het op smaak, met zout en peper.
a: Morgen gaan Tim en Jorik, op studiereis naar Noorwegen.
b: Het regent daar veel, en het is daar erg koud.
a: Brr neem dan gauw nog een hap, van de warme stamppot!
b: Zeker weten, eet smakelijk allemaal!
""".strip()


# ===========================================================================
# CSV Parsers
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
        raise ValueError(f"Invalid header(s): {bad}. Headers must be 'dutch' or 'persian' only.")
    return headers, data_rows


def load_dialog_csv() -> list[tuple[str, list[str]]]:
    """Return list of (speaker_id, sentences) for dialog mode."""
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
            raise ValueError(f"Row must start with a speaker label like 'a:' or 'b:'. Got: '{first_cell}'")

        sentences = [c for c in clean_cells if c]
        speaker_rows.append((speaker_id, sentences))

    if not speaker_rows:
        raise ValueError("DIALOG_CSV_DATA is empty.")

    return speaker_rows


# ===========================================================================
# Speed / Rate Parsers
# ===========================================================================

def parse_speed_to_float(speed: float | int | str = 1.0) -> float:
    """Convert speed format (e.g. 0.8, '0.8x', '-20%') to float multiplier for Google TTS (e.g. 0.8)."""
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
    """Convert speed format to edge-tts rate string (e.g. '-20%', '+10%')."""
    val = parse_speed_to_float(speed)
    pct = round((val - 1.0) * 100)
    return f"{pct:+d}%"


# ===========================================================================
# TTS Synthesis Functions (Google Cloud & Edge-TTS)
# ===========================================================================

def synthesize_google_tts_sync(text: str, voice_name: str, speed_float: float, filepath: Path) -> None:
    """Synthesize speech using Google Cloud Text-to-Speech REST API."""
    if not GOOGLE_API_KEY:
        raise ValueError(
            "Google API key not found! Please paste your key into 'google_api_key.txt' in the project root."
        )

    # Determine language code from voice name prefix (e.g. "nl-BE" or "nl-NL")
    lang_code = "nl-BE" if voice_name.startswith("nl-BE") else "nl-NL"

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
    voice: str,
    filepath: Path,
    speed: float | int | str = 1.0,
    max_retries: int = 3,
) -> None:
    """
    Unified TTS synthesizer:
    - If voice is Google Cloud Dutch (starts with 'nl-'): calls Google Cloud TTS.
    - If voice is Persian or Edge-TTS (starts with 'fa-'): calls Microsoft Edge-TTS.
    """
    speed_float = parse_speed_to_float(speed)
    rate_str    = parse_speed_to_rate_str(speed)

    is_google = voice.startswith("nl-")

    for attempt in range(1, max_retries + 1):
        try:
            if is_google:
                # Run synchronous requests call in thread pool to keep asyncio responsive
                await asyncio.to_thread(synthesize_google_tts_sync, text, voice, speed_float, filepath)
            else:
                await edge_tts.Communicate(text, voice, rate=rate_str).save(str(filepath))
            return
        except Exception as e:
            if attempt == max_retries:
                raise e
            wait_time = attempt * 2
            print(f"    [Warning] TTS attempt {attempt} failed ({e}). Retrying in {wait_time}s...")
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


def validate_order(headers: list[str]) -> None:
    """Check that every SEGMENT_ORDER entry references a valid column."""
    for item in SEGMENT_ORDER:
        if len(item) == 3:
            col_1based, gender, repeats = item
            speed = 1.0
        elif len(item) == 4:
            col_1based, gender, repeats, speed = item
        else:
            raise ValueError(
                f"Each SEGMENT_ORDER entry must have 3 or 4 elements: (col, gender, repeats[, speed]). Got: {item}"
            )

        idx = col_1based - 1
        if idx < 0 or idx >= len(headers):
            raise ValueError(
                f"SEGMENT_ORDER references col{col_1based}, but CSV only has {len(headers)} column(s)."
            )
        lang = headers[idx]
        if gender not in ("male", "female"):
            raise ValueError(f"Gender must be 'male' or 'female', got '{gender}'.")
        if (lang, gender) not in VOICES:
            raise ValueError(f"No voice configured for lang='{lang}', gender='{gender}'.")
        parse_speed_to_float(speed)


# ===========================================================================
# Normal Mode Builder
# ===========================================================================

async def build_row_normal(
    row_index: int,
    cells:     list[str],
    headers:   list[str],
    tmp_dir:   Path,
) -> AudioSegment:
    """Normal mode: synthesize audio per SEGMENT_ORDER with caching and adaptive pauses."""
    cache: dict[tuple[int, str, float], AudioSegment] = {}

    for item in SEGMENT_ORDER:
        col_1based = item[0]
        gender     = item[1]
        repeats    = item[2]
        speed      = item[3] if len(item) > 3 else 1.0
        speed_val  = parse_speed_to_float(speed)

        col_idx = col_1based - 1
        key     = (col_idx, gender, speed_val)
        if key in cache:
            continue

        lang  = headers[col_idx]
        text  = cells[col_idx].strip() if col_idx < len(cells) else ""
        voice = VOICES[(lang, gender)]

        speed_tag = f"_{int(speed_val * 100)}" if speed_val != 1.0 else ""
        path      = tmp_dir / f"row{row_index:03d}_col{col_1based}_{gender}{speed_tag}.mp3"

        provider = "Google" if voice.startswith("nl-") else "Edge"
        print(f"  [TTS - {provider}] col{col_1based} {lang} ({gender}, ×{repeats}, speed={speed_val}x): {text}")

        if not text:
            seg = AudioSegment.silent(duration=500)
        else:
            if not (path.exists() and path.stat().st_size > 0):
                await make_audio(text, voice, path, speed=speed_val)
                await asyncio.sleep(0.2)
            else:
                print(f"    [Cache] Using cached audio for row {row_index:03d} col {col_1based}")
            seg = AudioSegment.from_mp3(str(path))

        cache[key] = seg

    result = AudioSegment.empty()
    for item in SEGMENT_ORDER:
        col_1based = item[0]
        gender     = item[1]
        repeats    = item[2]
        speed      = item[3] if len(item) > 3 else 1.0
        speed_val  = parse_speed_to_float(speed)

        seg   = cache[(col_1based - 1, gender, speed_val)]
        pause = adaptive_silence(seg)
        for _ in range(repeats):
            result += seg + pause

    return result


# ===========================================================================
# Dialog Mode Builder
# ===========================================================================

async def build_dialog_turn(
    turn_index: int,
    speaker_id: str,
    text: str,
    tmp_dir: Path,
) -> AudioSegment:
    """Build audio for a single sentence in Dialog mode."""
    if speaker_id not in DIALOG_VOICES:
        raise ValueError(
            f"Speaker '{speaker_id}' not found in DIALOG_VOICES. Available: {list(DIALOG_VOICES.keys())}"
        )

    voice = DIALOG_VOICES[speaker_id]
    path  = tmp_dir / f"turn{turn_index:03d}_{speaker_id}.mp3"

    provider = "Google" if voice.startswith("nl-") else "Edge"
    print(f"  [TTS - {provider}] turn {turn_index:02d} | speaker '{speaker_id}' (×{DIALOG_REPEATS}): {text}")

    if not (path.exists() and path.stat().st_size > 0):
        await make_audio(text, voice, path)
        await asyncio.sleep(0.2)
    else:
        print(f"    [Cache] Using cached audio for turn {turn_index:02d}")

    seg   = AudioSegment.from_mp3(str(path))
    pause = adaptive_silence(seg)

    result = AudioSegment.empty()
    for _ in range(DIALOG_REPEATS):
        result += seg + pause

    return result


def clean_previous_outputs(directory: Path) -> None:
    """Clean up previously generated MP3/WAV files and temporary cache at startup."""
    if not directory.exists():
        return
    removed_count = 0
    for f in directory.glob("*.mp3"):
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
            import shutil
            try:
                shutil.rmtree(sub)
                removed_count += 1
            except Exception:
                pass
    if removed_count > 0:
        print(f"[Startup] Cleaned up {removed_count} previously generated file(s)/folder(s).")


# ===========================================================================
# Main Lesson Builder
# ===========================================================================

async def build_lesson() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Clean up old files from previous runs
    clean_previous_outputs(OUTPUT_DIR)

    tmp_dir = OUTPUT_DIR / "_google_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)


    # API key check
    if not GOOGLE_API_KEY:
        print("\n[ERROR] Google API key was not found!")
        print("Please paste your API key into 'google_api_key.txt' in the project root folder.")
        return

    if DIALOG_MODE:
        speaker_rows = load_dialog_csv()

        print("=" * 65)
        print("Mode: DIALOG (Google Cloud Dutch Voices)")
        print("Speakers & Sentences:")
        for speaker_id, sentences in speaker_rows:
            voice_name = DIALOG_VOICES.get(speaker_id, "UNKNOWN")
            print(f"  Speaker '{speaker_id}' ({voice_name}): {len(sentences)} sentence(s)")
        print(f"Total speaker rows: {len(speaker_rows)}")
        print(f"Repeats per sentence: ×{DIALOG_REPEATS}")
        print("=" * 65)

        all_segments: list[AudioSegment] = []
        generated_row_files: list[Path] = []
        turn_counter = 1

        for row_idx, (speaker_id, sentences) in enumerate(speaker_rows, start=1):
            print(f"\nRow {row_idx}/{len(speaker_rows)} (Speaker '{speaker_id}'):")
            row_audio = AudioSegment.empty()

            for text in sentences:
                turn_seg = await build_dialog_turn(turn_counter, speaker_id, text, tmp_dir)
                row_audio += turn_seg
                turn_counter += 1

            all_segments.append(row_audio)
            out_path = OUTPUT_DIR / f"{row_idx:03d}.mp3"
            normalize_and_export(row_audio, out_path)
            generated_row_files.append(out_path)
            print(f"  Saved row: {out_path.name} ({out_path.stat().st_size // 1024} KB)")

    else:
        headers, data_rows = load_normal_csv()
        validate_order(headers)

        print("=" * 65)
        print("Mode: NORMAL (Google Cloud Dutch + Edge-TTS Persian)")
        print("CSV Columns:")
        for i, lang in enumerate(headers, 1):
            print(f"  col{i} = {lang}")

        print("\nPlayback Order:")
        for item in SEGMENT_ORDER:
            col_1based = item[0]
            gender     = item[1]
            repeats    = item[2]
            speed      = item[3] if len(item) > 3 else 1.0
            speed_val  = parse_speed_to_float(speed)
            lang       = headers[col_1based - 1]
            voice      = VOICES[(lang, gender)]
            provider   = "Google" if voice.startswith("nl-") else "Edge"
            print(f"  col{col_1based} ({lang:7s}) | {gender:6s} | ×{repeats} | speed={speed_val}x | {provider} ({voice})")

        print(f"\nRows to process: {len(data_rows)}")
        print("=" * 65)

        all_segments: list[AudioSegment] = []
        generated_row_files: list[Path] = []

        for i, cells in enumerate(data_rows, start=1):
            preview = cells[0].strip() if cells else f"row {i}"
            print(f"\nRow {i}/{len(data_rows)}: {preview}")

            segment = await build_row_normal(i, cells, headers, tmp_dir)
            all_segments.append(segment)

            out_path = OUTPUT_DIR / f"{i:03d}.mp3"
            normalize_and_export(segment, out_path)
            generated_row_files.append(out_path)
            print(f"  Saved: {out_path.name} ({out_path.stat().st_size // 1024} KB)")

    # --- Full Combined Lesson ---
    print("\n" + "=" * 65)
    print("Building full combined lesson file...")
    full_lesson = sum(all_segments, AudioSegment.empty())

    full_path = OUTPUT_DIR / "full_lesson_google.mp3"
    normalize_and_export(full_lesson, full_path)
    print(f"Full lesson exported: {full_path.resolve()}")
    print(f"Duration            : {len(full_lesson) / 1000:.1f}s ({len(full_lesson) / 60000:.1f} mins)")
    print("=" * 65)

    # --- Cleanup chunk files if enabled ---
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
        import shutil
        if tmp_dir.exists():
            try:
                shutil.rmtree(tmp_dir)
            except Exception:
                pass
        print(f"[Cleanup] Removed {cleaned_count} row chunk files and temporary cache.")
        print(f"[Cleanup] Clean directory: only '{full_path.name}' remains.")

    print("All tasks completed successfully!")


if __name__ == "__main__":
    asyncio.run(build_lesson())

