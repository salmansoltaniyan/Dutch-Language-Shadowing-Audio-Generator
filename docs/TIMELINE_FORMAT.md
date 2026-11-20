# Lesson timeline format (for player apps)

Every lesson MP3 made by this project has a **timeline**: when each piece of text is spoken. A player uses it
to show the text of the piece that is playing (subtitles). The same JSON is stored in two places:

1. **Inside the MP3**: an ID3v2.4 tag at the start of the file, in a `TXXX` (user-defined text) frame with
   description `SHADOWING_TIMELINE`. Text encoding byte `3` = UTF-8. The value is the JSON on one line.
2. **Next to the MP3** (fallback): `<same name>.json`, e.g. `lesson_2026-11-20.mp3` → `lesson_2026-11-20.json`.

Read the tag first; use the `.json` file if the tag is missing. MP3s without either have no subtitles.

## JSON

```json
{"audio": "lesson_2026-11-20.mp3", "duration": 467.166,
 "segments": [
  {"start": 0.0,   "speech_end": 2.544, "end": 3.816,  "row": 1, "tag": "e", "lang": "persian", "text": "یادم می‌آید"},
  {"start": 3.816, "speech_end": 7.055, "end": 11.913, "row": 1, "tag": "a", "lang": "dutch",   "text": "ik herinner me"}
 ]}
```

| Field | Meaning |
|---|---|
| `start`, `end` | seconds from the start of this MP3. `end` of a segment = `start` of the next one, so the segments cover the whole file without gaps |
| `speech_end` | when the voice stops; from here to `end` is the pause in which the listener repeats |
| `row` | lesson line number (one exercise); several segments share a row, useful for "repeat row" |
| `tag` | speaker tag of the lesson (`a`, `b`, `e2`, …) |
| `lang` | `dutch`, `persian`, `english` or `german`: Persian is right-to-left |
| `text` | the spoken text (UTF-8) |

Show a segment from its `start` until its `end` (so also during the pause). Segments are sorted by `start`;
find the current one with a binary search on the playback position.

## Reading the tag on Android

With Media3 / ExoPlayer the ID3 frames arrive as metadata of the audio track:

```kotlin
override fun onTracksChanged(tracks: Tracks) {
    for (group in tracks.groups) for (i in 0 until group.length) {
        val meta = group.getTrackFormat(i).metadata ?: continue
        for (k in 0 until meta.length()) {
            val e = meta[k]
            if (e is TextInformationFrame && e.id == "TXXX" && e.description == "SHADOWING_TIMELINE")
                timeline = JSONObject(e.values.first())
        }
    }
}
```

Without Media3, parse the ID3v2.4 header yourself (Android's `MediaMetadataRetriever` does not return `TXXX`):
- Header (10 bytes): `"ID3"`, version `4 0`, flags, tag size as a 4-byte **syncsafe** integer (7 bits per byte).
- Then frames: 4-byte id, 4-byte syncsafe size, 2 flag bytes, body. Stop at padding (id byte 0).
- `TXXX` body: encoding byte (`3`), description `SHADOWING_TIMELINE`, a `0x00` byte, then the UTF-8 JSON.

Check a file on a computer:
`ffprobe -v error -show_entries format_tags=SHADOWING_TIMELINE -of default=nw=1:nk=1 lesson.mp3`
