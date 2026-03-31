"""
Smart Read Companion - Main processing pipeline.
Orchestrates loading, downloading, analysing and saving.
"""

import json
import os
import time
import sqlite3

from config import (
    PLAYLIST_DIR,
    PLAYLIST_FILES,
    PAUSE_BETWEEN_TRACKS,
    ANALYSIS_VERSION,
)
from database import (
    save_playlist,
    save_track,
    save_playlist_track_link,
    is_analysed,
    save_features,
)
from downloader import (
    is_cached,
    get_cached_path,
    download_track,
)
from analyser import analyse_track


# ─────────────────────────────────────────────
# PIPELINE
# ─────────────────────────────────────────────

from spotipy.oauth2 import SpotifyOAuth
import spotipy
import os
from dotenv import load_dotenv

load_dotenv()

def get_spotify_client():
    return spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
        redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI",
                               "https://127.0.0.1:1234"),
        scope="playlist-read-private"
    ))

def process_playlist(conn: sqlite3.Connection, label: str,
                     json_path: str, limit: int = None,
                     redownload: bool = False,
                     reanalyse: bool = False):
    """
    Full pipeline for one playlist:
    Load JSON → save metadata → download audio → analyse → save features.

    Resumable - safely re-run at any point without duplicating work.
    """
    print(f"\n{'='*55}")
    print(f"  Playlist  : {label}")
    print(f"  Version   : {ANALYSIS_VERSION}")
    print(f"  Redownload: {redownload} | Reanalyse: {reanalyse}")
    print(f"{'='*55}")

    if not os.path.exists(json_path):
        print(f"  ❌ File not found: {json_path}")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    tracks      = data.get("tracks", [])
    playlist_id = data.get("playlist_id", label)

    if limit:
        tracks = tracks[:limit]
        print(f"  ⚠️  Limit active: first {limit} tracks only")

    print(f"  Tracks to process: {len(tracks)}")

    save_playlist(conn, label, playlist_id, len(tracks))

    counts = {
        "downloaded":      0,
        "from_cache":      0,
        "download_failed": 0,
        "analysed":        0,
        "already_done":    0,
        "analyse_failed":  0,
        "skipped":         0,
    }

    # Create Spotify client once per playlist
    print(f"  Connecting to Spotify for ISRC lookups...")
    try:
        sp = get_spotify_client()
    except Exception as e:
        print(f"  ⚠️  Spotify unavailable: {e}")
        print(f"  ⚠️  Will fall back to Deezer name search")
        sp = None

    for i, track in enumerate(tracks):
        track_id = track.get("id")
        name     = track.get("name", "Unknown")

        if not track_id:
            counts["skipped"] += 1
            continue

        # Always save/update track metadata
        save_track(conn, track)
        save_playlist_track_link(conn, playlist_id, track_id)
        conn.commit()

        print(f"\n  [{i+1}/{len(tracks)}] {name[:50]}")

        # Pass sp to download_track
        mp3_path, source = download_track(
            track, conn, sp=sp, force=redownload
        )

        if mp3_path:
            size_kb = os.path.getsize(mp3_path) // 1024
            print(f"    ✅ Ready ({size_kb} KB) [{source}]")
            if source == "deezer_search":
                print(f"    ⚠️  Search match - verify this is correct")
            counts["downloaded"] += 1
        else:
            counts["download_failed"] += 1
            time.sleep(1)
            continue

        # ── Download phase ─────────────────────────────────
        if is_cached(track_id) and not redownload:
            mp3_path = get_cached_path(track_id)
            counts["from_cache"] += 1
            print(f"    📁 Using cached audio")
        else:
            print(f"    ⬇️  Downloading...")
            mp3_path, source = download_track(track, conn, force=redownload)

            if mp3_path:
                size_kb = os.path.getsize(mp3_path) // 1024
                print(f"    ✅ Downloaded ({size_kb} KB)")
                counts["downloaded"] += 1
            else:
                print(f"    ❌ Download failed [{source}]")
                counts["download_failed"] += 1
                time.sleep(1)
                continue

        # ── Analysis phase ─────────────────────────────────
        if is_analysed(conn, track_id) and not reanalyse:
            print(f"    ⏭️  Already analysed at v{ANALYSIS_VERSION}")
            counts["already_done"] += 1
            continue

        print(f"    🔬 Analysing...")
        features = analyse_track(mp3_path)

        if features:
            save_features(conn, track_id, features)
            print(f"    ✅ V={features['estimated_valence']} "
                  f"A={features['estimated_arousal']} "
                  f"BPM={features['bpm']} "
                  f"mode={features['track_mode']}")
            counts["analysed"] += 1
        else:
            save_features(conn, track_id, None,
                          failed=True, failure_reason="essentia_failed")
            print(f"    ❌ Analysis failed")
            counts["analyse_failed"] += 1

        time.sleep(PAUSE_BETWEEN_TRACKS)

    # ── Summary ────────────────────────────────────────────
    print(f"\n  📊 {label} complete:")
    for key, val in counts.items():
        if val > 0:
            print(f"     {key:<20} {val}")


def process_all(conn: sqlite3.Connection, limit: int = None,
                redownload: bool = False, reanalyse: bool = False):
    """Process all playlists in config."""
    for label, filename in PLAYLIST_FILES.items():
        json_path = os.path.join(PLAYLIST_DIR, filename)
        process_playlist(
            conn, label, json_path,
            limit=limit,
            redownload=redownload,
            reanalyse=reanalyse,
        )