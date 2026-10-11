# Dutch Language Shadowing Audio Generator

A Python tool to generate structured, high-quality audio files for language shadowing practice (Dutch and Persian translations/dialogues) using Microsoft Edge TTS and PyDub.

## Features

- **Adaptive Silence**: Pauses automatically scale based on the length of each word or sentence to allow sufficient shadowing time.
- **Dual Modes**:
  - **Normal Mode**: Word, sentence, and translation combinations with customizable order, voice gender, and repeat counts.
  - **Dialog Mode**: Multi-turn realistic dialogues where each speaker has a distinct voice.
- **High Compatibility Audio**: Outputs normalized stereo MP3 files (44.1 kHz, 128 kbps).
- **Flexible Input**: Inline CSV configuration without needing external spreadsheet files.

## Prerequisites

- Python 3.9+
- [FFmpeg](https://ffmpeg.org/) installed and available in your system `PATH` (required by `pydub` for audio processing and MP3 exporting).

## Installation

```bash
git clone https://github.com/your-username/dutch-language-shadowing.git
cd dutch-language-shadowing
pip install -r requirements.txt
```

## Usage

1. Open `src/word_sentences_meaning_shadowing.py`.
2. Configure settings under:
   - `SHARED CONFIGURATION`: Set `DIALOG_MODE = False` (for vocabulary/sentences) or `True` (for dialogue).
   - Adjust `SILENCE_RATIO` (default `0.8` means pause is 0.8× spoken duration).
3. Run the script:

```bash
python src/word_sentences_meaning_shadowing.py
```

Generated audio files will be saved in `src/output/` (individual items numbered `001.mp3`, `002.mp3`, etc., alongside a merged `full_lesson.mp3`).
