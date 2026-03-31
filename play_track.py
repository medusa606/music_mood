"""
play_track.py
Play cached tracks to verify yt-dlp downloaded the correct audio.

Usage:
    python play_track.py --playlist horror
    python play_track.py --track <spotify_id>
    python play_track.py --playlist horror --skip 3  # start from track 4
"""

import os
import sys
import sqlite3
import json
import subprocess
import argparse
from config import DB_PATH, AUDIO_CACHE_DIR


def play_track(mp3_path: str) -> subprocess.Popen:
    """Play an mp3 using ffplay. Returns process handle."""
    return subprocess.Popen(
        ['ffplay', '-nodisp', '-autoexit', '-loglevel', 'quiet', mp3_path]
    )


def stop_track(process: subprocess.Popen):
    """Stop currently playing track."""
    if process and process.poll() is None:
        process.terminate()


def get_playlist_tracks(conn: sqlite3.Connection, label: str) -> list:
    rows = conn.execute("""
        SELECT t.id, t.name, t.artists, t.album,
               tf.estimated_valence, tf.estimated_arousal,
               tf.bpm, tf.track_mode, tf.track_key
        FROM tracks t
        JOIN playlist_tracks pt ON t.id  = pt.track_id
        JOIN playlists p        ON pt.playlist_id = p.id
        LEFT JOIN track_features tf ON t.id = tf.track_id
            AND tf.analysis_version = '1.0'
        WHERE p.label = ?
        ORDER BY t.name
    """, (label,)).fetchall()
    return [dict(r) for r in rows]


def print_track_info(track: dict, index: int, total: int):
    """Print track details."""
    artists = json.loads(track["artists"]) if track["artists"] else []
    artist  = artists[0] if artists else "Unknown"

    print(f"\n  {'─'*50}")
    print(f"  [{index}/{total}] {track['name']}")
    print(f"  Artist  : {artist}")
    print(f"  Album   : {track.get('album', '?')}")
    print(f"  ID      : {track['id']}")

    if track.get("estimated_valence") is not None:
        print(f"  Essentia: V={track['estimated_valence']} "
              f"A={track['estimated_arousal']} "
              f"BPM={track['bpm']} "
              f"{track['track_mode']} {track['track_key']}")
    else:
        print(f"  Essentia: no data")


def verify_playlist(label: str, skip: int = 0):
    """
    Play through a playlist for manual verification.
    Shows track info, plays audio, waits for input.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    tracks = get_playlist_tracks(conn, label)
    if not tracks:
        print(f"❌ No tracks found for playlist: {label}")
        return

    if skip:
        tracks = tracks[skip:]
        print(f"  ⚠️  Skipping first {skip} tracks")

    total   = len(tracks)
    current_process = None

    print(f"\n{'═'*55}")
    print(f"  PLAYBACK VERIFICATION: {label}")
    print(f"  {total} tracks")
    print(f"{'═'*55}")
    print(f"\n  Controls:")
    print(f"    ENTER     → next track (stops current)")
    print(f"    s         → stop playback")
    print(f"    w         → flag as WRONG track")
    print(f"    r         → flag as needs REVIEW")
    print(f"    q         → quit")

    flagged = {"wrong": [], "review": []}

    for i, track in enumerate(tracks):
        track_id = track["id"]
        mp3_path = os.path.join(AUDIO_CACHE_DIR, f"{track_id}.mp3")

        # Stop previous track
        stop_track(current_process)

        print_track_info(track, i + 1 + skip, total + skip)

        if not os.path.exists(mp3_path):
            print(f"  ⚠️  Not cached - skipping")
            continue

        file_kb = os.path.getsize(mp3_path) // 1024
        print(f"  Cache   : {file_kb} KB")
        print(f"\n  ▶  Playing...")

        # Start playing
        current_process = play_track(mp3_path)

        # Wait for input
        try:
            cmd = input("  > ").strip().lower()
        except KeyboardInterrupt:
            stop_track(current_process)
            print("\n  Interrupted")
            break

        stop_track(current_process)

        if cmd == 'q':
            print("\n  Quitting...")
            break
        elif cmd == 'w':
            flagged["wrong"].append({
                "id": track_id, "name": track["name"]
            })
            print(f"  🚩 Flagged as WRONG TRACK")
        elif cmd == 'r':
            flagged["review"].append({
                "id": track_id, "name": track["name"]
            })
            print(f"  🔍 Flagged for REVIEW")
        elif cmd == 's':
            print(f"  ⏹  Stopped")
            # Wait for next enter before moving on
            input("  Press ENTER for next track...")

    # Print summary of flags
    print(f"\n{'═'*55}")
    print(f"  VERIFICATION SUMMARY")
    print(f"{'═'*55}")

    if flagged["wrong"]:
        print(f"\n  🚩 Wrong tracks ({len(flagged['wrong'])}):")
        for t in flagged["wrong"]:
            print(f"     {t['name']} | {t['id']}")

    if flagged["review"]:
        print(f"\n  🔍 Needs review ({len(flagged['review'])}):")
        for t in flagged["review"]:
            print(f"     {t['name']} | {t['id']}")

    if not flagged["wrong"] and not flagged["review"]:
        print(f"\n  ✅ All tracks verified")

    # Save flags to JSON for reference
    if flagged["wrong"] or flagged["review"]:
        import json
        flag_file = f"{label}_flags.json"
        with open(flag_file, "w") as f:
            json.dump(flagged, f, indent=2)
        print(f"\n  Flags saved to {flag_file}")

    conn.close()


def play_single_track(track_id: str):
    """Play a single track by Spotify ID."""
    mp3_path = os.path.join(AUDIO_CACHE_DIR, f"{track_id}.mp3")

    if not os.path.exists(mp3_path):
        print(f"❌ Not cached: {mp3_path}")
        print(f"   Run main.py to download first")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    track = conn.execute(
        "SELECT * FROM tracks WHERE id = ?", (track_id,)
    ).fetchone()

    if track:
        artists = json.loads(track["artists"]) if track["artists"] else []
        print(f"\n  ▶  {track['name']} - {artists[0] if artists else '?'}")

    print(f"  Playing {mp3_path}...")
    process = play_track(mp3_path)

    try:
        process.wait()  # wait until track finishes
    except KeyboardInterrupt:
        stop_track(process)

    conn.close()


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Play cached tracks for verification"
    )
    parser.add_argument("--playlist", type=str, default=None,
                        help="Playlist label to verify")
    parser.add_argument("--track",    type=str, default=None,
                        help="Single track ID to play")
    parser.add_argument("--skip",     type=int, default=0,
                        help="Skip first N tracks")
    args = parser.parse_args()

    if args.track:
        play_single_track(args.track)

    elif args.playlist:
        verify_playlist(args.playlist, skip=args.skip)

    else:
        parser.print_help()