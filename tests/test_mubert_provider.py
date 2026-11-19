"""Unit tests for Mubert API v3 provider with mocked HTTP responses."""
import unittest
from unittest.mock import MagicMock

from music.cache import MetadataTTLCache
from music.exceptions import ProviderConfigError, UnsupportedOperationError
from music.http_client import ResilientHTTPClient
from music.models import LicensingVerificationStatus
from music.providers.mubert import MubertProvider


class TestMubertProvider(unittest.TestCase):
    def setUp(self):
        self.mock_http = MagicMock(spec=ResilientHTTPClient)
        self.cache = MetadataTTLCache(default_ttl=60)
        self.provider = MubertProvider(
            company_id="test_company_id",
            license_token="test_license_token",
            enabled=True,
            http_client=self.mock_http,
            cache=self.cache,
        )

    def test_unsupported_operations_raise_explicitly(self):
        # Mubert does NOT support arbitrary catalog track search or static track details
        with self.assertRaises(UnsupportedOperationError) as ctx1:
            self.provider.search_tracks("electronic")
        self.assertIn("does not support static track search", str(ctx1.exception))

        with self.assertRaises(UnsupportedOperationError) as ctx2:
            self.provider.get_track_details("channel_1")
        self.assertIn("does not expose static catalog track detail", str(ctx2.exception))

    def test_unconfigured_state(self):
        unconfigured = MubertProvider(company_id="", license_token="")
        self.assertFalse(unconfigured.is_configured)
        with self.assertRaises(ProviderConfigError):
            unconfigured.get_track_stream("1.0.0")

    def test_verify_license_success(self):
        self.mock_http.request_json.return_value = {
            "data": [
                {
                    "name": "B2B Pro Tier",
                    "plan": "Business",
                    "is_active": True,
                    "limits": {"streams_per_month": 50000},
                }
            ]
        }
        status = self.provider.verify_license()
        self.assertTrue(status["verified"])
        self.assertEqual(status["plan"], "B2B Pro Tier")

    def test_get_playlists_channels(self):
        # First call provisions customer token, second call fetches public channels
        self.mock_http.request_json.side_effect = [
            {"data": {"id": "cust_123", "access_token": "token_abc"}},
            {
                "data": [
                    {
                        "playlist_index": "1.0.0",
                        "name": "Chillout Lounge",
                        "description": "Relaxing generative stream",
                        "tags": ["chill", "ambient"],
                    }
                ]
            },
        ]

        channels = self.provider.get_playlists(limit=5)
        self.assertEqual(len(channels), 1)
        ch = channels[0]
        self.assertEqual(ch.internal_id, "mubert:1.0.0")
        self.assertEqual(ch.provider_playlist_id, "1.0.0")
        self.assertEqual(ch.name, "Chillout Lounge")

    def test_get_track_stream_time_limited(self):
        self.mock_http.request_json.side_effect = [
            {"data": [{"plan": "Enterprise", "is_active": True}]},  # verify_license
            {"data": {"id": "cust_123", "access_token": "token_abc"}},  # customer tokens
            {
                "data": {
                    "link": "https://stream.mubert.com/b2b/v3/channel/1.0.0?session=xyz",
                    "expires_in": 900,
                }
            },
        ]

        playback = self.provider.get_track_stream("1.0.0")
        self.assertEqual(playback.internal_id, "mubert:1.0.0")
        self.assertEqual(playback.playback_type, "time_limited_stream")
        self.assertTrue(playback.is_playable)
        self.assertIsNotNone(playback.expires_at)
        self.assertEqual(playback.licensing.verification_status, LicensingVerificationStatus.VERIFIED.value)
        self.assertFalse(playback.licensing.redistribution_allowed)


if __name__ == "__main__":
    unittest.main()
