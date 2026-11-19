"""Unit tests for licensing validation rules under Non-Commercial and Commercial policies."""
import unittest

from music.exceptions import LicensingViolationError
from music.licensing import (
    LicensingValidator,
    build_audius_licensing,
    build_jamendo_licensing,
    build_mubert_licensing,
)
from music.models import (
    DeploymentMode,
    LicensingMetadata,
    LicensingVerificationStatus,
    UnifiedTrack,
)


class TestLicensing(unittest.TestCase):
    def test_non_commercial_mode_permits_free_cc_streams(self):
        validator = LicensingValidator(DeploymentMode.NON_COMMERCIAL.value)

        # Jamendo track with CC BY-NC is valid for non-commercial streaming
        jam_lic = build_jamendo_licensing(
            title="Acoustic Morning",
            artist="Folk Trio",
            license_ccurl="https://creativecommons.org/licenses/by-nc/4.0/",
            prourl=None,
            audiodownload_allowed=True,
            has_audio_stream=True,
            commercial_agreement_verified=False,
        )
        track = UnifiedTrack(
            internal_id="jamendo:101",
            provider="jamendo",
            provider_track_id="101",
            title="Acoustic Morning",
            artist="Folk Trio",
            playback_url="https://audio.example.com/stream.mp3",
            is_available=True,
            licensing=jam_lic,
        )

        playable, reason = validator.is_playable(track)
        self.assertTrue(playable)
        self.assertIsNone(reason)

    def test_commercial_mode_blocks_cc_nc_tracks(self):
        validator = LicensingValidator(DeploymentMode.COMMERCIAL.value)

        jam_lic = build_jamendo_licensing(
            title="Non-Commercial Tune",
            artist="Artist X",
            license_ccurl="https://creativecommons.org/licenses/by-nc/4.0/",
            prourl=None,
            audiodownload_allowed=True,
            has_audio_stream=True,
            commercial_agreement_verified=False,
        )
        track = UnifiedTrack(
            internal_id="jamendo:102",
            provider="jamendo",
            provider_track_id="102",
            title="Non-Commercial Tune",
            artist="Artist X",
            playback_url="https://audio.example.com/stream.mp3",
            is_available=True,
            licensing=jam_lic,
        )

        playable, reason = validator.is_playable(track)
        self.assertFalse(playable)
        self.assertIn("commercial", (reason or "").lower())

        with self.assertRaises(LicensingViolationError):
            validator.enforce_playback(track)

    def test_commercial_mode_allows_verified_commercial_clearance(self):
        validator = LicensingValidator(DeploymentMode.COMMERCIAL.value)

        # Jamendo track with verified commercial agreement
        jam_lic = build_jamendo_licensing(
            title="Commercial Track",
            artist="Pro Producer",
            license_ccurl="https://creativecommons.org/licenses/by/4.0/",
            prourl="https://licensing.jamendo.com/track/103",
            audiodownload_allowed=True,
            has_audio_stream=True,
            commercial_agreement_verified=True,
        )
        track = UnifiedTrack(
            internal_id="jamendo:103",
            provider="jamendo",
            provider_track_id="103",
            title="Commercial Track",
            artist="Pro Producer",
            playback_url="https://audio.example.com/stream.mp3",
            is_available=True,
            licensing=jam_lic,
        )

        playable, reason = validator.is_playable(track)
        self.assertTrue(playable)
        self.assertIsNone(reason)

    def test_audius_gated_and_unstreamable_always_blocked(self):
        validator_non_comm = LicensingValidator(DeploymentMode.NON_COMMERCIAL.value)
        validator_comm = LicensingValidator(DeploymentMode.COMMERCIAL.value)

        # Gated track (has stream_conditions)
        gated_lic = build_audius_licensing(
            title="Gated Song",
            artist="Crypto DJ",
            license_str="All Rights Reserved",
            is_streamable=True,
            stream_conditions={"nft": "0x123"},
        )
        gated_track = UnifiedTrack(
            internal_id="audius:gate1",
            provider="audius",
            provider_track_id="gate1",
            title="Gated Song",
            artist="Crypto DJ",
            playback_url="https://audio.example.com/gated.mp3",
            is_available=False,
            licensing=gated_lic,
        )

        self.assertFalse(validator_non_comm.is_playable(gated_track)[0])
        self.assertFalse(validator_comm.is_playable(gated_track)[0])

    def test_mubert_unverified_license_is_blocked(self):
        validator = LicensingValidator(DeploymentMode.COMMERCIAL.value)
        unverified_lic = build_mubert_licensing(title="AI Stream", b2b_license_verified=False)
        track = UnifiedTrack(
            internal_id="mubert:1.0.0",
            provider="mubert",
            provider_track_id="1.0.0",
            title="AI Stream",
            artist="Mubert AI",
            playback_url=None,
            is_available=False,
            licensing=unverified_lic,
        )
        self.assertFalse(validator.is_playable(track)[0])


if __name__ == "__main__":
    unittest.main()
