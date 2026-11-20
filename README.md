# Dutch Language Shadowing Audio Generator

Turn a plain-text lesson into one MP3 file for shadowing practice: every word or sentence is spoken by a
text-to-speech voice, followed by a pause in which you repeat it out loud. Lessons can mix Dutch, English,
German and Persian, with several voices.

```text
a: Ik herinner me haar naam. e: اسمش یادم می‌آید.
```
becomes: a Dutch voice says the sentence → pause → a Persian voice says the translation → pause.

## Two engines

The two apps work exactly the same way (same lesson format, same settings, same output). Only the voice
engine is different.

| | `src/google_shadowing_app.py` | `src/edge_tts_shadowing_app.py` |
|---|---|---|
| Dutch, English, German | Google Cloud **Chirp 3 HD** (very natural) | Microsoft **Edge-TTS** neural voices |
| Persian | Edge-TTS | Edge-TTS |
| Cost | Google bills per character after its free monthly quota | free |
| Needs | a Google Cloud API key | nothing (internet connection only) |

Start with Edge-TTS to try things out; use Google when you want the best Dutch voices.

## Windows program (no Python needed)

Download `ShadowingApp-windows.zip` from the
[Releases page](https://github.com/salmansoltaniyan/Dutch-Language-Shadowing-Audio-Generator/releases),
unzip it and double-click `ShadowingApp.exe`. A window opens with two boxes (lesson and speakers, filled with
a small example), the engine choice, a box for the Google API key and a Build button. FFmpeg is included.
Windows may say "Windows protected your PC" the first time: click *More info* → *Run anyway*.
`HOW_TO_USE.txt` in the zip explains the rest.

The same window also runs from source: `python src/shadowing_gui.py`.

### How the exe is made
`.github/workflows/build-exe.yml` builds it on GitHub with PyInstaller, adds FFmpeg (LGPL build), builds the
example lesson with the exe as a test (`ShadowingApp.exe --selftest`) and zips it.
- Push a tag to publish a release: `git tag v1.0` then `git push origin v1.0`.
- Or run the workflow by hand (Actions → Build Windows exe → Run workflow); the zip is then under the run's
  *Artifacts*.

## Installation

1. Python 3.9 or newer.
2. [FFmpeg](https://ffmpeg.org/) installed and on your `PATH` (pydub needs it to read and write MP3).
   Check with `ffmpeg -version`.
3. Install the packages:
   ```bash
   git clone https://github.com/salmansoltaniyan/Dutch-Language-Shadowing-Audio-Generator.git
   cd Dutch-Language-Shadowing-Audio-Generator
   pip install -r requirements.txt
   ```

### Google API key (Google engine only)
1. In the [Google Cloud Console](https://console.cloud.google.com/), create a project and enable the
   **Cloud Text-to-Speech API** (billing must be enabled on the project).
2. Under *APIs & Services → Credentials*, create an **API key**.
3. Paste the key into a file `google_api_key.txt` in the project root (one line, nothing else), or set the
   environment variable `GOOGLE_API_KEY`.

`google_api_key.txt` is in `.gitignore`. Never commit your key.

## Quick start

### Way 1: edit the app file
Open `src/edge_tts_shadowing_app.py` (or `src/google_shadowing_app.py`), replace `SPEAKERS` and
`LESSON_DATA` with your own, and run:
```bash
python src/edge_tts_shadowing_app.py
python src/google_shadowing_app.py
```

### Way 2 (recommended): keep each lesson in its own files
Put the lesson text in one file and the speakers in another, and run `src/run_lesson.py`. You do not
have to edit the app, and long lessons are split into parts (see below).

`my_lesson.txt`:
```text
# Hoofdstuk 11 — new words
e: یادم می‌آید a: ik herinner me
b: Ik herinner me haar naam. e: اسمش یادم می‌آید.
```
`my_lesson_speakers.txt`:
```python
SPEAKERS = {
    "a": {"language": "dutch",   "voice": "male1",   "repeats": 2, "speed": 0.8, "silence_ratio": 1.0},
    "b": {"language": "dutch",   "voice": "female1", "repeats": 1, "speed": 0.8, "silence_ratio": 1.0},
    "e": {"language": "persian", "voice": "female1", "repeats": 1, "speed": 1.0, "silence_ratio": 1.2},
}
```
Run:
```bash
python src/run_lesson.py my_lesson.txt my_lesson_speakers.txt my_lesson --engine edge
python src/run_lesson.py my_lesson.txt my_lesson_speakers.txt my_lesson                  # Google (default)
```
The result is `src/output/my_lesson_<date>_<time>.mp3`.

## The lesson format (`LESSON_DATA`)

- **One line = one row** (one exercise). Empty lines and lines starting with `#` are skipped.
- A line is split into segments by **speaker tags**: `a:`, `b:`, `e2:` … (letters, digits and `_`; a space
  before the tag and a space after the colon).
- Each segment is spoken by the voice of its tag, then followed by a pause.
- Write plain text with normal punctuation (`.` `,` `?` `!`): the voices use it for intonation.
  No markdown, numbering or quotes.
- Every tag you use must exist in `SPEAKERS`, otherwise the program stops with an error.

More rules and tips for writing lessons (also useful as a prompt for an AI that writes lessons for you):
[docs/LESSON_DATA_GUIDE.md](docs/LESSON_DATA_GUIDE.md).

## Speakers (`SPEAKERS`)

| Key | Meaning |
|---|---|
| `language` | `dutch`, `english`, `german` or `persian` |
| `voice` | `male1`, `male2`, `female1`, `female2`, or an exact voice name of the engine |
| `repeats` | how many times the segment (with its pause) is played in a row |
| `speed` | speaking speed, e.g. `0.8` = slower, `1.0` = normal |
| `silence_ratio` | optional: pause after the segment = segment length × this value (minimum 1 second). Without it, the global `SILENCE_RATIO` (1.6) is used |

Typical setup: a long pause after Dutch (time to repeat it), a short pause after the Persian translation.
To give the same voice two different pauses, use two tags with the same voice, e.g. `e` (pause 2.4, time to
answer) and `e2` (pause 1.2).

### Voice presets

| Preset | Google: Dutch | Edge: Dutch | Persian (both) |
|---|---|---|---|
| `male1` | nl-NL-Chirp3-HD-Fenrir | nl-NL-MaartenNeural | fa-IR-FaridNeural |
| `male2` | nl-NL-Chirp3-HD-Algenib | nl-BE-ArnaudNeural (Flemish) | fa-IR-FaridNeural |
| `female1` | nl-NL-Chirp3-HD-Aoede | nl-NL-FennaNeural | fa-IR-DilaraNeural |
| `female2` | nl-NL-Chirp3-HD-Gacrux | nl-NL-ColetteNeural | fa-IR-DilaraNeural |

English and German presets are listed in `VOICE_PRESETS` at the top of each app.

## Output

- Files go to `src/output/`. The name gets a date-time stamp, so earlier lessons are never overwritten.
- Format: MP3, 44.1 kHz, stereo, 192 kbps.
- A sentence that appears several times (same text, voice and speed) is synthesized only once, which saves
  time and Google characters.
- `CLEANUP_CHUNK_FILES = True` (default) keeps only the final lesson. Set it to `False` in the app to also
  keep one MP3 per row (`001.mp3`, `002.mp3`, …).

- **Timeline.** Every lesson MP3 gets a timeline: every spoken segment with its start time, end of speech,
  end of pause, row, tag, language and text. A player app can use it to show the text that is being spoken.
  It is saved twice: as a `.json` file with the same name next to the MP3, and inside the MP3 itself as the
  ID3 tag `TXXX:SHADOWING_TIMELINE` (so the MP3 alone is enough). Both contain the same JSON:
  ```json
  {"audio": "my_lesson_2026-11-19_21-03-01.mp3", "duration": 33.79,
   "segments": [{"start": 0.0, "speech_end": 1.87, "end": 4.12, "row": 1, "tag": "e",
                 "lang": "persian", "text": "یادم می‌آید"}]}
  ```
  To see the tag inside an MP3: `ffprobe -v error -show_entries format_tags=SHADOWING_TIMELINE -of default=nw=1:nk=1 lesson.mp3`,
  or open the file in [Mp3tag](https://www.mp3tag.de/en/) → *Extended Tags* (Alt+T).

Only with `run_lesson.py` (and the window app):
- **Long lessons are split.** A lesson longer than 30 minutes is saved as parts of about equal length, cut
  between two rows: `my_lesson_part1of3_<stamp>.mp3`, … (change `MAX_PART_MINUTES` in `run_lesson.py`).
  Every part has its own timeline.

## Troubleshooting

| Problem | Fix |
|---|---|
| `Couldn't find ffmpeg` / error while reading MP3 | install FFmpeg and make sure `ffmpeg -version` works in the same terminal |
| `Google API key was not found` | create `google_api_key.txt` in the project root (Google engine only) |
| `Google TTS API Error [403]` | enable the Cloud Text-to-Speech API and billing for the project of the key |
| `Speaker tag 'x' not found` | the lesson uses a tag that is not in `SPEAKERS` |
| Edge-TTS fails now and then | it retries 3 times; run again if it still fails (it needs internet) |
