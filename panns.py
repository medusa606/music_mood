from panns_inference import AudioTagging
at = AudioTagging(checkpoint_path=None, device='cpu')
print("Model ready")


"""
panns_test.py  (renamed from musicnn_test.py)

Runs PANNs audio tagging on cached tracks and compares
to existing Essentia features.

PANNs is trained on Google AudioSet - 527 tags including
mood, genre, instruments and sonic characteristics.

Usage:
    python panns_test.py                        # horror playlist
    python panns_test.py --playlist spy_thriller
    python panns_test.py --save results.json
"""

import os
import json
import argparse
import sqlite3
import numpy as np
import librosa

from panns_inference import AudioTagging
from config import AUDIO_CACHE_DIR, DB_PATH, ANALYSIS_VERSION


# ─────────────────────────────────────────────
# TAGS WE CARE ABOUT
# AudioSet has 527 tags - filter to relevant ones
# ─────────────────────────────────────────────

# Full list at:
# https://github.com/qiuqiangkong/audioset_tagging_cnn/blob/master/metadata/class_labels_indices.csv

MOOD_TAGS = [
    'Scary music',
    'Tense music',
    'Exciting music',
    'Tender music',
    'Sad music',
    'Happy music',
    'Angry music',
    'Funny music',
    'Melancholy',
]

TEXTURE_TAGS = [
    'Silence',
    'Noise',
    'Drone',
    'Cacophony',
    'Eruption',
]

INSTRUMENT_TAGS = [
    'Orchestra',
    'String section',
    'Choir',
    'Brass instrument',
    'Percussion',
    'Piano',
    'Synthesizer',
    'Violin, fiddle',
    'Cello',
]

ENERGY_TAGS = [
    'Loud',
    'Soft',
    'Lullaby',
    'March',
    'Theme music',
    'Background music',
    'Film score',
    'Soundtrack music',
]

ALL_RELEVANT_TAGS = MOOD_TAGS + TEXTURE_TAGS + INSTRUMENT_TAGS + ENERGY_TAGS


# ─────────────────────────────────────────────
# MODEL SETUP
# ─────────────────────────────────────────────

def load_model() -> AudioTagging:
    """Load PANNs model. Downloads on first run (~80MB)."""
    print("  Loading PANNs model (downloads on first run)...")
    model = AudioTagging(checkpoint_path=None, device='cpu')
    print("  ✅ Model ready")
    return model


# ─────────────────────────────────────────────
# ANALYSIS
# ─────────────────────────────────────────────

def run_panns(mp3_path: str, model: AudioTagging) -> dict | None:
    """
    Run PANNs on a single track.
    Returns all 527 tags with confidence scores.
    """
    try:
        # PANNs expects mono audio at 32kHz
        audio, sr = librosa.load(mp3_path, sr=32000, mono=True)

        # PANNs expects shape (batch, samples)
        audio_input = audio[np.newaxis, :]

        # Run inference
        clipwise_output, embedding = model.inference(audio_input)

        # clipwise_output shape: (1, 527)
        scores = clipwise_output[0]

        # Get class labels
        labels = model.labels

        # Build full tag dict
        all_tags = {
            label: round(float(score), 4)
            for label, score in zip(labels, scores)
        }

        # Sort by score
        sorted_tags = dict(
            sorted(all_tags.items(), key=lambda x: x[1], reverse=True)
        )

        # Filter to relevant tags
        relevant_tags = {
            tag: all_tags[tag]
            for tag in ALL_RELEVANT_TAGS
            if tag in all_tags
        }

        relevant_sorted = dict(
            sorted(relevant_tags.items(), key=lambda x: x[1], reverse=True)
        )

        return {
            "top_10_overall":  list(sorted_tags.items())[:10],
            "mood_tags":       {t: all_tags.get(t, 0.0) for t in MOOD_TAGS},
            "texture_tags":    {t: all_tags.get(t, 0.0) for t in TEXTURE_TAGS},
            "instrument_tags": {t: all_tags.get(t, 0.0) for t in INSTRUMENT_TAGS},
            "energy_tags":     {t: all_tags.get(t, 0.0) for t in ENERGY_TAGS},
            "relevant_sorted": relevant_sorted,
            "all_tags":        sorted_tags,
        }

    except Exception as e:
        print(f"    ❌ PANNs failed: {e}")
        return None


def derive_va_from_panns(panns_result: dict) -> dict:
    """
    Derive valence and arousal estimates from PANNs tags.
    Much richer signal than key/mode alone.
    """
    if not panns_result:
        return {}

    mood = panns_result.get("mood_tags", {})
    energy = panns_result.get("energy_tags", {})

    # ── Valence ──────────────────────────────────────────
    # Positive signals
    happy      = mood.get("Happy music", 0)
    exciting   = mood.get("Exciting music", 0)
    tender     = mood.get("Tender music", 0)
    funny      = mood.get("Funny music", 0)

    # Negative signals
    scary      = mood.get("Scary music", 0)
    tense      = mood.get("Tense music", 0)
    sad        = mood.get("Sad music", 0)
    angry      = mood.get("Angry music", 0)
    melancholy = mood.get("Melancholy", 0)

    positive_pull = (happy * 0.35 + exciting * 0.25 +
                     tender * 0.25 + funny * 0.15)

    negative_pull = (scary * 0.30 + tense * 0.25 +
                     angry * 0.25 + sad * 0.10 +
                     melancholy * 0.10)

    valence = 0.5 + (positive_pull * 0.5) - (negative_pull * 0.5)
    valence = round(min(max(valence, 0.0), 1.0), 3)

    # ── Arousal ───────────────────────────────────────────
    # High arousal signals
    loud      = energy.get("Loud", 0)
    march     = energy.get("March", 0)
    exciting2 = mood.get("Exciting music", 0)
    angry2    = mood.get("Angry music", 0)

    # Low arousal signals
    soft       = energy.get("Soft", 0)
    lullaby    = energy.get("Lullaby", 0)
    background = energy.get("Background music", 0)

    arousal_up   = (loud * 0.35 + exciting2 * 0.30 +
                    march * 0.20 + angry2 * 0.15)
    arousal_down = (soft * 0.50 + lullaby * 0.30 +
                    background * 0.20)

    arousal = 0.5 + (arousal_up * 0.5) - (arousal_down * 0.5)
    arousal = round(min(max(arousal, 0.0), 1.0), 3)

    return {
        "panns_valence": valence,
        "panns_arousal": arousal,
    }


# ─────────────────────────────────────────────
# DISPLAY
# ─────────────────────────────────────────────

def print_results(name: str, artist: str,
                  essentia: dict | None,
                  panns: dict | None):
    """Print formatted comparison."""

    print(f"\n  {'═'*55}")
    print(f"  🎵 {name}")
    print(f"     {artist}")
    print(f"  {'═'*55}")

    # ── Essentia ─────────────────────────────────────────
    if essentia:
        print(f"\n  ESSENTIA (structural):")
        print(f"    valence  : {essentia.get('estimated_valence')}  "
              f"{'█' * int((essentia.get('estimated_valence') or 0) * 20)}")
        print(f"    arousal  : {essentia.get('estimated_arousal')}  "
              f"{'█' * int((essentia.get('estimated_arousal') or 0) * 20)}")
        print(f"    BPM      : {essentia.get('bpm')}")
        print(f"    mode     : {essentia.get('track_mode')}")
        print(f"    key      : {essentia.get('track_key')}")
    else:
        print(f"\n  ESSENTIA: no data")

    # ── PANNs ─────────────────────────────────────────────
    if panns:
        va = derive_va_from_panns(panns)

        print(f"\n  PANNs (semantic tags):")
        print(f"    panns_valence : {va.get('panns_valence')}  "
              f"{'█' * int((va.get('panns_valence') or 0) * 20)}")
        print(f"    panns_arousal : {va.get('panns_arousal')}  "
              f"{'█' * int((va.get('panns_arousal') or 0) * 20)}")

        print(f"\n    Top 10 overall tags:")
        for tag, score in panns["top_10_overall"]:
            bar = "█" * int(score * 40)
            print(f"      {tag:<30} {score:.3f}  {bar}")

        print(f"\n    Mood tags:")
        for tag, score in sorted(panns["mood_tags"].items(),
                                  key=lambda x: x[1], reverse=True):
            bar = "█" * int(score * 40)
            print(f"      {tag:<30} {score:.3f}  {bar}")

        print(f"\n    Instrument tags:")
        for tag, score in sorted(panns["instrument_tags"].items(),
                                  key=lambda x: x[1], reverse=True):
            if score > 0.05:  # only show meaningful scores
                bar = "█" * int(score * 40)
                print(f"      {tag:<30} {score:.3f}  {bar}")

        # ── Comparison ────────────────────────────────────
        if essentia:
            print(f"\n  COMPARISON:")
            e_v = essentia.get('estimated_valence') or 0
            e_a = essentia.get('estimated_arousal') or 0
            p_v = va.get('panns_valence') or 0
            p_a = va.get('panns_arousal') or 0

            v_diff = abs(e_v - p_v)
            a_diff = abs(e_a - p_a)

            v_flag = "⚠️  DISAGREE" if v_diff > 0.2 else "✅ agree"
            a_flag = "⚠️  DISAGREE" if a_diff > 0.2 else "✅ agree"

            print(f"    Valence: essentia={e_v}  panns={p_v}  "
                  f"diff={v_diff:.3f}  {v_flag}")
            print(f"    Arousal: essentia={e_a}  panns={p_a}  "
                  f"diff={a_diff:.3f}  {a_flag}")

            if v_diff > 0.2:
                print(f"\n    ℹ️  Large valence disagreement.")
                print(f"       Essentia uses key/mode (structural)")
                print(f"       PANNs uses learned audio patterns (semantic)")
                print(f"       PANNs is likely more accurate for mood")
    else:
        print(f"\n  PANNs: analysis failed")


# ─────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────

def get_essentia_features(conn: sqlite3.Connection,
                           track_id: str) -> dict | None:
    row = conn.execute("""
        SELECT * FROM track_features
        WHERE track_id = ? AND analysis_version = ?
          AND analysis_failed = 0
    """, (track_id, ANALYSIS_VERSION)).fetchone()
    return dict(row) if row else None


def get_playlist_tracks(conn: sqlite3.Connection,
                         label: str) -> list:
    rows = conn.execute("""
        SELECT t.id, t.name, t.artists
        FROM tracks t
        JOIN playlist_tracks pt ON t.id = pt.track_id
        JOIN playlists p        ON pt.playlist_id = p.id
        WHERE p.label = ?
    """, (label,)).fetchall()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="PANNs audio tagging test"
    )
    parser.add_argument("--playlist", type=str, default="horror",
                        help="Playlist to test (default: horror)")
    parser.add_argument("--save",     type=str, default=None,
                        help="Save results to JSON")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    tracks = get_playlist_tracks(conn, args.playlist)
    if not tracks:
        print(f"❌ No tracks found for: {args.playlist}")
        print(f"   Run main.py --playlist {args.playlist} --limit 5 first")
        return

    print(f"\n{'═'*55}")
    print(f"  PANNs TEST  |  playlist: {args.playlist}")
    print(f"  Tracks: {len(tracks)}")
    print(f"{'═'*55}")

    # Load model once, reuse for all tracks
    model = load_model()

    all_results = []

    for track in tracks:
        track_id = track["id"]
        name     = track["name"]
        artists  = json.loads(track["artists"]) if track["artists"] else []
        artist   = artists[0] if artists else "Unknown"

        mp3_path = os.path.join(AUDIO_CACHE_DIR, f"{track_id}.mp3")

        if not os.path.exists(mp3_path):
            print(f"\n  ⏭️  {name} - not cached, skipping")
            continue

        print(f"\n  Analysing: {name[:50]}...")
        panns    = run_panns(mp3_path, model)
        essentia = get_essentia_features(conn, track_id)

        print_results(name, artist, essentia, panns)

        all_results.append({
            "track_id": track_id,
            "name":     name,
            "artist":   artist,
            "essentia": essentia,
            "panns":    panns,
            "derived":  derive_va_from_panns(panns) if panns else {},
        })

    if args.save:
        def serialise(obj):
            if isinstance(obj, (np.floating, np.integer)):
                return float(obj)
            if isinstance(obj, sqlite3.Row):
                return dict(obj)
            raise TypeError(f"Not serialisable: {type(obj)}")

        with open(args.save, "w") as f:
            json.dump(all_results, f, indent=2, default=serialise)
        print(f"\n✅ Saved to {args.save}")

    conn.close()
    print(f"\n✅ Done\n")


if __name__ == "__main__":
    main()