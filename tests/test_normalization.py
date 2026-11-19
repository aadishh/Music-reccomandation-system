"""Unit tests for UnifiedTrack metadata normalization and internal ID conventions."""
import unittest

from music.models import (
    LicensingMetadata,
    LicensingVerificationStatus,
    UnifiedTrack,
    make_internal_track_id,
    parse_internal_track_id,
)


class TestNormalization(unittest.TestCase):
    def test_internal_track_id_helpers(self):
        tid = make_internal_track_id("jamendo", "456789")
        self.assertEqual(tid, "jamendo:456789")

        provider, pid = parse_internal_track_id("audius:d72kp")
        self.assertEqual(provider, "audius")
        self.assertEqual(pid, "d72kp")

        with self.assertRaises(ValueError):
            parse_internal_track_id("invalid-format")

        with self.assertRaises(ValueError):
            parse_internal_track_id("jamendo:")

    def test_unified_track_complete_schema(self):
        lic = LicensingMetadata(
            license_type="CC BY",
            license_source="Jamendo API v3.0",
            permitted_playback_type="direct_stream",
            commercial_use_allowed=True,
            redistribution_allowed=False,
            attribution_required=True,
            attribution_text="'Track' by Artist via Jamendo (CC BY)",
            license_url="https://creativecommons.org/licenses/by/4.0/",
            verification_status=LicensingVerificationStatus.VERIFIED.value,
        )

        track = UnifiedTrack(
            internal_id="jamendo:999",
            provider="jamendo",
            provider_track_id="999",
            title="Horizon",
            artist="Solar Flares",
            album="Solar System",
            genre="electronic",
            duration=240,
            bpm=124.0,
            energy=0.72,
            mood_tags=["upbeat", "bright"],
            language="en",
            artwork="https://images.example.com/art.jpg",
            preview_url="https://audio.example.com/stream.mp3",
            playback_url="https://audio.example.com/stream.mp3",
            playback_reference="https://jamendo.com/track/999",
            is_available=True,
            licensing=lic,
            provider_metadata={"custom_flag": True, "play_count": 50000},
        )

        d = track.to_dict()

        # Verify all required fields from Unified Track Schema specification
        required_keys = [
            "internal_id",
            "provider",
            "provider_track_id",
            "title",
            "artist",
            "album",
            "genre",
            "duration",
            "bpm",
            "energy",
            "mood_tags",
            "artwork",
            "preview_url",
            "playback_url",
            "playback_reference",
            "license_type",
            "license_source",
            "commercial_usage_status",
            "attribution_requirements",
            "licensing",
            "provider_metadata",
        ]
        for key in required_keys:
            self.assertIn(key, d, f"Missing required UnifiedTrack schema key '{key}'")

        self.assertEqual(d["commercial_usage_status"], "allowed")
        self.assertTrue(d["attribution_requirements"]["required"])
        self.assertIn("Jamendo", d["attribution_requirements"]["text"])
        # Verify provider-specific fields are preserved separately
        self.assertEqual(d["provider_metadata"]["play_count"], 50000)


if __name__ == "__main__":
    unittest.main()
