"""
Smart Read Companion - Database setup and all read/write operations.
All SQL lives here. Nothing else should talk to SQLite directly.
"""

import sqlite3
import json
from datetime import datetime
from config import DB_PATH, ANALYSIS_VERSION


# ─────────────────────────────────────────────
# INIT
# ─────────────────────────────────────────────

def init_database(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    statements = [

        """CREATE TABLE IF NOT EXISTS playlists (
            id            TEXT PRIMARY KEY,
            label         TEXT NOT NULL,
            track_count   INTEGER,
            created_at    TEXT
        )""",

        """CREATE TABLE IF NOT EXISTS tracks (
            id                  TEXT PRIMARY KEY,
            uri                 TEXT,
            name                TEXT NOT NULL,
            artists             TEXT,
            artist_id           TEXT,
            artist_genres       TEXT,
            album               TEXT,
            release_date        TEXT,
            duration_ms         INTEGER,
            spotify_url         TEXT,
            added_at            TEXT,
            isrc                TEXT,
            deezer_id           INTEGER,
            deezer_preview_url  TEXT,
            popularity          INTEGER
        )""",

        """CREATE TABLE IF NOT EXISTS playlist_tracks (
            playlist_id   TEXT NOT NULL,
            track_id      TEXT NOT NULL,
            PRIMARY KEY   (playlist_id, track_id),
            FOREIGN KEY   (playlist_id) REFERENCES playlists(id),
            FOREIGN KEY   (track_id)    REFERENCES tracks(id)
        )""",

        """CREATE TABLE IF NOT EXISTS track_downloads (
            track_id          TEXT PRIMARY KEY,
            local_path        TEXT,
            file_size_bytes   INTEGER,
            download_source   TEXT,
            search_query      TEXT,
            downloaded_at     TEXT,
            download_failed   INTEGER DEFAULT 0,
            failure_reason    TEXT,
            FOREIGN KEY (track_id) REFERENCES tracks(id)
        )""",

        """CREATE TABLE IF NOT EXISTS track_features (
            track_id            TEXT NOT NULL,
            analysis_version    TEXT NOT NULL,
            bpm                 REAL,
            beats_confidence    REAL,
            danceability        REAL,
            loudness            REAL,
            rms_energy          REAL,
            loudness_mean       REAL,
            spectral_centroid   REAL,
            track_key           TEXT,
            track_mode          TEXT,
            key_strength        REAL,
            estimated_valence   REAL,
            estimated_arousal   REAL,
            analysis_source     TEXT,
            analysed_at         TEXT,
            analysis_failed     INTEGER DEFAULT 0,
            failure_reason      TEXT,
            PRIMARY KEY (track_id, analysis_version),
            FOREIGN KEY (track_id) REFERENCES tracks(id)
        )""",

        """CREATE TABLE IF NOT EXISTS track_features_active (
            track_id            TEXT PRIMARY KEY,
            analysis_version    TEXT,
            FOREIGN KEY (track_id) REFERENCES tracks(id)
        )""",

        # ── Indexes ───────────────────────────────────────
        """CREATE INDEX IF NOT EXISTS idx_playlist_tracks_playlist
            ON playlist_tracks(playlist_id)""",

        """CREATE INDEX IF NOT EXISTS idx_features_valence_arousal
            ON track_features(estimated_valence, estimated_arousal)""",

        """CREATE INDEX IF NOT EXISTS idx_downloads_failed
            ON track_downloads(download_failed)""",

        """CREATE INDEX IF NOT EXISTS idx_tracks_isrc
            ON tracks(isrc)""",
    ]

    for statement in statements:
        try:
            conn.execute(statement)
        except sqlite3.OperationalError as e:
            print(f"❌ Schema error:\n{statement}\n\nError: {e}")
            raise

    conn.commit()
    print(f"✅ Database ready: {db_path}")
    return conn


# ─────────────────────────────────────────────
# PLAYLISTS
# ─────────────────────────────────────────────

def save_playlist(conn: sqlite3.Connection, label: str,
                  playlist_id: str, track_count: int):
    conn.execute("""
        INSERT OR REPLACE INTO playlists (id, label, track_count, created_at)
        VALUES (?, ?, ?, ?)
    """, (playlist_id, label, track_count, datetime.utcnow().isoformat()))
    conn.commit()


# ─────────────────────────────────────────────
# TRACKS
# ─────────────────────────────────────────────

def save_track(conn: sqlite3.Connection, track: dict):
    """
    Save core track metadata from Spotify playlist JSON.
    ISRC, Deezer fields and popularity saved separately
    via save_track_enrichment() once we have them.
    """
    conn.execute("""
        INSERT OR REPLACE INTO tracks
        (id, uri, name, artists, artist_id, artist_genres,
         album, release_date, duration_ms, spotify_url, added_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        track["id"],
        track.get("uri"),
        track["name"],
        json.dumps(track.get("artists", [])),
        track.get("artist_id"),
        json.dumps(track.get("artist_genres", [])),
        track.get("album"),
        track.get("release_date"),
        track.get("duration_ms"),
        track.get("spotify_url"),
        track.get("added_at"),
    ))


def save_track_enrichment(conn: sqlite3.Connection, track_id: str,
                           isrc: str = None,
                           deezer_id: int = None,
                           deezer_preview_url: str = None,
                           popularity: int = None):
    """
    Save enrichment fields separately so save_track()
    stays clean and we can update these independently.
    """
    conn.execute("""
        UPDATE tracks SET
            isrc               = COALESCE(?, isrc),
            deezer_id          = COALESCE(?, deezer_id),
            deezer_preview_url = COALESCE(?, deezer_preview_url),
            popularity         = COALESCE(?, popularity)
        WHERE id = ?
    """, (isrc, deezer_id, deezer_preview_url, popularity, track_id))
    conn.commit()


def save_playlist_track_link(conn: sqlite3.Connection,
                              playlist_id: str, track_id: str):
    conn.execute("""
        INSERT OR IGNORE INTO playlist_tracks (playlist_id, track_id)
        VALUES (?, ?)
    """, (playlist_id, track_id))


# ─────────────────────────────────────────────
# DOWNLOADS
# ─────────────────────────────────────────────

def save_download_record(conn: sqlite3.Connection, track_id: str,
                          local_path: str | None, search_query: str,
                          failed: bool = False,
                          failure_reason: str = None):
    import os
    file_size = (
        os.path.getsize(local_path)
        if local_path and os.path.exists(local_path)
        else None
    )
    conn.execute("""
        INSERT OR REPLACE INTO track_downloads
        (track_id, local_path, file_size_bytes, download_source,
         search_query, downloaded_at, download_failed, failure_reason)
        VALUES (?, ?, ?, 'deezer', ?, ?, ?, ?)
    """, (
        track_id,
        local_path,
        file_size,
        search_query,
        datetime.utcnow().isoformat(),
        1 if failed else 0,
        failure_reason,
    ))
    conn.commit()


def get_download_status(conn: sqlite3.Connection,
                         track_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM track_downloads WHERE track_id = ?",
        (track_id,)
    ).fetchone()
    return dict(row) if row else None


# ─────────────────────────────────────────────
# FEATURES
# ─────────────────────────────────────────────

def is_analysed(conn: sqlite3.Connection, track_id: str,
                version: str = ANALYSIS_VERSION) -> bool:
    row = conn.execute("""
        SELECT track_id FROM track_features
        WHERE track_id = ? AND analysis_version = ?
    """, (track_id, version)).fetchone()
    return row is not None


def save_features(conn: sqlite3.Connection, track_id: str,
                  features: dict | None,
                  version: str = ANALYSIS_VERSION,
                  failed: bool = False,
                  failure_reason: str = None):
    now = datetime.utcnow().isoformat()

    if failed or features is None:
        conn.execute("""
            INSERT OR REPLACE INTO track_features
            (track_id, analysis_version, analysis_source,
             analysed_at, analysis_failed, failure_reason)
            VALUES (?, ?, 'essentia', ?, 1, ?)
        """, (track_id, version, now, failure_reason or "unknown"))

    else:
        conn.execute("""
            INSERT OR REPLACE INTO track_features
            (track_id, analysis_version,
             bpm, beats_confidence, danceability,
             loudness, rms_energy, loudness_mean, spectral_centroid,
             track_key, track_mode, key_strength,
             estimated_valence, estimated_arousal,
             analysis_source, analysed_at, analysis_failed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    'essentia', ?, 0)
        """, (
            track_id,
            version,
            features.get("bpm"),
            features.get("beats_confidence"),
            features.get("danceability"),
            features.get("loudness"),
            features.get("rms_energy"),
            features.get("loudness_mean"),
            features.get("spectral_centroid"),
            features.get("track_key"),
            features.get("track_mode"),
            features.get("key_strength"),
            features.get("estimated_valence"),
            features.get("estimated_arousal"),
            now,
        ))

    conn.execute("""
        INSERT OR REPLACE INTO track_features_active
        (track_id, analysis_version)
        VALUES (?, ?)
    """, (track_id, version))

    conn.commit()


# ─────────────────────────────────────────────
# SUMMARY QUERIES
# ─────────────────────────────────────────────

def print_database_summary(conn: sqlite3.Connection):
    total = conn.execute(
        "SELECT COUNT(*) FROM tracks"
    ).fetchone()[0]

    analysed = conn.execute(
        "SELECT COUNT(*) FROM track_features WHERE analysis_failed = 0"
    ).fetchone()[0]

    failed = conn.execute(
        "SELECT COUNT(*) FROM track_features WHERE analysis_failed = 1"
    ).fetchone()[0]

    print(f"\n{'='*55}")
    print(f"  DATABASE SUMMARY")
    print(f"{'='*55}")
    print(f"  Total tracks:          {total}")
    print(f"  Successfully analysed: {analysed}")
    print(f"  Failed:                {failed}")
    print(f"  Not yet processed:     {total - analysed - failed}")

    print(f"\n  Per playlist:")
    rows = conn.execute("""
        SELECT p.label,
               p.track_count,
               COUNT(CASE WHEN tf.analysis_failed = 0 THEN 1 END) AS done,
               COUNT(CASE WHEN tf.analysis_failed = 1 THEN 1 END) AS fails
        FROM playlists p
        LEFT JOIN playlist_tracks pt ON p.id  = pt.playlist_id
        LEFT JOIN track_features  tf ON pt.track_id = tf.track_id
        GROUP BY p.label
    """).fetchall()

    for row in rows:
        print(f"    {row['label']:<20} "
              f"{row['done']:>4} done  "
              f"{row['fails']:>4} failed  "
              f"of {row['track_count']}")

    print(f"\n  Sample results:")
    samples = conn.execute("""
        SELECT t.name, t.artists,
               tf.estimated_valence, tf.estimated_arousal,
               tf.bpm, tf.track_mode
        FROM tracks t
        JOIN track_features tf ON t.id = tf.track_id
        WHERE tf.analysis_failed = 0
        LIMIT 5
    """).fetchall()

    for s in samples:
        artist = json.loads(s["artists"])[0] if s["artists"] else "?"
        print(f"    {s['name'][:35]:<35} | "
              f"{artist[:20]:<20} | "
              f"V={s['estimated_valence']} "
              f"A={s['estimated_arousal']} "
              f"BPM={s['bpm']} "
              f"{s['track_mode']}")