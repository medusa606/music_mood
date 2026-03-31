"""
Smart Read Companion - Audio analysis with Essentia.
All feature extraction and VAD estimation logic lives here.
Swap this file out if you change analysis library.
"""

import numpy as np
import essentia.standard as es


# ─────────────────────────────────────────────
# VAD ESTIMATION
# ─────────────────────────────────────────────

def estimate_valence(scale: str, key_strength: float,
                     spectral_centroid: float) -> float:
    """
    Estimate valence (0=dark/negative, 1=bright/positive).

    Major key  → higher valence
    Brighter spectral content → higher valence
    Heuristic approximation - not as precise as Spotify's model.
    """
    base               = 0.65 if scale == "major" else 0.30
    brightness_adjust  = min(max((spectral_centroid - 1000) / 6000, -0.1), 0.1)
    return round(min(max(base + brightness_adjust, 0.0), 1.0), 3)


def estimate_arousal(rms_energy: float, bpm: float) -> float:
    """
    Estimate arousal (0=calm, 1=intense).

    Higher RMS energy → louder → more arousal
    Higher BPM        → faster → more arousal
    Energy weighted more heavily than tempo for cinematic scores.
    """
    rms_norm = min(rms_energy / 0.2, 1.0)
    bpm_norm = min(max((bpm - 40) / 160, 0.0), 1.0)
    arousal  = (rms_norm * 0.6) + (bpm_norm * 0.4)
    return round(min(max(arousal, 0.0), 1.0), 3)


# ─────────────────────────────────────────────
# MAIN ANALYSIS
# ─────────────────────────────────────────────

def analyse_track(mp3_path: str) -> dict | None:
    """
    Full Essentia analysis pipeline for one track.
    Returns feature dict or None on failure.
    """
    try:
        # ── Load ─────────────────────────────────────────────
        loader = es.MonoLoader(filename=mp3_path, sampleRate=44100)
        audio  = loader()

        if len(audio) == 0:
            print("    ❌ Empty audio file")
            return None

        # ── Rhythm ───────────────────────────────────────────
        rhythm_extractor = es.RhythmExtractor2013(method="multifeature")
        bpm, beats, beats_confidence, _, beats_intervals = rhythm_extractor(audio)

        # ── Energy ───────────────────────────────────────────
        loudness = es.Loudness()(audio)
        rms      = es.RMS()(audio)

        # ── Spectral Centroid ─────────────────────────────────
        centroid       = es.SpectralCentroidTime()
        spec_centroids = []
        for frame in es.FrameGenerator(
            audio, frameSize=2048, hopSize=1024, startFromZero=True
        ):
            spec_centroids.append(centroid(frame))
        avg_centroid = float(np.mean(spec_centroids)) if spec_centroids else 0.0

        # ── Key / Mode ────────────────────────────────────────
        key, scale, key_strength = es.KeyExtractor()(audio)

        # ── Danceability ──────────────────────────────────────
        danceability, _ = es.Danceability()(audio)

        # ── MusicExtractor (optional richer features) ─────────
        loudness_mean = None
        try:
            music_features, _ = es.MusicExtractor(
                lowlevelStats=["mean"],
                rhythmStats=["mean"],
                tonalStats=["mean"]
            )(mp3_path)
            loudness_mean = float(
                music_features["lowlevel.loudness_ebu128.integrated"]
            )
        except Exception:
            pass  # optional - don't fail if unavailable

        # ── Derived VAD ───────────────────────────────────────
        bpm_val  = float(bpm)
        rms_val  = float(rms)

        return {
            "bpm":               round(bpm_val, 2),
            "beats_confidence":  round(float(beats_confidence), 3),
            "loudness":          round(float(loudness), 3),
            "rms_energy":        round(rms_val, 5),
            "loudness_mean":     round(loudness_mean, 3) if loudness_mean else None,
            "spectral_centroid": round(avg_centroid, 2),
            "track_key":         key,
            "track_mode":        scale,
            "key_strength":      round(float(key_strength), 3),
            "danceability":      round(float(danceability), 4),
            "estimated_valence": estimate_valence(scale, float(key_strength), avg_centroid),
            "estimated_arousal": estimate_arousal(rms_val, bpm_val),
        }

    except Exception as e:
        print(f"    ❌ Essentia analysis failed: {e}")
        return None