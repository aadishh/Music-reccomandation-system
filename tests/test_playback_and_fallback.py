"""Unit tests for playback URL resolution, expired stream recovery, retry backoff, and provider fallback."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from music.exceptions import (
    ProviderRateLimitError,
    ProviderUnavailableError,
    StreamExpiredError,
)
from music.http_client import ResilientHTTPClient
from music.licensing import LicensingValidator
from music.models import (
    DeploymentMode,
    LicensingMetadata,
    LicensingVerificationStatus,
    PlaybackInfo,
    UnifiedTrack,
)
from music.providers.base import BaseMusicProvider
from music.registry import ProviderRegistry


class MockFailingProvider(BaseMusicProvider):
    name = "failing"

    @property
    def capabilities(self):
        from music.models import ProviderCapabilities
        return ProviderCapabilities(search_tracks=True, get_recommendations=True)

    @property
    def is_configured(self):
        return True

    def search_tracks(self, *args, **kwargs):
        raise ProviderUnavailableError("Failing provider is currently down.", provider=self.name)

    def get_recommendations(self, *args, **kwargs):
        raise ProviderUnavailableError("Recommendations endpoint unreachable.", provider=self.name)

    def get_provider_status(self, force_refresh=False):
        from music.models import ProviderStatus
        return ProviderStatus(
            provider=self.name,
            configured=True,
            healthy=False,
            status="unavailable",
            message="Down",
            capabilities=self.capabilities,
        )


class MockHealthyProvider(BaseMusicProvider):
    name = "healthy"

    @property
    def capabilities(self):
        from music.models import ProviderCapabilities
        return ProviderCapabilities(
            search_tracks=True,
            get_track_details=True,
            get_track_stream=True,
            get_recommendations=True,
        )

    @property
    def is_configured(self):
        return True

    def search_tracks(self, *args, **kwargs):
        return [
            UnifiedTrack(
                internal_id="healthy:track_ok",
                provider=self.name,
                provider_track_id="track_ok",
                title="Resilient Track",
                artist="Backup Artist",
                playback_url="https://audio.example.com/ok.mp3",
                is_available=True,
                licensing=LicensingMetadata(
                    license_type="CC BY",
                    license_source="Healthy Provider",
                    permitted_playback_type="direct_stream",
                    commercial_use_allowed=True,
                    verification_status=LicensingVerificationStatus.VERIFIED.value,
                ),
            )
        ]

    def get_track_stream(self, provider_track_id):
        return PlaybackInfo(
            internal_id=f"{self.name}:{provider_track_id}",
            provider=self.name,
            provider_track_id=provider_track_id,
            playback_url=f"https://audio.example.com/{provider_track_id}.mp3",
            playback_reference=None,
            playback_type="direct_stream",
            expires_at=None,
            is_playable=True,
            licensing=LicensingMetadata(
                license_type="CC BY",
                license_source="Healthy Provider",
                permitted_playback_type="direct_stream",
                commercial_use_allowed=True,
                verification_status=LicensingVerificationStatus.VERIFIED.value,
            ),
        )

    def get_provider_status(self, force_refresh=False):
        from music.models import ProviderStatus
        return ProviderStatus(
            provider=self.name,
            configured=True,
            healthy=True,
            status="healthy",
            message="OK",
            capabilities=self.capabilities,
        )


class TestPlaybackAndFallback(unittest.TestCase):
    def test_cross_provider_fallback_on_search(self):
        registry = ProviderRegistry(licensing_validator=LicensingValidator(DeploymentMode.NON_COMMERCIAL.value))
        failing = MockFailingProvider()
        healthy = MockHealthyProvider()

        registry.register(failing)
        registry.register(healthy)

        # Search should not crash when one provider fails; healthy provider tracks returned with error log
        tracks, errors = registry.search_tracks("ambient", limit=10)
        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0].internal_id, "healthy:track_ok")
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["provider"], "failing")

    def test_expired_playback_detection_and_refresh(self):
        provider = MockHealthyProvider()
        # Mock get_track_stream returning expired on first call, fresh on second
        now = datetime.now(timezone.utc)
        past = (now - timedelta(minutes=5)).isoformat()
        future = (now + timedelta(minutes=15)).isoformat()

        expired_info = PlaybackInfo(
            internal_id="healthy:exp1",
            provider="healthy",
            provider_track_id="exp1",
            playback_url="https://audio.example.com/expired.mp3",
            playback_reference=None,
            playback_type="time_limited_stream",
            expires_at=past,
            is_playable=True,
            licensing=LicensingMetadata(
                license_type="Mubert B2B",
                license_source="Mubert",
                permitted_playback_type="time_limited_stream",
                commercial_use_allowed=True,
                verification_status=LicensingVerificationStatus.VERIFIED.value,
            ),
            refresh_supported=True,
        )
        fresh_info = PlaybackInfo(
            internal_id="healthy:exp1",
            provider="healthy",
            provider_track_id="exp1",
            playback_url="https://audio.example.com/fresh.mp3",
            playback_reference=None,
            playback_type="time_limited_stream",
            expires_at=future,
            is_playable=True,
            licensing=LicensingMetadata(
                license_type="Mubert B2B",
                license_source="Mubert",
                permitted_playback_type="time_limited_stream",
                commercial_use_allowed=True,
                verification_status=LicensingVerificationStatus.VERIFIED.value,
            ),
            refresh_supported=True,
        )

        provider.get_track_stream = MagicMock(side_effect=[expired_info, fresh_info])
        registry = ProviderRegistry(licensing_validator=LicensingValidator(DeploymentMode.NON_COMMERCIAL.value))
        registry.register(provider)

        # Calling get_playback_info with refresh=True should detect expiration and refresh automatically
        resolved = registry.get_playback_info("healthy:exp1", refresh=True)
        self.assertEqual(resolved.playback_url, "https://audio.example.com/fresh.mp3")
        self.assertFalse(resolved.is_expired())

    def test_resilient_http_client_rate_limit_retry_after(self):
        mock_session = MagicMock()
        mock_sleep = MagicMock()

        # Simulate 429 with Retry-After: 1 on first attempt, 200 JSON on second
        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "1.5"}

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {"success": True}

        mock_session.request.side_effect = [resp_429, resp_200]

        client = ResilientHTTPClient(
            provider_name="test_api",
            max_retries=2,
            max_retry_after_seconds=5.0,
            session=mock_session,
            sleep_fn=mock_sleep,
        )

        result = client.request_json("GET", "https://api.example.com/data")
        self.assertEqual(result, {"success": True})
        mock_sleep.assert_called_with(1.5)


if __name__ == "__main__":
    unittest.main()
