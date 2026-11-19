"""Integration tests for all Flask endpoints (/api/music/*), authentication, and backward compatibility."""
import json
import unittest
from unittest.mock import MagicMock

from app import create_app
from music.licensing import LicensingValidator
from music.models import (
    DeploymentMode,
    LicensingMetadata,
    LicensingVerificationStatus,
    PlaybackInfo,
    ProviderCapabilities,
    ProviderStatus,
    UnifiedTrack,
)
from music.providers.base import BaseMusicProvider
from music.registry import ProviderRegistry
from music.storage import MusicStorage


class DummyMusicProvider(BaseMusicProvider):
    name = "dummy"

    @property
    def capabilities(self):
        return ProviderCapabilities(
            search_tracks=True,
            get_track_details=True,
            get_track_stream=True,
            get_playlists=True,
            get_recommendations=True,
        )

    @property
    def is_configured(self):
        return True

    def _sample_track(self, tid="track1"):
        return UnifiedTrack(
            internal_id=f"dummy:{tid}",
            provider="dummy",
            provider_track_id=tid,
            title="Dummy Title",
            artist="Dummy Artist",
            genre="indie",
            duration=180,
            bpm=110.0,
            energy=0.65,
            mood_tags=["chill", "upbeat"],
            language="en",
            artwork="https://images.example.com/dummy.jpg",
            playback_url=f"https://audio.example.com/{tid}.mp3",
            playback_reference=f"https://example.com/tracks/{tid}",
            is_available=True,
            licensing=LicensingMetadata(
                license_type="CC BY",
                license_source="Dummy Provider",
                permitted_playback_type="direct_stream",
                commercial_use_allowed=True,
                verification_status=LicensingVerificationStatus.VERIFIED.value,
            ),
        )

    def search_tracks(self, *args, **kwargs):
        return [self._sample_track("s1")]

    def get_track_details(self, provider_track_id):
        return self._sample_track(provider_track_id)

    def get_track_stream(self, provider_track_id):
        track = self._sample_track(provider_track_id)
        return PlaybackInfo(
            internal_id=track.internal_id,
            provider=self.name,
            provider_track_id=provider_track_id,
            playback_url=track.playback_url,
            playback_reference=track.playback_reference,
            playback_type="direct_stream",
            expires_at=None,
            is_playable=True,
            licensing=track.licensing,
            attribution_text=track.licensing.attribution_text,
            refresh_supported=True,
        )

    def get_recommendations(self, *args, **kwargs):
        return [self._sample_track("rec1"), self._sample_track("rec2")]

    def get_provider_status(self, force_refresh=False):
        return ProviderStatus(
            provider=self.name,
            configured=True,
            healthy=True,
            status="healthy",
            message="Dummy provider is operating normally.",
            capabilities=self.capabilities,
            licensing_notes="Dummy non-commercial test provider.",
        )


class TestApiEndpointsAndAuth(unittest.TestCase):
    def setUp(self):
        self.registry = ProviderRegistry(licensing_validator=LicensingValidator(DeploymentMode.NON_COMMERCIAL.value))
        self.provider = DummyMusicProvider()
        self.registry.register(self.provider)

        self.storage = MusicStorage(":memory:")
        self.app = create_app(
            registry=self.registry,
            storage=self.storage,
            config_overrides={
                "TESTING": True,
                "APP_API_KEY": "secret-test-api-key",
                "REQUIRE_AUTH_FOR_API": True,
                "SECRET_KEY": "flask-test-secret-key",
            },
        )
        self.client = self.app.test_client()

    def test_unauthenticated_request_is_rejected_with_401(self):
        res = self.client.get("/api/music/search?q=test")
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertEqual(data["code"], "unauthorized")

    def test_bearer_api_key_authentication(self):
        headers = {"Authorization": "Bearer secret-test-api-key"}
        res = self.client.get("/api/music/search?q=test", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("tracks", data)
        self.assertEqual(len(data["tracks"]), 1)

    def test_invalid_bearer_api_key_is_rejected_with_401(self):
        headers = {"Authorization": "Bearer wrong-key"}
        res = self.client.get("/api/music/search?q=test", headers=headers)
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.get_json()["code"], "invalid_api_key")

    def test_session_auth_and_csrf_protection(self):
        # 1. Loading index initializes a signed session cookie and returns csrf_token
        index_res = self.client.get("/")
        self.assertEqual(index_res.status_code, 200)

        with self.client.session_transaction() as sess:
            csrf_token = sess.get("csrf_token")
            self.assertIsNotNone(csrf_token)

        # GET request with session cookie succeeds without explicit CSRF header
        get_res = self.client.get("/api/music/search?q=acoustic")
        self.assertEqual(get_res.status_code, 200)

        # POST without CSRF token must be rejected with 403
        post_bad = self.client.post(
            "/api/music/feedback",
            json={"track_id": "dummy:s1", "feedback": "like"},
        )
        self.assertEqual(post_bad.status_code, 403)
        self.assertEqual(post_bad.get_json()["code"], "invalid_csrf_token")

        # POST with valid X-CSRF-Token succeeds
        post_good = self.client.post(
            "/api/music/feedback",
            headers={"X-CSRF-Token": csrf_token},
            json={"track_id": "dummy:s1", "feedback": "like"},
        )
        self.assertEqual(post_good.status_code, 200)
        self.assertTrue(post_good.get_json()["success"])

    def test_get_providers_endpoint_does_not_leak_secrets(self):
        headers = {"Authorization": "Bearer secret-test-api-key"}
        res = self.client.get("/api/music/providers", headers=headers)
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        # Verify no credentials leaked
        self.assertNotIn("secret-test-api-key", body)
        self.assertNotIn("license_token", body)
        self.assertNotIn("client_secret", body)

    def test_get_track_details_and_playback_endpoints(self):
        headers = {"Authorization": "Bearer secret-test-api-key"}
        # Track details
        res_track = self.client.get("/api/music/track/dummy:s1", headers=headers)
        self.assertEqual(res_track.status_code, 200)
        track_data = res_track.get_json()
        self.assertEqual(track_data["internal_id"], "dummy:s1")
        self.assertTrue(track_data["playable_under_current_policy"])

        # Playback stream resolution
        res_play = self.client.get("/api/music/playback/dummy:s1", headers=headers)
        self.assertEqual(res_play.status_code, 200)
        play_data = res_play.get_json()
        self.assertTrue(play_data["is_playable"])
        self.assertEqual(play_data["playback_type"], "direct_stream")
        self.assertIn("https://", play_data["playback_url"])

    def test_get_recommendations_endpoint(self):
        headers = {"Authorization": "Bearer secret-test-api-key"}
        res = self.client.get(
            "/api/music/recommendations?emotion=happy&mode=mood_matching&limit=5",
            headers=headers,
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["detected_emotion"], "happy")
        self.assertEqual(data["mode"], "mood_matching")
        self.assertIsInstance(data["tracks"], list)

    def test_history_and_favorites_flow(self):
        headers = {"Authorization": "Bearer secret-test-api-key"}
        # Play a track to record history
        self.client.get("/api/music/playback/dummy:hist1?record_history=true", headers=headers)

        res_hist = self.client.get("/api/music/history", headers=headers)
        self.assertEqual(res_hist.status_code, 200)
        self.assertGreaterEqual(res_hist.get_json()["count"], 1)

        # Add favorite
        fav_payload = {
            "track_id": "dummy:fav1",
            "is_favorite": True,
            "track": {"title": "Fav Track", "artist": "Artist"},
        }
        res_add_fav = self.client.post("/api/music/favorites", headers=headers, json=fav_payload)
        self.assertEqual(res_add_fav.status_code, 200)

        # Retrieve favorites
        res_favs = self.client.get("/api/music/favorites", headers=headers)
        self.assertEqual(res_favs.status_code, 200)
        favs = res_favs.get_json()["favorites"]
        self.assertTrue(any(f["track_id"] == "dummy:fav1" for f in favs))

    def test_health_and_backward_compatibility(self):
        res_health = self.client.get("/health")
        self.assertEqual(res_health.status_code, 200)
        health_data = res_health.get_json()
        self.assertEqual(health_data["status"], "healthy")
        self.assertEqual(health_data["version"], "4.0-multi-provider")
        self.assertIn("dummy", health_data["configured_providers"])
        # Spotify client reference must NOT exist
        self.assertNotIn("spotify_connected", health_data)

        res_test = self.client.get("/test")
        self.assertEqual(res_test.status_code, 200)
        self.assertIn("supported_emotions", res_test.get_json())


if __name__ == "__main__":
    unittest.main()
