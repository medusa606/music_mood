"""
Smart Read Companion - Central configuration
All paths, constants and settings in one place.
"""

import os

# ─────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────

PLAYLIST_DIR    = "playlist_data"
AUDIO_CACHE_DIR = "audio_cache"
TEMP_DIR        = "temp_audio"
DB_PATH         = "track_features.db"

# ─────────────────────────────────────────────
# ANALYSIS
# ─────────────────────────────────────────────

ANALYSIS_VERSION = "1.0"  # bump when you change analysis logic

# ─────────────────────────────────────────────
# PLAYLISTS
# ─────────────────────────────────────────────

PLAYLIST_FILES = {
    "reading_soundscape": "reading_soundscape.json",
    "space_opera":        "space_opera.json",
    "horror":             "horror.json",
    "space_pirates":      "space_pirates.json",
    "spy_thriller":       "spy_thriller.json",
}

# ─────────────────────────────────────────────
# DOWNLOAD
# ─────────────────────────────────────────────

DOWNLOAD_TIMEOUT_SECS  = 15
DOWNLOAD_RETRIES       = 2
DOWNLOAD_QUALITY_KBPS  = "128"
PAUSE_BETWEEN_TRACKS   = 0.5   # seconds, keeps YouTube happy

# ─────────────────────────────────────────────
# CREATE DIRECTORIES ON IMPORT
# ─────────────────────────────────────────────

for _dir in [PLAYLIST_DIR, AUDIO_CACHE_DIR, TEMP_DIR]:
    os.makedirs(_dir, exist_ok=True)