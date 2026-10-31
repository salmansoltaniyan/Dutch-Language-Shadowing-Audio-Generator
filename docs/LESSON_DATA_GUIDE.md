# LESSON_DATA Guide — Dutch Shadowing Audio Generator

This document explains how my shadowing app works, so you can write `LESSON_DATA`
for it. I will give you a chapter of a Dutch textbook (dialogue, vocabulary,
grammar, exercises); you turn it into a `LESSON_DATA` block that I paste into
`src/google_shadowing_app.py` and run to produce one MP3 file.

## How the app works

1. It reads `LESSON_DATA`, a multi-line string. **Every line is one "row".**
2. Each row is split into segments by **speaker tags**: `a:`, `b:`, `c:` ...
3. Each segment is spoken by the voice configured for that tag in `SPEAKERS`
   (language, voice, number of repeats, speed).
4. After **every** spoken segment the app inserts a silence of
   `1.6 × segment length` (minimum 1 second). That pause is the time I use to
   repeat out loud (shadowing).
5. If a speaker has `repeats: 2`, the segment + pause is played twice in a row.
6. All rows are joined into a single file `full_lesson_google.mp3`.

TTS engines: Dutch / English / German use Google Cloud Chirp 3 HD (paid per
character). Persian uses Microsoft Edge-TTS (free). Identical text with the
same voice and speed is synthesized only once and reused, so repeating a
sentence inside the lesson costs nothing extra.

## Current speaker tags (default setup)

| Tag | Language | Voice              | Typical role                         |
|-----|----------|--------------------|--------------------------------------|
| `a` | Dutch    | male1 (Fenrir)     | Dutch speaker 1 / dialogue person A  |
| `b` | Dutch    | female1 (Aoede)    | Dutch speaker 2 / dialogue person B  |
| `c` | Dutch    | male2 (Algenib)    | Dutch speaker 3                      |
| `d` | Dutch    | female2 (Gacrux)   | Dutch speaker 4                      |
| `e` | Persian  | female1 (Dilara)   | Persian translation for `a`          |
| `f` | Persian  | male1 (Farid)      | Persian translation for `b`          |
| `g` | Persian  | female2 (Dilara)   | extra Persian voice                  |

All Dutch voices currently run at speed 0.95, Persian at 1.1, repeats = 1.
Available presets per language: `male1`, `male2`, `female1`, `female2`.
Languages: `dutch`, `english`, `german`, `persian`.

Use only tags that exist in `SPEAKERS`. An unknown tag stops the program with an
error. If a lesson needs a different setup (more speakers, slower speed, more
repeats, English instead of Persian), also give me an updated `SPEAKERS` block
in this format:

```python
SPEAKERS = {
    "a": {"language": "dutch",   "voice": "male1",   "repeats": 1, "speed": 0.95},
    "b": {"language": "dutch",   "voice": "female1", "repeats": 1, "speed": 0.95},
    "e": {"language": "persian", "voice": "female1", "repeats": 1, "speed": 1.1,
          "silence_ratio": 0.5},
}
```

`silence_ratio` is optional: the pause after that speaker is
`segment length × silence_ratio`. Without it, the global `SILENCE_RATIO` is used.
Typical use: a short pause after the Persian translation (nothing to repeat)
and a long pause after Dutch (time to shadow).

## Syntax rules (important)

- Format of a row: `tag: text tag: text tag: text ...`
- A tag is letters/digits/underscore followed by a colon, at the start of the
  line or after a space. A tag can appear several times in one row.
- **Never use a colon inside the spoken text.** Anything like `word:` or `8:30`
  after a space is read as a new speaker tag and breaks the row.
  Write times as `half negen` / `8.30`, and drop labels like `Let op:`.
- Empty lines are ignored. Lines starting with `#` are comments (not spoken);
  use them for section titles, e.g. `# Hoofdstuk 5 — Woordenlijst`.
- Everything in the text is read aloud, including brackets and slashes.
  `(formal)` or `ik / jij` will be spoken. Put only what I should hear.
- Keep segments short: one sentence or one phrase. Because the pause is 1.6×
  the length, a very long sentence means a very long pause and is hard to
  shadow. Split long sentences into two segments or two rows.
- Persian text must be natural, fluent Persian (not word-for-word).

## Lesson formats I use

### 1. Dialogue with Persian translation, each line twice (my standard)

Persian first, then Dutch, and the whole pair twice. The Persian voice matches
the Dutch speaker (`e` pairs with `a`, `f` pairs with `b`).

```
e: نوبت چه کسی است؟ a: Wie is er aan de beurt? e: نوبت چه کسی است؟ a: Wie is er aan de beurt?
f: من. b: Ik. f: من. b: Ik.
e: چیز دیگری لازم دارید؟ a: Anders nog iets? e: چیز دیگری لازم دارید؟ a: Anders nog iets?
```

### 2. Pure dialogue (listening, no translation)

```
a: Heb je het artikel gelezen over echte Hollandse winterkost?
b: Ja, in de studentenkeuken. Wat maken ze deze week?
```

### 3. Vocabulary: word → example sentence → translation

```
a: uitstekend b: Het gaat uitstekend met mij. e: عالی
a: de buren b: Onze buren komen morgen eten. e: همسایه‌ها
```

Variant with several example sentences for one word:

```
a: uitstekend b: Ik ben heel blij. b: Het gaat uitstekend. e: عالی
```

### 4. Grammar drill: situation → cue → answer

The learner hears a situation and a cue, tries to make the sentence in the
pause, then hears the correct answer.

```
b: Ik wil op vakantie! a: een paar dagen naar Parijs gaan d: Zullen we een paar dagen naar Parijs gaan?
b: Dit is een leuk café! a: hier iets drinken d: Zullen we hier iets drinken?
```

### 5. Translation drill (Persian → Dutch)

Persian first; I try to say it in Dutch during the pause; then the Dutch answer.

```
e: من هفته آینده به تعطیلات می‌روم. a: Ik ga volgende week op vakantie.
```

## What I expect from you for each chapter

1. Ask which format(s) I want if I didn't say, or propose a sensible mix
   (for example dialogue format 1 + vocabulary format 3 + grammar drill format 4).
2. Return **one code block** containing the complete `LESSON_DATA` content,
   ready to paste between the triple quotes of `LESSON_DATA = """ ... """`.
   Use `#` comment lines to separate sections.
3. If the speaker setup must change, return a second code block with the full
   `SPEAKERS` dict.
4. Keep the Dutch text exactly as in the book (correct spelling, punctuation),
   unless I ask for simplified or extra example sentences.
5. Check before answering: no colons inside text, only configured tags,
   one row per line, no explanations inside the spoken text.
