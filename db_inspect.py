"""
db_inspect.py

Detailed database inspection tool.
Check data quality, completeness and consistency.

Usage:
    python db_inspect.py                    # full report
    python db_inspect.py --playlist horror  # one playlist
    python db_inspect.py --track <id>       # single track detail
"""

import sqlite3
import json
import argparse
from config import DB_PATH, ANALYSIS_VERSION


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ─────────────────────────────────────────────
# INSPECTION QUERIES
# ─────────────────────────────────────────────

def check_va_scores(conn: sqlite3.Connection, label: str = None):
    """
    Verify VA scores are saved and within expected ranges.
    Flags anything that looks wrong.
    """
    print(f"\n{'═'*60}")
    print(f"  VA SCORE VERIFICATION"
          + (f" - {label}" if label else " - ALL PLAYLISTS"))
    print(f"{'═'*60}")

    where = "WHERE p.label = ?" if label else ""
    params = (label,) if label else ()

    rows = conn.execute(f"""
        SELECT 
            t.name,
            t.artists,
            p.label,
            tf.estimated_valence,
            tf.estimated_arousal,
            tf.bpm,
            tf.track_mode,
            tf.track_key,
            tf.rms_energy,
            tf.loudness,
            tf.spectral_centroid,
            tf.beats_confidence,
            tf.danceability,
            tf.key_strength,
            tf.loudness_mean,
            tf.analysis_version,
            tf.analysed_at,
            tf.analysis_failed,
            tf.failure_reason
        FROM tracks t
        JOIN playlist_tracks pt ON t.id = pt.track_id
        JOIN playlists p        ON pt.playlist_id = p.id
        LEFT JOIN track_features tf ON t.id = tf.track_id
        {where}
        ORDER BY p.label, t.name
    """, params).fetchall()

    if not rows:
        print(f"  ❌ No tracks found")
        return

    issues   = []
    ok_count = 0

    for row in rows:
        name    = row["name"]
        artists = json.loads(row["artists"]) if row["artists"] else []
        artist  = artists[0] if artists else "?"
        label_  = row["label"]

        # ── Check for missing features ────────────────────
        if row["analysis_failed"]:
            issues.append(f"  🔴 FAILED   | {label_:<15} | "
                          f"{name[:35]:<35} | {row['failure_reason']}")
            continue

        if row["estimated_valence"] is None:
            issues.append(f"  🔴 NULL VA  | {label_:<15} | "
                          f"{name[:35]:<35} | no features saved")
            continue

        # ── Check VA ranges (should be 0.0 - 1.0) ────────
        v = row["estimated_valence"]
        a = row["estimated_arousal"]

        if not (0.0 <= v <= 1.0):
            issues.append(f"  🟡 BAD V    | {label_:<15} | "
                          f"{name[:35]:<35} | V={v} out of range")

        if not (0.0 <= a <= 1.0):
            issues.append(f"  🟡 BAD A    | {label_:<15} | "
                          f"{name[:35]:<35} | A={a} out of range")

        # ── Check BPM is sensible ─────────────────────────
        bpm = row["bpm"]
        if bpm and not (20 <= bpm <= 300):
            issues.append(f"  🟡 BAD BPM  | {label_:<15} | "
                          f"{name[:35]:<35} | BPM={bpm}")

        # ── Check nothing critical is null ────────────────
        critical_fields = ["bpm", "rms_energy", "track_mode", "track_key"]
        for field in critical_fields:
            if row[field] is None:
                issues.append(f"  🟡 NULL     | {label_:<15} | "
                              f"{name[:35]:<35} | {field} is null")

        # ── Print the row ─────────────────────────────────
        v_bar = "█" * int(v * 20)
        a_bar = "█" * int(a * 20)

        print(f"\n  {name[:45]}")
        print(f"  {artist[:45]}")
        print(f"  Playlist : {label_}")
        print(f"  Version  : {row['analysis_version']} "
              f"| Analysed: {row['analysed_at']}")
        print(f"  ┌─────────────────────────────────────")
        print(f"  │ Valence  {v:.3f}  {v_bar:<20} "
              f"{'dark/negative' if v < 0.35 else 'neutral' if v < 0.65 else 'bright/positive'}")
        print(f"  │ Arousal  {a:.3f}  {a_bar:<20} "
              f"{'calm' if a < 0.35 else 'moderate' if a < 0.65 else 'intense'}")
        print(f"  │ BPM      {row['bpm']}")
        print(f"  │ Mode     {row['track_mode']}  "
              f"Key: {row['track_key']}")
        print(f"  │ RMS      {row['rms_energy']}")
        print(f"  │ Loudness {row['loudness']} "
              f"(mean: {row['loudness_mean']})")
        print(f"  │ Centroid {row['spectral_centroid']}")
        print(f"  │ Dance    {row['danceability']}")
        print(f"  │ BeatConf {row['beats_confidence']}")
        print(f"  └─────────────────────────────────────")
        ok_count += 1

    # ── Issues summary ────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"  Total: {len(rows)} | OK: {ok_count} | Issues: {len(issues)}")

    if issues:
        print(f"\n  ⚠️  ISSUES FOUND:")
        for issue in issues:
            print(issue)
    else:
        print(f"\n  ✅ All VA scores look valid")


def check_completeness(conn: sqlite3.Connection):
    """
    Check what percentage of tracks have been processed.
    """
    print(f"\n{'═'*60}")
    print(f"  COMPLETENESS REPORT")
    print(f"{'═'*60}")

    rows = conn.execute("""
        SELECT 
            p.label,
            p.track_count                                    AS total,
            COUNT(t.id)                                      AS in_db,
            COUNT(td.track_id)                               AS downloaded,
            COUNT(CASE WHEN td.download_failed = 0 
                       THEN 1 END)                           AS dl_ok,
            COUNT(CASE WHEN td.download_failed = 1 
                       THEN 1 END)                           AS dl_failed,
            COUNT(CASE WHEN tf.analysis_failed = 0 
                       THEN 1 END)                           AS analysed,
            COUNT(CASE WHEN tf.analysis_failed = 1 
                       THEN 1 END)                           AS analyse_failed
        FROM playlists p
        LEFT JOIN playlist_tracks pt ON p.id  = pt.playlist_id
        LEFT JOIN tracks t           ON pt.track_id = t.id
        LEFT JOIN track_downloads td ON t.id  = td.track_id
        LEFT JOIN track_features  tf ON t.id  = tf.track_id
        GROUP BY p.label
        ORDER BY p.label
    """).fetchall()

    for row in rows:
        total     = row["total"] or 0
        analysed  = row["analysed"] or 0
        dl_ok     = row["dl_ok"] or 0
        dl_failed = row["dl_failed"] or 0
        pct       = round(analysed / total * 100) if total else 0
        bar       = "█" * (pct // 5) + "░" * (20 - pct // 5)

        print(f"\n  {row['label']}")
        print(f"  [{bar}] {pct}%")
        print(f"  Total in playlist : {total}")
        print(f"  In database       : {row['in_db']}")
        print(f"  Downloaded OK     : {dl_ok}")
        print(f"  Download failed   : {dl_failed}")
        print(f"  Analysed OK       : {analysed}")
        print(f"  Analysis failed   : {row['analyse_failed']}")

        not_started = total - (dl_ok + dl_failed)
        if not_started > 0:
            print(f"  Not yet started   : {not_started}")


def check_download_sources(conn: sqlite3.Connection):
    """
    Check how tracks were matched - ISRC vs search fallback.
    Search matches are less reliable and worth reviewing.
    """
    print(f"\n{'═'*60}")
    print(f"  DOWNLOAD SOURCE REPORT")
    print(f"{'═'*60}")

    rows = conn.execute("""
        SELECT t.name, t.artists, p.label,
               td.download_source, td.search_query,
               td.download_failed, td.failure_reason
        FROM tracks t
        JOIN playlist_tracks pt ON t.id = pt.track_id
        JOIN playlists p        ON pt.playlist_id = p.id
        LEFT JOIN track_downloads td ON t.id = td.track_id
        ORDER BY td.download_source, p.label, t.name
    """).fetchall()

    sources = {}
    for row in rows:
        source = row["download_source"] or "not_downloaded"
        if source not in sources:
            sources[source] = []
        sources[source].append(row)

    for source, tracks in sources.items():
        icon = {
            "deezer_isrc":   "✅",
            "deezer_search": "⚠️ ",
            "not_downloaded": "⬜",
            "youtube":       "❌",
        }.get(source, "❓")

        print(f"\n  {icon} {source.upper()} ({len(tracks)} tracks)")

        if source == "deezer_search":
            print(f"     ↳ These used name search not ISRC")
            print(f"       Verify these are correct tracks:")

        for row in tracks:
            artists = json.loads(row["artists"]) if row["artists"] else []
            artist  = artists[0] if artists else "?"
            print(f"     {row['label']:<15} {row['name'][:35]:<35} "
                  f"| {artist[:20]}")


def check_single_track(conn: sqlite3.Connection, track_id: str):
    """Full detail on a single track."""
    print(f"\n{'═'*60}")
    print(f"  TRACK DETAIL: {track_id}")
    print(f"{'═'*60}")

    track = conn.execute(
        "SELECT * FROM tracks WHERE id = ?", (track_id,)
    ).fetchone()

    if not track:
        print(f"  ❌ Track not found in database")
        return

    print(f"\n  METADATA:")
    for key in track.keys():
        val = track[key]
        if key == "artists":
            val = json.loads(val) if val else []
        print(f"    {key:<20} {val}")

    features = conn.execute(
        "SELECT * FROM track_features WHERE track_id = ?",
        (track_id,)
    ).fetchall()

    print(f"\n  FEATURES ({len(features)} version(s)):")
    for feat in features:
        print(f"\n    Version: {feat['analysis_version']}")
        for key in feat.keys():
            if key != "track_id":
                print(f"      {key:<25} {feat[key]}")

    download = conn.execute(
        "SELECT * FROM track_downloads WHERE track_id = ?",
        (track_id,)
    ).fetchone()

    print(f"\n  DOWNLOAD:")
    if download:
        for key in download.keys():
            if key != "track_id":
                print(f"    {key:<25} {download[key]}")
    else:
        print(f"    No download record")


def check_va_distribution(conn: sqlite3.Connection):
    """
    Show VA distribution across all analysed tracks.
    Useful for seeing if scores cluster oddly.
    """
    print(f"\n{'═'*60}")
    print(f"  VA DISTRIBUTION")
    print(f"{'═'*60}")

    rows = conn.execute("""
        SELECT p.label,
               ROUND(AVG(tf.estimated_valence), 3) AS avg_v,
               ROUND(MIN(tf.estimated_valence), 3) AS min_v,
               ROUND(MAX(tf.estimated_valence), 3) AS max_v,
               ROUND(AVG(tf.estimated_arousal), 3) AS avg_a,
               ROUND(MIN(tf.estimated_arousal), 3) AS min_a,
               ROUND(MAX(tf.estimated_arousal), 3) AS max_a,
               ROUND(AVG(tf.bpm), 1)               AS avg_bpm,
               COUNT(*)                             AS track_count
        FROM track_features tf
        JOIN playlist_tracks pt ON tf.track_id = pt.track_id
        JOIN playlists p        ON pt.playlist_id = p.id
        WHERE tf.analysis_failed = 0
        GROUP BY p.label
    """).fetchall()

    for row in rows:
        print(f"\n  {row['label']} ({row['track_count']} tracks)")
        print(f"  {'─'*40}")
        print(f"  Valence  avg={row['avg_v']}  "
              f"range=[{row['min_v']} → {row['max_v']}]")
        print(f"  Arousal  avg={row['avg_a']}  "
              f"range=[{row['min_a']} → {row['max_a']}]")
        print(f"  BPM      avg={row['avg_bpm']}")

        # Visual VA position
        v = row["avg_v"] or 0
        a = row["avg_a"] or 0
        quadrant = (
            "dark + calm      (melancholic, atmospheric)" if v < 0.5 and a < 0.5 else
            "dark + intense   (threatening, dramatic)"   if v < 0.5 and a >= 0.5 else
            "bright + calm    (peaceful, tender)"        if v >= 0.5 and a < 0.5 else
            "bright + intense (exciting, triumphant)"
        )
        print(f"  Profile  {quadrant}")


# ─────────────────────────────────────────────
# WHAT ELSE SHOULD WE BE SAVING?
# ─────────────────────────────────────────────

def check_missing_metadata(conn: sqlite3.Connection):
    """
    Check for metadata fields that are empty
    but could be populated from Spotify.
    """
    print(f"\n{'═'*60}")
    print(f"  METADATA COMPLETENESS")
    print(f"{'═'*60}")

    fields = [
        ("uri",          "Spotify URI - needed for playback"),
        ("artist_id",    "Artist ID - needed for genre lookup"),
        ("artist_genres","Artist genres - useful for matching"),
        ("album",        "Album name"),
        ("release_date", "Release date"),
        ("duration_ms",  "Track duration"),
    ]

    for field, description in fields:
        count = conn.execute(f"""
            SELECT COUNT(*) FROM tracks
            WHERE {field} IS NULL OR {field} = '' OR {field} = '[]'
        """).fetchone()[0]

        total = conn.execute(
            "SELECT COUNT(*) FROM tracks"
        ).fetchone()[0]

        pct  = round(count / total * 100) if total else 0
        icon = "✅" if count == 0 else "⚠️ " if pct < 20 else "❌"

        print(f"  {icon} {field:<20} "
              f"{count:>4}/{total} missing ({pct}%)  "
              f"→ {description}")


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Database inspection and data quality checks"
    )
    parser.add_argument("--playlist", type=str, default=None,
                        help="Check specific playlist")
    parser.add_argument("--track",    type=str, default=None,
                        help="Check single track by ID")
    parser.add_argument("--va",       action="store_true",
                        help="VA score verification only")
    parser.add_argument("--sources",  action="store_true",
                        help="Download source report only")
    parser.add_argument("--dist",     action="store_true",
                        help="VA distribution report only")
    args = parser.parse_args()

    conn = get_conn()

    if args.track:
        check_single_track(conn, args.track)

    elif args.va:
        check_va_scores(conn, args.playlist)

    elif args.sources:
        check_download_sources(conn)

    elif args.dist:
        check_va_distribution(conn)

    else:
        # Full report
        check_completeness(conn)
        check_va_scores(conn, args.playlist)
        check_download_sources(conn)
        check_va_distribution(conn)
        check_missing_metadata(conn)

    conn.close()


if __name__ == "__main__":
    main()