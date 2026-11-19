"""Unit tests for Jamendo API v3.0 provider with mocked HTTP responses."""
import unittest
from unittest.mock import MagicMock

from music.cache import MetadataTTLCache
from music.exceptions import (
    ProviderAuthError,
    ProviderConfigError,
    ProviderRateLimitError,
    TrackNotFoundError,
)
from music.http_client import ResilientHTTPClient
from music.models import LicensingVerificationStatus
from music.providers.jamendo import JamendoProvider


class TestJamendoProvider(unittest.TestCase):
    def setUp(self):
        self.mock_http = MagicMock(spec=ResilientHTTPClient)
        self.cache = MetadataTTLCache(default_ttl=60)
        self.provider = JamendoProvider(
            client_id="test_jamendo_client_id",
            enabled=True,
            http_client=self.mock_http,
            cache=self.cache,
        )

    def test_unconfigured_provider_raises_error(self):
        unconfigured = JamendoProvider(client_id="", enabled=True)
        self.assertFalse(unconfigured.is_configured)
        with self.assertRaises(ProviderConfigError):
            unconfigured.search_tracks("acoustic")

    def test_disabled_provider_raises_error(self):
        disabled = JamendoProvider(client_id="valid_id", enabled=False)
        self.assertFalse(disabled.is_configured)
        with self.assertRaises(ProviderConfigError):
            disabled.get_track_details("12345")

    def test_search_tracks_success(self):
        self.mock_http.request_json.return_value = {
            "headers": {"status": "success", "code": 0},
            "results": [
                {
                    "id": "1001",
                    "name": "Sunny Horizons",
                    "artist_name": "Ambient Explorer",
                    "album_name": "Bright Skies",
                    "duration": 210,
                    "audio": "https://prod-1.storage.jamendo.com/?trackid=1001&format=mp32",
                    "album_image": "https://usercontent.jamendo.com?type=album&id=401",
                    "license_ccurl": "https://creativecommons.org/licenses/by/4.0/",
                    "prourl": "https://licensing.jamendo.com/en/track/1001",
                    "audiodownload_allowed": True,
                    "musicinfo": {
                        "speed": "medium",
                        "tags": {
                            "genres": ["pop", "acoustic"],
                            "vartags": ["happy", "uplifting"],
                        },
                        "lang": "en",
                    },
                    "shareurl": "https://www.jamendo.com/track/1001",
                }
            ],
        }

        tracks = self.provider.search_tracks("sunny", genre="pop", mood="happy", limit=10)
        self.assertEqual(len(tracks), 1)
        track = tracks[0]

        self.assertEqual(track.internal_id, "jamendo:1001")
        self.assertEqual(track.provider, "jamendo")
        self.assertEqual(track.title, "Sunny Horizons")
        self.assertEqual(track.artist, "Ambient Explorer")
        self.assertEqual(track.genre, "pop")
        self.assertEqual(track.duration, 210)
        self.assertIn("happy", track.mood_tags)
        self.assertEqual(track.playback_url, "https://prod-1.storage.jamendo.com/?trackid=1001&format=mp32")
        self.assertEqual(track.licensing.license_type, "CC BY")
        self.assertTrue(track.licensing.attribution_required)
        self.assertIn("Jamendo", track.licensing.attribution_text)

    def test_get_track_details_and_stream(self):
        self.mock_http.request_json.return_value = {
            "headers": {"status": "success", "code": 0},
            "results": [
                {
                    "id": "2002",
                    "name": "Quiet Rain",
                    "artist_name": "Calm Strings",
                    "duration": 180,
                    "audio": "https://prod-1.storage.jamendo.com/?trackid=2002&format=mp32",
                    "license_ccurl": "https://creativecommons.org/licenses/by-nc/4.0/",
                    "audiodownload_allowed": False,
                    "musicinfo": {"speed": "low", "tags": {"genres": ["ambient"], "vartags": ["calm"]}},
                }
            ],
        }

        track = self.provider.get_track_details("2002")
        self.assertEqual(track.internal_id, "jamendo:2002")
        self.assertEqual(track.licensing.license_type, "CC BY-NC")
        # In standard free tier, non-commercial CC license is marked restricted for commercial use
        self.assertFalse(track.licensing.commercial_use_allowed)
        self.assertEqual(track.licensing.verification_status, LicensingVerificationStatus.RESTRICTED.value)

        # Test stream resolution
        stream_info = self.provider.get_track_stream("2002")
        self.assertEqual(stream_info.internal_id, "jamendo:2002")
        self.assertEqual(stream_info.playback_type, "direct_stream")
        self.assertTrue(stream_info.is_playable)

    def test_track_not_found(self):
        self.mock_http.request_json.return_value = {
            "headers": {"status": "success", "code": 0},
            "results": [],
        }
        with self.assertRaises(TrackNotFoundError):
            self.provider.get_track_details("999999")

    def test_api_rate_limit_and_auth_error_handling(self):
        # Jamendo code 4 = Invalid Client ID
        self.mock_http.request_json.return_value = {
            "headers": {"status": "failed", "code": 4, "error_message": "Invalid client_id"},
            "results": [],
        }
        with self.assertRaises(ProviderAuthError):
            self.provider.search_tracks("rock")

        # Jamendo code 12 = Rate Limit / Quota Exceeded
        self.mock_http.request_json.return_value = {
            "headers": {"status": "failed", "code": 12, "error_message": "Monthly rate limit reached"},
            "results": [],
        }
        with self.assertRaises(ProviderRateLimitError):
            self.provider.search_tracks("rock")

    def test_recommendations_with_speed_profile(self):
        self.mock_http.request_json.return_value = {
            "headers": {"status": "success", "code": 0},
            "results": [
                {
                    "id": "3003",
                    "name": "Energetic Groove",
                    "artist_name": "Beat Maker",
                    "duration": 150,
                    "audio": "https://stream.jamendo.com/3003.mp3",
                    "license_ccurl": "https://creativecommons.org/licenses/by-sa/4.0/",
                    "musicinfo": {"speed": "high", "tags": {"genres": ["dance"], "vartags": ["fast"]}},
                }
            ],
        }

        recs = self.provider.get_recommendations(
            mood_tags=["energetic", "dance"],
            genres=["dance"],
            target_energy=0.85,
            limit=5,
        )
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0].energy, 0.78)  # mapped from speed='high'


if __name__ == "__main__":
    unittest.main()
