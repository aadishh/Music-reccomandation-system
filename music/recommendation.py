"""Provider-independent AI emotion recommendation engine with Mood Matching & Mood Shifting."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from config import DEFAULT_RECOMMENDATION_WEIGHTS
from music.models import (
    RecommendationMode,
    RecommendationRequest,
    ScoredTrack,
    UnifiedTrack,
)
from music.registry import ProviderRegistry
from music.storage import MusicStorage

logger = logging.getLogger(__name__)

# Mode A: Mood Matching — aligns musical mood, energy, and tempo with detected emotion
MOOD_MATCHING_PROFILES: Dict[str, Dict[str, Any]] = {
    "happy": {
        "target_mood": "upbeat",
        "mood_tags": ["happy", "upbeat", "energetic", "joyful", "bright", "feelgood", "lively"],
        "genres": ["pop", "dance", "electronic", "funk", "indie"],
        "bpm_range": (110.0, 138.0),
        "target_energy": 0.78,
    },
    "sad": {
        "target_mood": "melancholic",
        "mood_tags": ["sad", "melancholy", "emotional", "calm", "soft", "reflective", "tender"],
        "genres": ["acoustic", "ambient", "indie", "classical", "piano", "folk"],
        "bpm_range": (65.0, 94.0),
        "target_energy": 0.28,
    },
    "angry": {
        "target_mood": "intense",
        "mood_tags": ["aggressive", "intense", "energetic", "dark", "fiery", "gritty", "powerful"],
        "genres": ["rock", "metal", "hip-hop", "electronic", "punk"],
        "bpm_range": (122.0, 160.0),
        "target_energy": 0.88,
    },
    "neutral": {
        "target_mood": "balanced",
        "mood_tags": ["chill", "relaxed", "easygoing", "cool", "focus", "mellow", "groovy"],
        "genres": ["lo-fi", "jazz", "indie", "electronic", "pop"],
        "bpm_range": (88.0, 114.0),
        "target_energy": 0.50,
    },
    "fear": {
        "target_mood": "atmospheric",
        "mood_tags": ["dark", "cinematic", "brooding", "ambient", "dramatic", "atmospheric"],
        "genres": ["ambient", "soundtrack", "electronic", "classical"],
        "bpm_range": (70.0, 100.0),
        "target_energy": 0.42,
    },
    "surprise": {
        "target_mood": "exciting",
        "mood_tags": ["excited", "upbeat", "energizing", "fun", "dynamic", "lively"],
        "genres": ["electronic", "pop", "funk", "dance", "indie"],
        "bpm_range": (114.0, 142.0),
        "target_energy": 0.80,
    },
    "disgust": {
        "target_mood": "gritty",
        "mood_tags": ["gritty", "defiant", "alternative", "raw", "serious", "rock"],
        "genres": ["alternative", "rock", "indie", "hip-hop"],
        "bpm_range": (95.0, 128.0),
        "target_energy": 0.68,
    },
}

# Mode B: Mood Shifting — applies iso-principle inspired transitions toward constructive states
MOOD_SHIFTING_PROFILES: Dict[str, Dict[str, Any]] = {
    "happy": {
        "target_mood": "sustained_positive",
        "mood_tags": ["happy", "groovy", "uplifting", "bright", "feelgood", "warm"],
        "genres": ["pop", "funk", "indie", "dance"],
        "bpm_range": (108.0, 132.0),
        "target_energy": 0.74,
    },
    "sad": {
        "target_mood": "uplifting_comfort",
        "mood_tags": ["hopeful", "warm", "uplifting", "peaceful", "bright", "inspiring"],
        "genres": ["indie", "acoustic", "pop", "chill", "folk"],
        "bpm_range": (92.0, 116.0),
        "target_energy": 0.56,
    },
    "angry": {
        "target_mood": "calming_decompress",
        "mood_tags": ["calm", "peaceful", "chill", "relaxing", "ambient", "easygoing"],
        "genres": ["ambient", "lo-fi", "jazz", "acoustic", "classical"],
        "bpm_range": (72.0, 96.0),
        "target_energy": 0.32,
    },
    "neutral": {
        "target_mood": "energizing_focus",
        "mood_tags": ["fresh", "groovy", "upbeat", "inspiring", "lively", "cool"],
        "genres": ["indie", "electronic", "funk", "pop"],
        "bpm_range": (102.0, 124.0),
        "target_energy": 0.65,
    },
    "fear": {
        "target_mood": "grounding_reassuring",
        "mood_tags": ["peaceful", "calm", "warm", "soft", "relaxing", "comforting"],
        "genres": ["ambient", "piano", "acoustic", "classical", "chill"],
        "bpm_range": (68.0, 90.0),
        "target_energy": 0.28,
    },
    "surprise": {
        "target_mood": "curated_groove",
        "mood_tags": ["cool", "groovy", "upbeat", "smooth", "feelgood"],
        "genres": ["electronic", "funk", "indie", "pop"],
        "bpm_range": (100.0, 124.0),
        "target_energy": 0.66,
    },
    "disgust": {
        "target_mood": "refreshing_reset",
        "mood_tags": ["fresh", "bright", "chill", "peaceful", "uplifting", "clean"],
        "genres": ["lo-fi", "indie", "acoustic", "ambient", "jazz"],
        "bpm_range": (86.0, 112.0),
        "target_energy": 0.48,
    },
}

USER_MOOD_SYNONYMS: Dict[str, List[str]] = {
    "calm": ["calm", "peaceful", "relaxing", "chill", "ambient", "soft"],
    "energetic": ["energetic", "upbeat", "energizing", "lively", "party", "dance"],
    "focus": ["focus", "instrumental", "ambient", "lo-fi", "chill", "study"],
    "happy": ["happy", "upbeat", "bright", "feelgood", "joyful"],
    "melancholic": ["sad", "melancholy", "emotional", "tender", "acoustic"],
    "workout": ["energetic", "aggressive", "intense", "powerful", "fast", "electronic"],
    "romantic": ["romantic", "tender", "warm", "soft", "soul"],
}


class EmotionRecommendationEngine:
    """Weighted multi-signal recommendation engine decoupled from individual music providers."""

    def __init__(
        self,
        registry: ProviderRegistry,
        storage: Optional[MusicStorage] = None,
        weights: Optional[Dict[str, float]] = None,
    ) -> None:
        self.registry = registry
        self.storage = storage
        self.weights: Dict[str, float] = dict(DEFAULT_RECOMMENDATION_WEIGHTS)
        if weights:
            self.weights.update(weights)

    def resolve_target_profile(self, request: RecommendationRequest) -> Dict[str, Any]:
        emotion = (request.detected_emotion or "neutral").strip().lower()
        mode = (request.mode or RecommendationMode.MOOD_MATCHING.value).strip().lower()
        if mode not in {RecommendationMode.MOOD_MATCHING.value, RecommendationMode.MOOD_SHIFTING.value}:
            mode = RecommendationMode.MOOD_MATCHING.value

        profiles = (
            MOOD_SHIFTING_PROFILES
            if mode == RecommendationMode.MOOD_SHIFTING.value
            else MOOD_MATCHING_PROFILES
        )
        base_profile = dict(profiles.get(emotion, profiles["neutral"]))
        base_profile["detected_emotion"] = emotion
        base_profile["mode"] = mode

        if request.user_selected_mood:
            user_mood = request.user_selected_mood.strip().lower()
            extra_tags = USER_MOOD_SYNONYMS.get(user_mood, [user_mood])
            base_profile["mood_tags"] = list(dict.fromkeys(extra_tags + base_profile["mood_tags"]))
            base_profile["user_selected_mood"] = user_mood

        return base_profile

    def recommend(
        self,
        request: RecommendationRequest,
        *,
        candidate_tracks: Optional[List[UnifiedTrack]] = None,
    ) -> Dict[str, Any]:
        """Generate ranked recommendations with explainable weighted scoring."""
        target_profile = self.resolve_target_profile(request)

        # Merge stored user preferences when user_id is present
        preferred_genres = [g.strip().lower() for g in request.preferred_genres if g and g.strip()]
        preferred_artists = [a.strip().lower() for a in request.preferred_artists if a and a.strip()]
        language = (request.language or "").strip().lower() or None

        history_records: List[Dict[str, Any]] = []
        feedback_summary: Dict[str, Any] = {
            "liked_ids": set(),
            "disliked_ids": set(),
            "liked_artists": set(),
            "liked_genres": set(),
            "disliked_artists": set(),
        }

        if self.storage and request.user_id:
            prefs = self.storage.get_preferences(request.user_id)
            if not preferred_genres and prefs.get("preferred_genres"):
                preferred_genres = [g.lower() for g in prefs["preferred_genres"]]
            if not preferred_artists and prefs.get("preferred_artists"):
                preferred_artists = [a.lower() for a in prefs["preferred_artists"]]
            if not language and prefs.get("language"):
                language = prefs["language"].lower()
            history_records = self.storage.get_history(request.user_id, limit=40)
            feedback_summary = self.storage.get_feedback_summary(request.user_id)

        query_genres = list(dict.fromkeys(preferred_genres + list(target_profile["genres"])))
        provider_errors: List[Dict[str, Any]] = []

        if candidate_tracks is not None:
            raw_candidates = candidate_tracks
        else:
            raw_candidates, provider_errors = self.registry.gather_recommendation_candidates(
                mood_tags=target_profile["mood_tags"],
                genres=query_genres,
                bpm_range=target_profile["bpm_range"],
                target_energy=target_profile["target_energy"],
                language=language,
                providers=request.providers,
                per_provider_limit=max(15, request.limit * 2),
            )

        # Filter strictly: never recommend unavailable or licensing-blocked tracks
        eligible_candidates: List[UnifiedTrack] = []
        for track in raw_candidates:
            allowed, _ = self.registry.licensing_validator.is_playable(track)
            if allowed:
                eligible_candidates.append(track)

        scored: List[ScoredTrack] = []
        for track in eligible_candidates:
            scored_track = self.score_track(
                track=track,
                request=request,
                target_profile=target_profile,
                preferred_genres=preferred_genres,
                preferred_artists=preferred_artists,
                language=language,
                history_records=history_records,
                feedback_summary=feedback_summary,
            )
            scored.append(scored_track)

        scored.sort(key=lambda item: item.score, reverse=True)
        top_scored = scored[: max(1, int(request.limit))]

        return {
            "mode": target_profile["mode"],
            "detected_emotion": target_profile["detected_emotion"],
            "emotion_confidence": self._normalize_confidence(request.emotion_confidence),
            "target_profile": {
                "target_mood": target_profile["target_mood"],
                "mood_tags": target_profile["mood_tags"],
                "bpm_range": list(target_profile["bpm_range"]),
                "target_energy": target_profile["target_energy"],
                "user_selected_mood": target_profile.get("user_selected_mood"),
            },
            "weights": dict(self.weights),
            "count": len(top_scored),
            "tracks": [item.to_dict() for item in top_scored],
            "provider_errors": provider_errors,
        }

    def score_track(
        self,
        *,
        track: UnifiedTrack,
        request: RecommendationRequest,
        target_profile: Dict[str, Any],
        preferred_genres: List[str],
        preferred_artists: List[str],
        language: Optional[str],
        history_records: List[Dict[str, Any]],
        feedback_summary: Dict[str, Any],
    ) -> ScoredTrack:
        w = self.weights
        confidence = self._normalize_confidence(request.emotion_confidence)
        track_tags = {t.lower() for t in track.mood_tags}
        if track.genre:
            track_tags.add(track.genre.lower())
        artist_lower = (track.artist or "").strip().lower()
        genre_lower = (track.genre or "").strip().lower()

        # 1. Emotion / Mood Tag Score (scaled by DeepFace confidence)
        profile_mood_tags = {t.lower() for t in target_profile["mood_tags"]}
        tag_overlap = len(track_tags & profile_mood_tags)
        raw_mood_score = min(1.0, tag_overlap / 2.0) if profile_mood_tags else 0.0
        # Confidence scales weight between 0.5x (low confidence) and 1.0x (high confidence)
        confidence_factor = 0.5 + 0.5 * confidence
        emotion_mood_component = w["emotion_mood"] * raw_mood_score * confidence_factor

        # 2. User-selected mood match
        user_mood_component = 0.0
        if request.user_selected_mood:
            u_mood = request.user_selected_mood.strip().lower()
            u_synonyms = set(USER_MOOD_SYNONYMS.get(u_mood, [u_mood]))
            u_overlap = len(track_tags & u_synonyms)
            user_mood_component = w["user_mood"] * min(1.0, u_overlap / 1.0)

        # 3. Preferred genres (user preference + profile genres)
        genre_component = 0.0
        if preferred_genres:
            if genre_lower in preferred_genres or bool(track_tags & set(preferred_genres)):
                genre_component = w["genre"]
        elif genre_lower in {g.lower() for g in target_profile["genres"]}:
            genre_component = w["genre"] * 0.7

        # 4. Preferred artists
        artist_component = 0.0
        if preferred_artists and any(pa in artist_lower or artist_lower in pa for pa in preferred_artists):
            artist_component = w["artist"]

        # 5. Language match
        language_component = 0.0
        if language:
            if track.language and track.language.lower().startswith(language[:2]):
                language_component = w["language"]
            elif track.language is None:
                # Neutral small fallback when provider does not expose language metadata
                language_component = w["language"] * 0.25

        # 6. BPM proximity score
        bpm_component = 0.0
        bpm_min, bpm_max = target_profile["bpm_range"]
        if track.bpm is not None and track.bpm > 0:
            if bpm_min <= track.bpm <= bpm_max:
                bpm_sim = 1.0
            else:
                distance = min(abs(track.bpm - bpm_min), abs(track.bpm - bpm_max))
                bpm_sim = max(0.0, 1.0 - (distance / 45.0))
            bpm_component = w["bpm"] * bpm_sim

        # 7. Energy proximity score
        energy_component = 0.0
        target_energy = float(target_profile["target_energy"])
        if track.energy is not None:
            energy_sim = max(0.0, 1.0 - abs(track.energy - target_energy))
            energy_component = w["energy"] * energy_sim

        # 8. Listening history affinity (genre/artist familiarity from past plays)
        history_affinity_component = 0.0
        recent_play_penalty = 0.0
        if history_records:
            recent_ids = [r["track_id"] for r in history_records[:15]]
            if track.internal_id in recent_ids:
                # Stronger penalty the more recently it was played
                recency_idx = recent_ids.index(track.internal_id)
                decay = 1.0 - (recency_idx / max(1, len(recent_ids)))
                recent_play_penalty = -w["recent_play_penalty"] * max(0.3, decay)

            hist_genres = {(r.get("genre") or "").lower() for r in history_records if r.get("genre")}
            hist_artists = {(r.get("artist") or "").lower() for r in history_records if r.get("artist")}
            affinity = 0.0
            if genre_lower and genre_lower in hist_genres:
                affinity += 0.5
            if artist_lower and artist_lower in hist_artists:
                affinity += 0.5
            history_affinity_component = w["history_affinity"] * min(1.0, affinity)

        # 9. Likes & Dislikes feedback
        feedback_component = 0.0
        if track.internal_id in feedback_summary["liked_ids"]:
            feedback_component += w["like_boost"]
        elif artist_lower in feedback_summary["liked_artists"] or genre_lower in feedback_summary["liked_genres"]:
            feedback_component += w["like_boost"] * 0.45

        if track.internal_id in feedback_summary["disliked_ids"]:
            feedback_component -= w["dislike_penalty"]
        elif artist_lower in feedback_summary["disliked_artists"]:
            feedback_component -= w["dislike_penalty"] * 0.4

        breakdown = {
            "emotion_mood": emotion_mood_component,
            "user_mood": user_mood_component,
            "genre": genre_component,
            "artist": artist_component,
            "language": language_component,
            "bpm": bpm_component,
            "energy": energy_component,
            "history_affinity": history_affinity_component,
            "feedback": feedback_component,
            "recent_play_penalty": recent_play_penalty,
        }
        total_score = sum(breakdown.values())

        return ScoredTrack(
            track=track,
            score=total_score,
            score_breakdown=breakdown,
            recommendation_mode=target_profile["mode"],
            target_profile={
                "target_mood": target_profile["target_mood"],
                "bpm_range": list(target_profile["bpm_range"]),
                "target_energy": target_profile["target_energy"],
            },
        )

    @staticmethod
    def _normalize_confidence(confidence: float) -> float:
        try:
            val = float(confidence)
        except (TypeError, ValueError):
            return 0.75
        if val > 1.0:
            val = val / 100.0
        return max(0.0, min(1.0, val))
