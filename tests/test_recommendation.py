"""Unit tests for the EmotionRecommendationEngine: Mode A & Mode B, weighted scoring, and feedback."""
import unittest
from unittest.mock import MagicMock

from music.models import (
    LicensingMetadata,
    LicensingVerificationStatus,
    RecommendationMode,
    RecommendationRequest,
    UnifiedTrack,
)
from music.recommendation import EmotionRecommendationEngine
from music.registry import ProviderRegistry
from music.storage import MusicStorage


def _make_track(
    internal_id: str,
    title: str,
    artist: str,
    genre: str,
    bpm: float,
    energy: float,
    mood_tags: list[str],
    language: str = "en",
    is_available: bool = True,
) -> UnifiedTrack:
    return UnifiedTrack(
        internal_id=internal_id,
        provider=internal_id.split(":")[0],
        provider_track_id=internal_id.split(":")[1],
        title=title,
        artist=artist,
        genre=genre,
        duration=200,
        bpm=bpm,
        energy=energy,
        mood_tags=mood_tags,
        language=language,
        artwork="https://art.example.com/art.jpg",
        playback_url="https://audio.example.com/play.mp3",
        is_available=is_available,
        licensing=LicensingMetadata(
            license_type="CC BY",
            license_source="Test Provider",
            permitted_playback_type="direct_stream",
            commercial_use_allowed=True,
            verification_status=LicensingVerificationStatus.VERIFIED.value,
        ),
    )


class TestRecommendationEngine(unittest.TestCase):
    def setUp(self):
        from music.licensing import LicensingValidator
        from music.models import DeploymentMode
        self.mock_registry = MagicMock(spec=ProviderRegistry)
        self.mock_registry.licensing_validator = LicensingValidator(DeploymentMode.NON_COMMERCIAL.value)
        self.storage = MusicStorage(":memory:")
        self.engine = EmotionRecommendationEngine(
            registry=self.mock_registry,
            storage=self.storage,
        )

    def test_mode_a_mood_matching_target_profiles(self):
        req_sad = RecommendationRequest(detected_emotion="sad", mode=RecommendationMode.MOOD_MATCHING.value)
        profile_sad = self.engine.resolve_target_profile(req_sad)
        self.assertEqual(profile_sad["target_mood"], "melancholic")
        self.assertLess(profile_sad["target_energy"], 0.40)
        self.assertLess(profile_sad["bpm_range"][1], 100.0)

        req_happy = RecommendationRequest(detected_emotion="happy", mode=RecommendationMode.MOOD_MATCHING.value)
        profile_happy = self.engine.resolve_target_profile(req_happy)
        self.assertEqual(profile_happy["target_mood"], "upbeat")
        self.assertGreater(profile_happy["target_energy"], 0.70)

    def test_mode_b_mood_shifting_target_profiles(self):
        # Sad in mood shifting should aim for uplifting comfort (~0.56 energy, ~104 bpm)
        req_shift_sad = RecommendationRequest(detected_emotion="sad", mode=RecommendationMode.MOOD_SHIFTING.value)
        profile_shift_sad = self.engine.resolve_target_profile(req_shift_sad)
        self.assertEqual(profile_shift_sad["target_mood"], "uplifting_comfort")
        self.assertGreater(profile_shift_sad["target_energy"], 0.50)
        self.assertIn("hopeful", profile_shift_sad["mood_tags"])

        # Angry in mood shifting should transition toward calming/decompressing (~0.32 energy)
        req_shift_angry = RecommendationRequest(detected_emotion="angry", mode=RecommendationMode.MOOD_SHIFTING.value)
        profile_shift_angry = self.engine.resolve_target_profile(req_shift_angry)
        self.assertEqual(profile_shift_angry["target_mood"], "calming_decompress")
        self.assertLess(profile_shift_angry["target_energy"], 0.40)

    def test_recommendation_scoring_and_ranking(self):
        track_high_match = _make_track(
            internal_id="jamendo:1",
            title="Happy Day",
            artist="The Optimists",
            genre="pop",
            bpm=124.0,
            energy=0.80,
            mood_tags=["happy", "upbeat", "bright"],
        )
        track_low_match = _make_track(
            internal_id="audius:2",
            title="Dark Abyss",
            artist="Metal Force",
            genre="metal",
            bpm=160.0,
            energy=0.95,
            mood_tags=["dark", "aggressive"],
        )

        candidates = [track_low_match, track_high_match]
        req = RecommendationRequest(
            detected_emotion="happy",
            emotion_confidence=0.92,
            mode=RecommendationMode.MOOD_MATCHING.value,
            limit=5,
        )

        res = self.engine.recommend(req, candidate_tracks=candidates)
        tracks = res["tracks"]

        self.assertEqual(len(tracks), 2)
        # Happy track should rank highest for detected 'happy' emotion
        self.assertEqual(tracks[0]["internal_id"], "jamendo:1")
        self.assertGreater(tracks[0]["recommendation_score"], tracks[1]["recommendation_score"])
        self.assertIn("score_breakdown", tracks[0])
        self.assertGreater(tracks[0]["score_breakdown"]["emotion_mood"], 0)

    def test_likes_boost_and_dislikes_penalty(self):
        user_id = "test-user-feedback"
        track_a = _make_track("jamendo:10", "Song A", "Artist A", "pop", 120.0, 0.70, ["happy"])
        track_b = _make_track("audius:20", "Song B", "Artist B", "pop", 120.0, 0.70, ["happy"])

        # User likes track A, dislikes track B
        self.storage.record_feedback(user_id=user_id, track_id="jamendo:10", feedback="like")
        self.storage.record_feedback(user_id=user_id, track_id="audius:20", feedback="dislike")

        req = RecommendationRequest(
            detected_emotion="happy",
            user_id=user_id,
            limit=5,
        )
        res = self.engine.recommend(req, candidate_tracks=[track_b, track_a])
        ranked = res["tracks"]

        self.assertEqual(ranked[0]["internal_id"], "jamendo:10")
        self.assertGreater(ranked[0]["recommendation_score"], ranked[1]["recommendation_score"])
        self.assertGreater(ranked[0]["score_breakdown"]["feedback"], 0)
        self.assertLess(ranked[1]["score_breakdown"]["feedback"], 0)

    def test_recency_penalty_reduces_score_of_recently_played_tracks(self):
        user_id = "test-user-history"
        track = _make_track("jamendo:30", "Repeated Song", "Artist X", "pop", 120.0, 0.70, ["happy"])

        req_fresh = RecommendationRequest(detected_emotion="happy", user_id=user_id, limit=5)
        score_fresh = self.engine.score_track(
            track=track,
            request=req_fresh,
            target_profile=self.engine.resolve_target_profile(req_fresh),
            preferred_genres=[],
            preferred_artists=[],
            language=None,
            history_records=[],
            feedback_summary={"liked_ids": set(), "disliked_ids": set(), "liked_artists": set(), "liked_genres": set(), "disliked_artists": set()},
        ).score

        # Record this track in listening history
        self.storage.record_play(user_id=user_id, track_id="jamendo:30", provider="jamendo")
        history = self.storage.get_history(user_id)

        score_after_play = self.engine.score_track(
            track=track,
            request=req_fresh,
            target_profile=self.engine.resolve_target_profile(req_fresh),
            preferred_genres=[],
            preferred_artists=[],
            language=None,
            history_records=history,
            feedback_summary={"liked_ids": set(), "disliked_ids": set(), "liked_artists": set(), "liked_genres": set(), "disliked_artists": set()},
        ).score

        self.assertLess(score_after_play, score_fresh)


if __name__ == "__main__":
    unittest.main()
