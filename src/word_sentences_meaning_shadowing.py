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
SILENCE_RATIO  = 0.9
MIN_SILENCE_MS = 1000   # minimum pause in milliseconds

# Final MP3 output settings (normalized for universal player compatibility)
OUTPUT_SAMPLE_RATE = 44100   # Hz  (standard CD quality)
OUTPUT_CHANNELS    = 2       # 1=mono, 2=stereo
OUTPUT_BITRATE     = "128k"  # MP3 bitrate

# Choose which mode to run (True = Dialog Mode, False = Normal Mode)
DIALOG_MODE = False


# ===========================================================================
# NORMAL MODE CONFIGURATION
# ===========================================================================

# ---------------------------------------------------------------------------
# Please generate raw CSV text based on the list of Dutch words provided below:
#
# 1. First row (Header) must strictly be:
#    dutch,dutch,persian
#
# 2. Column 1: The Dutch word or phrase (include article 'de' or 'het' for nouns).
# 3. Column 2: A natural, practical example sentence in Dutch containing the word.
# 4. Column 3: Accurate and natural Persian translation of word(meaning).

#
# Important Rules:
# - Do not add any extra columns or explanations.
# - Output ONLY valid raw CSV text (no markdown formatting, no code blocks).
# - Do NOT use commas (,) inside the Dutch sentences to prevent CSV column breaking.
#   Use periods (.) or words like 'en' instead.

# ---------------------------------------------------------------------------
CSV_DATA = """
dutch,dutch,persian
uitstekend,Het gaat uitstekend met mij.,عالی
fantastisch,Wij hebben een fantastisch weekend gehad.,فوق‌العاده
niet zo goed,Het gaat vandaag niet zo goed met hem.,نه چندان خوب
Heb je zin om,Heb je zin om koffie te drinken?,میلی داری به
Ga je mee,Ga je mee naar de stad?,همراه من می‌آیی
Goed idee,Dat is echt een goed idee.,ایده خوب
Dat vind ik niet leuk,Dat vind ik helemaal niet leuk.,دوست ندارم
het lokaal,De studenten zitten in het lokaal.,کلاس
roepen,Moeder gaat de kinderen roepen.,صدا زدن
spellen,Kun je jouw naam even spellen?,هجی کردن
geven,Ik wil jou een cadeau geven.,دادن
de ouders,Mijn ouders wonen in een ander land.,والدین
de activiteit,Voetballen is een leuke activiteit.,فعالیت
het moment,Wacht even op dit moment.,لحظه
nemen,Ik ga een warme thee nemen.,برداشتن
de collega,Mijn collega helpt mij op het werk.,همکار
automatisch,Deze deur gaat automatisch open.,خودکار
de diensten,De bank biedt goede diensten aan.,خدمات
het Talencentrum,Ik leer Nederlands bij het Talencentrum.,مرکز زبان
bezoeken,Wij gaan morgen onze oma bezoeken.,دیدار کردن
de vraag,De cursist stelt een moeilijke vraag.,سؤال
beantwoord,De leraar heeft de e-mail beantwoord.,پاسخ داده
raadplegen,Je moet eerst de website raadplegen.,مراجعه کردن
ons best doen,Wij doen ons best om te slagen.,تلاش کردن
spoedig,Wij hopen op een spoedig antwoord.,سریع
het secretariaat,Het secretariaat is nu gesloten.,دبیرخانه
de openingstijden,Wat zijn de openingstijden van de winkel?,ساعات کاری
de werkdag,Vrijdag is mijn laatste werkdag.,روز کاری
bereikbaar,De dokter is vandaag niet bereikbaar.,در دسترس
wil je graag doen,Wat wil je graag vandaag doen?,دوست داری انجام بدی
kom je samen mee,Kom je samen mee naar het feest?,همراه من می‌آیی
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
# Each entry is a tuple with 3 or 4 elements:
#   (column_index, gender, repeats[, speed])
#
#   column_index : 1-based column position in the CSV  (1, 2, 3, ...)
#   gender       : "male" or "female"
#   repeats      : how many times to play this segment
#   speed        : (Optional) speed multiplier. Default is 1.0 (normal).
#                  Examples: 0.8 (slower), 1.2 (faster), "0.8x", "-20%", etc.
#
# Examples:
#   (2, "male", 2, 0.8)    -> Dutch sentence, male voice, 2 repeats, at 0.8x speed
#   (1, "male", 1)         -> Dutch word, male voice, 1 repeat, normal speed (1.0x)
#   (3, "female", 1, 1.0)  -> Persian translation, female voice, normal speed
# ---------------------------------------------------------------------------
SEGMENT_ORDER = [
    (1, "male",   1, 0.8),  # Dutch word, male voice, 1 repeat, slower speed
    (2, "male", 2),
    (3, "female",   1),
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

def parse_speed_to_rate(speed: float | int | str = 1.0) -> str:
    """Convert speed (e.g. 0.8, 1.2, '0.8x', '-20%') to edge-tts rate format (e.g. '-20%', '+20%')."""
    if isinstance(speed, str):
        s = speed.strip().lower()
        if s.endswith('%'):
            return s if s.startswith(('+', '-')) else f"+{s}"
        if s.endswith('x'):
            s = s[:-1]
        try:
            val = float(s)
        except ValueError:
            raise ValueError(f"Invalid speed format: '{speed}'. Use e.g. 0.8, '0.8x', or '-20%'.")
    else:
        val = float(speed)

    pct = round((val - 1.0) * 100)
    return f"{pct:+d}%"


async def make_audio(text: str, voice: str, filepath: Path, rate: str = "+0%", max_retries: int = 3) -> None:
    """Synthesize text to speech and save to filepath with retry mechanism and rate support."""
    for attempt in range(1, max_retries + 1):
        try:
            await edge_tts.Communicate(text, voice, rate=rate).save(str(filepath))
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
        parse_speed_to_rate(speed)


# ===========================================================================
# Normal mode builder
# ===========================================================================

async def build_row_normal(
    row_index: int,
    cells:     list[str],
    headers:   list[str],
    tmp_dir:   Path,
) -> AudioSegment:
    """Normal mode: assemble audio per SEGMENT_ORDER with optional individual speeds."""
    cache: dict[tuple[int, str, str], AudioSegment] = {}

    for item in SEGMENT_ORDER:
        col_1based = item[0]
        gender     = item[1]
        repeats    = item[2]
        speed      = item[3] if len(item) > 3 else 1.0
        rate       = parse_speed_to_rate(speed)

        col_idx = col_1based - 1
        key     = (col_idx, gender, rate)
        if key in cache:
            continue

        lang  = headers[col_idx]
        text  = cells[col_idx].strip() if col_idx < len(cells) else ""
        voice = VOICES[(lang, gender)]

        rate_tag    = rate.replace('+', 'p').replace('-', 'm').replace('%', '')
        rate_suffix = f"_{rate_tag}" if rate != "+0%" else ""
        path        = tmp_dir / f"row{row_index:03d}_col{col_1based}_{gender}{rate_suffix}.mp3"

        speed_display = f"{speed}x" if isinstance(speed, (int, float)) else str(speed)
        print(f"  [TTS] col{col_1based} {lang} ({gender}, ×{repeats}, speed={speed_display}): {text}")
        if not text:
            # Fallback for empty text: generate 500ms of silence rather than crashing TTS
            seg = AudioSegment.silent(duration=500)
        else:
            if not (path.exists() and path.stat().st_size > 0):
                await make_audio(text, voice, path, rate=rate)
                await asyncio.sleep(0.3)
            else:
                print(f"    [Cache] Using existing audio for row {row_index:03d} col {col_1based}{rate_suffix}")
            seg = AudioSegment.from_mp3(str(path))

        cache[key] = seg

    result = AudioSegment.empty()
    for item in SEGMENT_ORDER:
        col_1based = item[0]
        gender     = item[1]
        repeats    = item[2]
        speed      = item[3] if len(item) > 3 else 1.0
        rate       = parse_speed_to_rate(speed)

        seg   = cache[(col_1based - 1, gender, rate)]
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
    if not (path.exists() and path.stat().st_size > 0):
        await make_audio(text, voice, path)
        await asyncio.sleep(0.3)
    else:
        print(f"    [Cache] Using existing audio for turn {turn_index:02d}")

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
        for item in SEGMENT_ORDER:
            col_1based = item[0]
            gender     = item[1]
            repeats    = item[2]
            speed      = item[3] if len(item) > 3 else 1.0
            speed_str  = f"{speed}x" if isinstance(speed, (int, float)) else str(speed)
            lang       = headers[col_1based - 1]
            print(f"  col{col_1based} ({lang:7s})  |  {gender:6s}  |  ×{repeats}  |  speed: {speed_str}")

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


if __name__ == "__main__":
    asyncio.run(build_lesson())