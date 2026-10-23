# music_mood

**Estimates the emotional feel (Valence/Arousal) of soundtrack music, so a book's mood can be
matched to the right track.**

This is the *music side* of [**Music Supervisor**](https://github.com/medusa606/manuscript_app), an app
that scores music to the book you're reading. Its sister repo
[**emotion-reader**](https://github.com/medusa606/emotion-reader) places each page of a book on the
same Valence/Arousal map, so the app can pick the track whose mood is closest to the current scene.

> **Why not just use Spotify's audio features?** Spotify removed `valence`, `energy` and the rest of
> its audio-features API for new apps in November 2024. This repo rebuilds those features by
> analysing 30-second previews directly.

---

## Where this fits

```text
 ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────────────┐
 │ db_builder       │   │ emotion-reader   │   │ music_mood               │
 │ (book metadata)  │   │ (book VA curve)  │   │ ◄── YOU ARE HERE         │
 └────────┬─────────┘   └────────┬─────────┘   └────────────┬─────────────┘
          │                      ┆ page VA                  ┆ track VA
          ▼                      ▼                          ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │ manuscript_app (Android): follow reading position → pick nearest track │
 └────────────────────────────────────────────────────────────────────────┘
                                       ┆ = planned, not wired in yet
```

See the [manuscript_app README](https://github.com/medusa606/manuscript_app#readme) for the full
system picture and project status.

---

## Pipeline

```text
 Spotify playlist  ──(spotipy, exported once)──►  playlist_data/<label>.json
                                                         │
                                                         ▼
                                     Spotify API: track → ISRC code
                                                         │
                                  ┌──────────────────────┴───────────────────────┐
                                  ▼                                              ▼
                    Deezer /track/isrc:<ISRC>                 fallback: Deezer search "name artist"
                    (exact recording match)                   (flagged "verify this is correct")
                                  └──────────────────────┬───────────────────────┘
                                                         ▼
                                     30 s MP3 preview → audio_cache/<spotify_id>.mp3
                                                         │
                                                         ▼
                Essentia: BPM · RMS energy · loudness · spectral centroid · key/mode · danceability
                                                         │
                                                         ▼
               Valence = 0.65 if major else 0.30, ± up to 0.1 for spectral brightness
               Arousal = 0.6 × energy + 0.4 × tempo   (both normalised)
                                                         │
                                                         ▼
                                         track_features.db (SQLite)
```

Every step is **resumable**: re-running skips tracks that are already downloaded or analysed at the
current `ANALYSIS_VERSION`.

Both V and A are on a **0 … 1** scale. emotion-reader uses −1 … +1, so rescale one side before
matching (`v_book = 2 * v_music - 1`).

---

## What's in the database

`track_features.db` is committed and currently holds:

| Playlist | Tracks analysed | avg V | avg A | avg BPM | minor key |
|----------|---------------:|------:|------:|--------:|----------:|
| reading_soundscape | 492 | 0.36 | 0.44 | 118 | 68 % |
| space_pirates | 328 | 0.39 | 0.55 | 123 | 65 % |
| space_opera | 305 | 0.34 | 0.48 | 117 | 67 % |
| spy_thriller | 93 | 0.30 | 0.58 | 117 | 81 % |
| horror | 10 | 0.36 | 0.53 | 132 | 60 % |

1,190 unique tracks in total, 1,174 analysed (some tracks appear in more than one playlist).

> **Honest caveat:** the playlist averages are close together, so the key/tempo/energy heuristic
> barely separates *horror* from *space pirates*. `panns.py` is an experiment to fix this; see below.

### Schema

| Table | Purpose |
|-------|---------|
| `playlists` | Spotify playlist ID, label, track count |
| `tracks` | Spotify metadata: name, artists, album, release date, ISRC, Deezer ID and preview URL, popularity |
| `playlist_tracks` | Many-to-many link |
| `track_downloads` | Local path, size, source (`deezer`), failure reason |
| `track_features` | One row per (track, analysis_version): BPM, key, mode, RMS, loudness, centroid, danceability, **estimated_valence**, **estimated_arousal** |
| `track_features_active` | Which analysis version is current for each track |

---

## Usage

```bash
python main.py                              # process every playlist in config.py
python main.py --playlist horror            # one playlist
python main.py --playlist horror --limit 5  # quick test
python main.py --reanalyse                  # re-run Essentia, keep downloads
python main.py --redownload                 # force fresh downloads
python main.py --summary                    # database summary
python main.py --cache                      # audio-cache status
python main.py --clear-cache [--dry-run]    # delete MP3s that are already analysed
```

Helper scripts:

| Script | Purpose |
|--------|---------|
| `db_inspect.py` | Data-quality report: `--playlist horror`, `--track <spotify_id>` |
| `play_track.py` | Listen to cached previews (needs `ffplay`) to check the Deezer match is right |
| `panns.py` | **Experiment:** tags audio with PANNs (AudioSet: *Scary music*, *Tense music*, *Happy music*, *Orchestra*, *Choir*…), derives an alternative V/A, and compares it to Essentia |
| `spotify.py` | One-off exporter: Spotify playlist → `playlist_data/*.json` |

### Adding a playlist

1. Export it with `spotify.py` (set `playlist_name`, `playlist_id` and `output_file`) into
   `playlist_data/`.
2. Add a `label: filename` entry to `PLAYLIST_FILES` in [`config.py`](config.py).
3. Run `python main.py --playlist <label>`.

---

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

* **Essentia** has pip wheels for Linux and macOS only. On Windows, use WSL.
* `panns.py` also needs `pip install panns-inference librosa torch`. It downloads a ~300 MB
  checkpoint on first run.
* `play_track.py` needs `ffplay` (part of FFmpeg).

Create a `.env` file (it's git-ignored) with your
[Spotify developer app](https://developer.spotify.com/dashboard) credentials:

```ini
SPOTIFY_CLIENT_ID=...
SPOTIFY_CLIENT_SECRET=...
SPOTIFY_REDIRECT_URI=https://127.0.0.1:1234
```

Spotify is used only to look up ISRC codes. If it's unavailable, the pipeline falls back to a
Deezer name search. Deezer previews need no API key.

---

## Repo layout

```text
main.py          CLI entry point
config.py        paths, playlist list, download settings, ANALYSIS_VERSION
pipeline.py      orchestration: load JSON → download → analyse → save
downloader.py    Spotify ISRC → Deezer preview download + cache
analyser.py      Essentia feature extraction + V/A heuristics
database.py      all SQLite access
db_inspect.py    data-quality reports
panns.py         PANNs audio-tagging experiment
play_track.py    listen to cached previews
spotify.py       playlist exporter (one-off script)
playlist_data/   exported playlists (archive/ holds older formats)
datasets/        jamendo_tags.json: tag-normalisation map (genre spelling variants)
track_features.db
```

## Next steps

* Decide between Essentia heuristics, PANNs, or a blend. PANNs mood tags look far more
  discriminative for film-score material.
* Add **Dominance** (e.g. from loudness and low-end weight) to make it full VAD.
* Export a compact `tracks.json` (`spotify_id, v, a, bpm, mode, playlist`) for the Android app.
* Tag tracks with candidate **leitmotif** roles (hero, villain, love theme…) for character themes.
