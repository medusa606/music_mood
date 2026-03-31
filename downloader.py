"""
downloader.py - Updated with ISRC-based exact track matching
"""

import os
import requests
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from pathlib import Path
from dotenv import load_dotenv

from database import (
    save_download_record,
    get_download_status,
    is_analysed,
    save_track_enrichment,
)
from config import (
    AUDIO_CACHE_DIR,
    DOWNLOAD_TIMEOUT_SECS,
    ANALYSIS_VERSION,
)

load_dotenv()


# ─────────────────────────────────────────────
# SPOTIFY CLIENT (for ISRC lookup only)
# ─────────────────────────────────────────────

def get_spotify_client():
    return spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
        redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI",
                               "https://127.0.0.1:1234"),
        scope="playlist-read-private"
    ))


# ─────────────────────────────────────────────
# CACHE HELPERS
# ─────────────────────────────────────────────

def get_cached_path(track_id: str) -> str:
    return os.path.join(AUDIO_CACHE_DIR, f"{track_id}.mp3")


def is_cached(track_id: str) -> bool:
    path = get_cached_path(track_id)
    return os.path.exists(path) and os.path.getsize(path) > 0


# ─────────────────────────────────────────────
# ISRC LOOKUP
# ─────────────────────────────────────────────

def get_isrc(spotify_track_id: str, sp) -> str | None:
    """Get ISRC from Spotify track metadata."""
    try:
        track = sp.track(spotify_track_id)
        isrc  = track.get("external_ids", {}).get("isrc")
        if isrc:
            print(f"    ISRC: {isrc}")
        return isrc
    except Exception as e:
        print(f"    ⚠️  Could not get ISRC: {e}")
        return None


# ─────────────────────────────────────────────
# DEEZER LOOKUP
# ─────────────────────────────────────────────

def find_preview_by_isrc(isrc: str) -> dict | None:
    """
    Find exact track on Deezer using ISRC.
    Returns track info including preview URL or None.
    """
    url = f"https://api.deezer.com/2.0/track/isrc:{isrc}"

    try:
        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            data = response.json()

            if data.get("error") or not data.get("preview"):
                return None

            return {
                "deezer_id":   data.get("id"),
                "title":       data.get("title"),
                "artist":      data.get("artist", {}).get("name"),
                "preview_url": data.get("preview"),
                "duration":    data.get("duration"),
                "source":      "deezer_isrc",
            }

    except Exception as e:
        print(f"    ⚠️  Deezer ISRC lookup failed: {e}")

    return None


def find_preview_by_search(track_name: str,
                            artist: str) -> dict | None:
    """
    Fallback: search Deezer by name/artist if ISRC fails.
    Less accurate but better than YouTube text search.
    """
    url    = "https://api.deezer.com/search"
    query  = f'track:"{track_name}" artist:"{artist}"'
    params = {"q": query, "limit": 3}

    try:
        response = requests.get(url, params=params, timeout=10)
        data     = response.json()

        if not data.get("data"):
            # Try broader search without quotes
            params["q"] = f"{track_name} {artist}"
            response    = requests.get(url, params=params, timeout=10)
            data        = response.json()

        if data.get("data"):
            track = data["data"][0]
            if not track.get("preview"):
                return None

            return {
                "deezer_id":   track["id"],
                "title":       track["title"],
                "artist":      track["artist"]["name"],
                "preview_url": track["preview"],
                "duration":    track["duration"],
                "source":      "deezer_search",
            }

    except Exception as e:
        print(f"    ⚠️  Deezer search failed: {e}")

    return None


def download_preview(preview_url: str,
                     track_id: str) -> str | None:
    """
    Download a Deezer 30s preview MP3.
    Direct link - no yt-dlp needed.
    """
    cached_path = get_cached_path(track_id)

    try:
        response = requests.get(
            preview_url,
            timeout=DOWNLOAD_TIMEOUT_SECS,
            stream=True
        )

        if response.status_code == 200:
            with open(cached_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            if os.path.getsize(cached_path) > 0:
                return cached_path
            else:
                os.remove(cached_path)
                return None

    except Exception as e:
        print(f"    ⚠️  Preview download failed: {e}")

    return None


# ─────────────────────────────────────────────
# MAIN DOWNLOAD FUNCTION
# ─────────────────────────────────────────────

def download_track(track: dict, conn,
                   sp=None, force: bool = False) -> tuple[str | None, str]:
    """
    Download track audio for analysis using ISRC matching.

    Priority order:
    1. Already cached → return immediately
    2. ISRC → Deezer exact match → download 30s preview
    3. Name/artist → Deezer search → download 30s preview
    4. Failed → record failure, return None

    Returns (local_path, source).
    """
    track_id = track["id"]
    name     = track.get("name", "Unknown")
    artists  = track.get("artists", [])
    artist   = artists[0] if artists else ""

    # FIX 1: isrc must be defined before the enrichment call below.
    # Initialise to None here so it's always in scope regardless
    # of which branch runs.
    isrc = None

    # ── Already cached ────────────────────────────────
    if not force and is_cached(track_id):
        return get_cached_path(track_id), "cache"

    # ── Skip previous failures unless forced ──────────
    if not force:
        status = get_download_status(conn, track_id)
        if status and status["download_failed"]:
            print(f"    ⏭️  Previously failed - use --redownload to retry")
            return None, "previously_failed"

    deezer_info = None

    # ── Try ISRC matching first ────────────────────────
    if sp:
        print(f"    🔍 Looking up ISRC...")
        isrc = get_isrc(track_id, sp)

        if isrc:
            print(f"    🔍 Searching Deezer by ISRC...")
            deezer_info = find_preview_by_isrc(isrc)

            if deezer_info:
                print(f"    ✅ Exact match: "
                      f"{deezer_info['title']} - "
                      f"{deezer_info['artist']}")
            else:
                print(f"    ⚠️  ISRC not found on Deezer")

    # ── Fallback to Deezer name search ────────────────
    if not deezer_info:
        print(f"    🔍 Searching Deezer by name...")
        deezer_info = find_preview_by_search(name, artist)

        if deezer_info:
            print(f"    ⚠️  Search match (verify): "
                  f"{deezer_info['title']} - "
                  f"{deezer_info['artist']}")
        else:
            print(f"    ❌ Not found on Deezer")
            save_download_record(
                conn, track_id, None,
                f"ISRC+search: {name} {artist}",
                failed=True,
                failure_reason="not_found_on_deezer"
            )
            return None, "not_found"

    # ── Download preview ──────────────────────────────
    print(f"    ⬇️  Downloading 30s preview...")
    local_path = download_preview(deezer_info["preview_url"], track_id)

    if local_path:
        size_kb = os.path.getsize(local_path) // 1024
        print(f"    ✅ Downloaded ({size_kb} KB) "
              f"via {deezer_info['source']}")

        # FIX 2: save_track_enrichment and save_download_record
        # were called with wrong arguments in your version.
        # save_track_enrichment takes track_id + enrichment fields.
        # save_download_record takes track_id + path + query string.
        # Both are now called correctly and only once each.
        save_track_enrichment(
            conn,
            track_id           = track_id,
            isrc               = isrc,
            deezer_id          = deezer_info.get("deezer_id"),
            deezer_preview_url = deezer_info.get("preview_url"),
        )

        save_download_record(
            conn,
            track_id       = track_id,
            local_path     = local_path,
            search_query   = deezer_info.get("preview_url"),
            failed         = False,
        )

        return local_path, deezer_info["source"]

    else:
        # FIX 3: failure path was correct but kept separate
        # from the success block for clarity
        save_download_record(
            conn,
            track_id       = track_id,
            local_path     = None,
            search_query   = deezer_info.get("preview_url"),
            failed         = True,
            failure_reason = "preview_download_failed",
        )
        return None, "download_failed"


# ─────────────────────────────────────────────
# CACHE MANAGEMENT
# ─────────────────────────────────────────────

def cache_summary(conn):
    files      = list(Path(AUDIO_CACHE_DIR).glob("*.mp3"))
    total_size = sum(f.stat().st_size for f in files)
    size_mb    = total_size / (1024 * 1024)
    unanalysed = [
        f for f in files
        if not is_analysed(conn, f.stem, ANALYSIS_VERSION)
    ]

    print(f"\n{'='*55}")
    print(f"  AUDIO CACHE SUMMARY")
    print(f"{'='*55}")
    print(f"  Files in cache:           {len(files)}")
    print(f"  Total size:               {size_mb:.1f} MB")
    print(f"  Not yet analysed:         {len(unanalysed)}")
    print(f"  Safe to delete:           {len(files) - len(unanalysed)}")


def clear_analysed_cache(conn, dry_run: bool = True):
    files     = list(Path(AUDIO_CACHE_DIR).glob("*.mp3"))
    to_delete = []

    for f in files:
        track_id = f.stem
        if is_analysed(conn, track_id, ANALYSIS_VERSION):
            row = conn.execute("""
                SELECT analysis_failed FROM track_features
                WHERE track_id = ? AND analysis_version = ?
            """, (track_id, ANALYSIS_VERSION)).fetchone()
            if row and not row["analysis_failed"]:
                to_delete.append(f)

    total_mb = sum(f.stat().st_size for f in to_delete) / (1024 * 1024)

    if dry_run:
        print(f"\n  DRY RUN - would delete "
              f"{len(to_delete)} files ({total_mb:.1f} MB)")
        print(f"  Run without --dry-run to delete")
    else:
        print(f"\n  Deleting {len(to_delete)} files ({total_mb:.1f} MB)...")
        for f in to_delete:
            f.unlink()
            print(f"    🗑️  {f.name}")
        print(f"  ✅ Done")