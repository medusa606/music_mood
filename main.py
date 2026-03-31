"""
project_root/
│
├── config.py     All settings and paths. Edit this, nothing else.
├── database.py   All SQLite operations. Nothing else touches the DB.
├── downloader.py yt-dlp downloads and cache management.
├── analyser.py   Essentia analysis. Swap this to change analysis tool.
├── pipeline.py   Orchestration. Calls the other modules in order.
├── main.py       Entry point and CLI arguments only.
"""

"""
Smart Read Companion - Entry point.
Run this file. All commands go through here.

Usage:
    python main.py                              # process all playlists
    python main.py --playlist horror            # one playlist
    python main.py --playlist horror --limit 5  # test run
    python main.py --reanalyse                  # re-analyse, skip downloads
    python main.py --redownload                 # force re-download everything
    python main.py --summary                    # database summary
    python main.py --cache                      # cache status
    python main.py --clear-cache                # delete analysed audio
    python main.py --clear-cache --dry-run      # preview what would be deleted
"""

import argparse
from config import DB_PATH, PLAYLIST_FILES
from database import init_database, print_database_summary
from downloader import cache_summary, clear_analysed_cache
from pipeline import process_playlist, process_all
import os
from config import PLAYLIST_DIR


def main():
    parser = argparse.ArgumentParser(
        description="Smart Read Companion - Track Analysis Pipeline"
    )
    parser.add_argument("--playlist",    type=str,
                        help="Process one playlist by label")
    parser.add_argument("--limit",       type=int,
                        help="Limit tracks per playlist (for testing)")
    parser.add_argument("--redownload",  action="store_true",
                        help="Force re-download even if cached")
    parser.add_argument("--reanalyse",   action="store_true",
                        help="Re-analyse even if already done")
    parser.add_argument("--summary",     action="store_true",
                        help="Print database summary and exit")
    parser.add_argument("--cache",       action="store_true",
                        help="Print cache status and exit")
    parser.add_argument("--clear-cache", action="store_true",
                        help="Delete audio files for analysed tracks")
    parser.add_argument("--dry-run",     action="store_true",
                        help="Use with --clear-cache to preview only")
    args = parser.parse_args()

    conn = init_database(DB_PATH)

    if args.summary:
        print_database_summary(conn)

    elif args.cache:
        cache_summary(conn)

    elif args.clear_cache:
        clear_analysed_cache(conn, dry_run=args.dry_run)

    elif args.playlist:
        if args.playlist not in PLAYLIST_FILES:
            print(f"❌ Unknown playlist: '{args.playlist}'")
            print(f"   Available: {list(PLAYLIST_FILES.keys())}")
        else:
            json_path = os.path.join(PLAYLIST_DIR, PLAYLIST_FILES[args.playlist])
            process_playlist(
                conn, args.playlist, json_path,
                limit=args.limit,
                redownload=args.redownload,
                reanalyse=args.reanalyse,
            )
            print_database_summary(conn)

    else:
        process_all(
            conn,
            limit=args.limit,
            redownload=args.redownload,
            reanalyse=args.reanalyse,
        )
        print_database_summary(conn)

    conn.close()
    print(f"\n✅ Done. Database: {DB_PATH}\n")


if __name__ == "__main__":
    main()