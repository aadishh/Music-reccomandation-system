"""Unit tests for Audius REST API v1 provider with mocked HTTP responses."""
import unittest
from unittest.mock import MagicMock

from music.cache import MetadataTTLCache
from music.exceptions import LicensingViolationError, TrackNotFoundError
from music.http_client import ResilientHTTPClient
from music.models import LicensingVerificationStatus
from music.providers.audius import AudiusProvider


class TestAudiusProvider(unittest.TestCase):
    def setUp(self):
        self.mock_http = MagicMock(spec=ResilientHTTPClient)
        self.cache = MetadataTTLCache(default_ttl=60)
        self.provider = AudiusProvider(
            api_key="test_audius_api_key",
            app_name="TestApp",
            enabled=True,
            http_client=self.mock_http,
            cache=self.cache,
        )

    def test_search_tracks_success(self):
        self.mock_http.request_json.return_value = {
            "data": [
                {
                    "id": "D72kP",
                    "title": "Neon Sunset",
                    "user": {"id": "user123", "name": "Synth Master", "handle": "synthmaster"},
                    "duration": 195,
                    "genre": "Electronic",
                    "mood": "Upbeat",
                    "bpm": 128.0,
                    "tags": "synthwave,retro,80s",
                    "artwork": {"480x480": "https://creatornode.audius.co/artwork/D72kP_480.jpg"},
                    "is_streamable": True,
                    "stream_conditions": None,
                    "is_unlisted": False,
                    "license": "Creative Commons Attribution",
                    "permalink": "/synthmaster/neon-sunset",
                }
            ]
        }

        tracks = self.provider.search_tracks("neon", genre="Electronic", mood="Upbeat", limit=5)
        self.assertEqual(len(tracks), 1)
        track = tracks[0]

        self.assertEqual(track.internal_id, "audius:D72kP")
        self.assertEqual(track.provider, "audius")
        self.assertEqual(track.title, "Neon Sunset")
        self.assertEqual(track.artist, "Synth Master")
        self.assertEqual(track.genre, "electronic")
        self.assertEqual(track.bpm, 128.0)
        self.assertIsNotNone(track.energy)
        self.assertIn("synthwave", track.mood_tags)
        self.assertTrue(track.is_available)
        self.assertEqual(track.licensing.license_type, "Creative Commons Attribution")
        self.assertTrue(track.licensing.commercial_use_allowed)
        self.assertEqual(track.licensing.verification_status, LicensingVerificationStatus.VERIFIED.value)

    def test_gated_track_is_blocked_for_playback(self):
        self.mock_http.request_json.return_value = {
            "data": {
                "id": "Gated123",
                "title": "VIP Club Exclusive",
                "user": {"name": "DJ Exclusive"},
                "is_streamable": True,
                "stream_conditions": {"nft_collection": "0xabc123"},
                "license": "All Rights Reserved",
            }
        }

        track = self.provider.get_track_details("Gated123")
        self.assertFalse(track.is_available)
        self.assertEqual(track.licensing.verification_status, LicensingVerificationStatus.BLOCKED.value)

        # Attempting to get authorized stream for gated track must raise LicensingViolationError
        with self.assertRaises(LicensingViolationError):
            self.provider.get_track_stream("Gated123")

    def test_non_streamable_track_is_blocked(self):
        self.mock_http.request_json.return_value = {
            "data": {
                "id": "Disabled456",
                "title": "Private Track",
                "user": {"name": "Artist X"},
                "is_streamable": False,
                "stream_conditions": None,
            }
        }
        track = self.provider.get_track_details("Disabled456")
        self.assertFalse(track.is_available)
        with self.assertRaises(LicensingViolationError):
            self.provider.get_track_stream("Disabled456")

    def test_get_track_stream_success(self):
        self.mock_http.request_json.return_value = {
            "data": {
                "id": "Streamable999",
                "title": "Open Audio",
                "user": {"name": "Free Sounds"},
                "is_streamable": True,
                "stream_conditions": None,
                "is_unlisted": False,
                "license": "All Rights Reserved",
            }
        }
        # Simulate HEAD check returning a CDN stream redirect
        self.mock_http.resolve_redirect_url.return_value = (
            302,
            "https://audius-discovery-1.org/v1/tracks/Streamable999/stream?app_name=TestApp",
        )

        stream_info = self.provider.get_track_stream("Streamable999")
        self.assertEqual(stream_info.internal_id, "audius:Streamable999")
        self.assertTrue(stream_info.is_playable)
        self.assertIn("Streamable999", stream_info.playback_url)

    def test_track_not_found(self):
        self.mock_http.request_json.return_value = None
        with self.assertRaises(TrackNotFoundError):
            self.provider.get_track_details("NonExistent")


if __name__ == "__main__":
    unittest.main()
