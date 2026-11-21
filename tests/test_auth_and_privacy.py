"""Unit and integration tests for Supabase Authentication, PostgreSQL schema,
Privacy compliance (India DPDP Act 2023, US State laws, BIPA), Consent Management,
and In-Memory Frame Processing.
"""
from __future__ import annotations

import base64
import os
import unittest
from unittest.mock import MagicMock, patch

from app import create_app
import config
from database.connection import SupabaseConnectionManager
from database.repository import LocalFallbackRepository, SupabaseRepository
from privacy.consent import ConsentManager


class TestDatabaseAndRepository(unittest.TestCase):
    """Test repository operations, immutable consent ledger, data export, and cascade deletion."""

    def setUp(self):
        self.repo = LocalFallbackRepository(db_path=":memory:")
        self.user_id = "usr_test_12345"
        self.email = "alex@example.com"

    def test_profile_and_preferences_lifecycle(self):
        profile = self.repo.create_profile(
            user_id=self.user_id,
            email=self.email,
            full_name="Alex Morgan",
            country="IN",
        )
        self.assertEqual(profile["id"], self.user_id)
        self.assertEqual(profile["email"], self.email)
        self.assertEqual(profile["country"], "IN")

        by_email = self.repo.get_profile_by_email(self.email)
        self.assertIsNotNone(by_email)
        self.assertEqual(by_email["id"], self.user_id)

        # Update profile
        updated = self.repo.update_profile(self.user_id, full_name="Alex M. Rivera")
        self.assertEqual(updated["full_name"], "Alex M. Rivera")

        # Preferences
        prefs = self.repo.update_preferences(
            self.user_id,
            {
                "preferred_music_provider": "audius",
                "preferred_genres": ["ambient", "lo-fi"],
                "preferred_language": "en",
                "autoplay_enabled": True,
            },
        )
        self.assertEqual(prefs["preferred_music_provider"], "audius")
        self.assertIn("ambient", prefs["preferred_genres"])

    def test_immutable_consent_audit_ledger(self):
        # 1. Initial consent
        rec1 = self.repo.record_consent(
            user_id=self.user_id,
            consent_type="camera_processing",
            policy_version="2026.1",
            accepted=True,
            jurisdiction="IN",
            consent_method="registration_form",
        )
        self.assertTrue(rec1["accepted"])
        self.assertIsNone(rec1["withdrawn_at"])
        self.assertTrue(self.repo.has_consent(self.user_id, "camera_processing"))

        # 2. Withdraw consent
        rec2 = self.repo.withdraw_consent(
            user_id=self.user_id,
            consent_type="camera_processing",
            jurisdiction="IN",
        )
        self.assertIsNotNone(rec2["withdrawn_at"])
        self.assertFalse(self.repo.has_consent(self.user_id, "camera_processing"))

        # 3. Re-grant consent
        rec3 = self.repo.record_consent(
            user_id=self.user_id,
            consent_type="camera_processing",
            policy_version="2026.1",
            accepted=True,
            jurisdiction="IN",
            consent_method="privacy_dashboard_toggle",
        )
        self.assertTrue(self.repo.has_consent(self.user_id, "camera_processing"))

        # 4. Verify immutable audit trail: historical events are preserved, never overwritten
        history = self.repo.get_consent_history(self.user_id)
        self.assertEqual(len(history), 3, "All consent mutations must be preserved in immutable ledger")
        self.assertEqual(history[0]["id"], rec3["id"], "Most recent event appears first")

        status = self.repo.get_consent_status(self.user_id)
        self.assertTrue(status.get("camera_processing"))

    def test_emotion_history_optin_and_clearing(self):
        # 1. Without opt-in consent, emotion events must NOT be recorded (Strict DPDP / GDPR purpose limitation)
        blocked_res = self.repo.record_emotion(self.user_id, detected_emotion="happy", confidence_score=88.5)
        self.assertIsNone(blocked_res)
        self.assertEqual(len(self.repo.get_emotion_history(self.user_id)), 0)

        # 2. Grant explicit affirmative opt-in consent for emotion_history
        self.repo.record_consent(
            user_id=self.user_id,
            consent_type="emotion_history",
            policy_version="1.0",
            accepted=True,
            jurisdiction="IN",
        )

        # 3. Now emotion events are recorded to history
        self.repo.record_emotion(self.user_id, detected_emotion="happy", confidence_score=88.5)
        self.repo.record_emotion(self.user_id, detected_emotion="calm", confidence_score=92.0)

        history = self.repo.get_emotion_history(self.user_id)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["detected_emotion"], "calm")

        # 4. Selective deletion
        deleted_count = self.repo.clear_emotion_history(self.user_id)
        self.assertEqual(deleted_count, 2)
        self.assertEqual(len(self.repo.get_emotion_history(self.user_id)), 0)

    def test_data_portability_export(self):
        self.repo.create_profile(self.user_id, email=self.email, full_name="Alex M.")
        self.repo.update_preferences(self.user_id, {"preferred_music_provider": "jamendo"})
        self.repo.record_consent(
            user_id=self.user_id,
            consent_type="terms_and_conditions",
            policy_version="2026.1",
            accepted=True,
            jurisdiction="US",
        )
        self.repo.record_listen(
            user_id=self.user_id,
            track_id="jamendo:101",
            provider="jamendo",
            track_title="Ambient Waves",
            artist_name="Sound Artist",
        )
        self.repo.set_favorite(
            user_id=self.user_id,
            track_id="jamendo:101",
            provider="jamendo",
            track_title="Ambient Waves",
            artist_name="Sound Artist",
            is_favorite=True,
        )

        export = self.repo.export_user_data(self.user_id)
        self.assertEqual(export["user_id"], self.user_id)
        self.assertIn("profile", export)
        self.assertIn("preferences", export)
        self.assertIn("consents", export)
        self.assertIn("listening_history", export)
        self.assertIn("favorites", export)
        self.assertEqual(len(export["listening_history"]), 1)
        self.assertEqual(len(export["favorites"]), 1)

    def test_cascading_account_deletion(self):
        self.repo.create_profile(self.user_id, email=self.email)
        self.repo.update_preferences(self.user_id, {"theme": "dark"})
        self.repo.record_consent(
            user_id=self.user_id,
            consent_type="privacy_policy",
            policy_version="2026.1",
            accepted=True,
        )
        self.repo.record_emotion(self.user_id, detected_emotion="happy", confidence_score=90.0)
        self.repo.record_listen(
            user_id=self.user_id,
            track_id="audius:202",
            provider="audius",
            track_title="Beat Loop",
            artist_name="Audius Producer",
        )
        self.repo.set_favorite(
            user_id=self.user_id,
            track_id="audius:202",
            provider="audius",
            track_title="Beat Loop",
            artist_name="Audius Producer",
            is_favorite=True,
        )

        # Execute cascading deletion
        res = self.repo.delete_user_account(self.user_id)
        self.assertTrue(res["success"])

        # Verify all child records are permanently erased
        self.assertIsNone(self.repo.get_profile(self.user_id))
        self.assertEqual(len(self.repo.get_consent_history(self.user_id)), 0)
        self.assertEqual(len(self.repo.get_emotion_history(self.user_id)), 0)
        self.assertEqual(len(self.repo.get_listening_history(self.user_id)), 0)
        self.assertEqual(len(self.repo.get_favorites(self.user_id)), 0)


class TestPrivacyAndConsentRoutes(unittest.TestCase):
    """Test Flask routes for legal pages, consent recording/revocation, and data export."""

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["WTF_CSRF_ENABLED"] = False
        self.client = self.app.test_client()

    def test_legal_and_consent_pages_render(self):
        # Privacy Policy
        res_policy = self.client.get("/privacy/policy")
        self.assertEqual(res_policy.status_code, 200)
        self.assertIn(b"Privacy Policy", res_policy.data)
        self.assertIn(b"Digital Personal Data Protection Act", res_policy.data)

        # Terms and Conditions
        res_terms = self.client.get("/privacy/terms")
        self.assertEqual(res_terms.status_code, 200)
        self.assertIn(b"Terms and Conditions", res_terms.data)

        # Standalone Camera Consent
        res_cam = self.client.get("/privacy/camera-consent")
        self.assertEqual(res_cam.status_code, 200)
        self.assertIn(b"Webcam & Facial Emotion Processing Notice", res_cam.data)

    def test_record_and_withdraw_consent_api(self):
        # Record camera consent
        res = self.client.post(
            "/privacy/consent",
            json={
                "consent_type": "camera_processing",
                "accepted": True,
                "jurisdiction": "IN",
                "consent_method": "test_suite",
            },
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertTrue(data["current_consents"]["camera_processing"])

        # Check status endpoint
        res_status = self.client.get("/privacy/status")
        self.assertEqual(res_status.status_code, 200)
        status_data = res_status.get_json()
        self.assertTrue(status_data["consents"]["camera_processing"])

        # Withdraw camera consent
        res_w = self.client.post(
            "/privacy/withdraw",
            json={"consent_type": "camera_processing"},
        )
        self.assertEqual(res_w.status_code, 200)
        w_data = res_w.get_json()
        self.assertFalse(w_data["current_consents"]["camera_processing"])

    def test_data_export_json_attachment(self):
        res = self.client.get("/privacy/export")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, "application/json")
        self.assertIn("attachment; filename=", res.headers.get("Content-Disposition", ""))


class TestCameraConsentAndInMemoryProcessing(unittest.TestCase):
    """Verify strictly in-memory processing (zero disk writes) and consent gating."""

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        # 1x1 dummy JPEG base64
        self.dummy_image = (
            "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP///////////////////////"
            "///////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBAB"
            "AAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="
        )

    def test_analyze_without_camera_consent_returns_403(self):
        with self.client.session_transaction() as sess:
            sess["consents"] = {"camera_processing": False}

        res = self.client.post(
            "/analyze",
            json={"image": self.dummy_image},
        )
        self.assertEqual(res.status_code, 403)
        data = res.get_json()
        self.assertEqual(data.get("consent_required"), "camera_processing")

    def test_analyze_with_consent_processes_strictly_in_memory_and_writes_no_files_to_disk(self):
        # Ensure target file does not exist initially
        if os.path.exists(config.CAPTURED_IMAGE_PATH):
            os.remove(config.CAPTURED_IMAGE_PATH)

        # Grant consent in payload (JIT)
        res = self.client.post(
            "/analyze",
            json={
                "image": self.dummy_image,
                "camera_consent_granted": True,
                "jurisdiction": "IN",
            },
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("dominant_emotion", data)
        self.assertIn("recommendations", data)

        # CRITICAL PRIVACY VERIFICATION: Confirm NO file was written to disk!
        self.assertFalse(
            os.path.exists(config.CAPTURED_IMAGE_PATH),
            f"PRIVACY VIOLATION: Captured image must NEVER be written to disk at {config.CAPTURED_IMAGE_PATH}",
        )

    def test_auto_capture_requires_camera_consent(self):
        with self.client.session_transaction() as sess:
            sess["consents"] = {"camera_processing": False}

        res = self.client.post("/auto-capture", json={"enable": True})
        self.assertEqual(res.status_code, 403)
        data = res.get_json()
        self.assertEqual(data.get("consent_required"), "camera_processing")


class TestUserAuthenticationFlows(unittest.TestCase):
    """Test user registration, unbundled consents, login, profile management, and account deletion."""

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        self.email = "testuser_auth@example.com"
        self.password = "SecurePassword123!"

    def test_register_requires_unbundled_terms_and_privacy_consent(self):
        # Missing terms consent
        res = self.client.post(
            "/auth/register",
            json={
                "email": self.email,
                "password": self.password,
                "consent_terms": False,
                "consent_privacy": True,
            },
        )
        self.assertEqual(res.status_code, 400)

        # Successful registration with unbundled items
        res_ok = self.client.post(
            "/auth/register",
            json={
                "email": self.email,
                "password": self.password,
                "full_name": "Test Auth User",
                "country": "IN",
                "consent_terms": True,
                "consent_privacy": True,
                "consent_camera": True,
                "consent_emotion_history": True,
            },
        )
        self.assertEqual(res_ok.status_code, 200)
        data = res_ok.get_json()
        self.assertTrue(data["success"])
        self.assertTrue(bool(data["user_id"]))

    def test_login_and_protected_route(self):
        # Register user first
        email = "member@example.com"
        self.client.post(
            "/auth/register",
            json={
                "email": email,
                "password": self.password,
                "consent_terms": True,
                "consent_privacy": True,
            },
        )

        # Login
        res_login = self.client.post(
            "/auth/login",
            json={"email": email, "password": self.password},
        )
        self.assertEqual(res_login.status_code, 200)
        token = res_login.get_json()["access_token"]

        # Access protected profile endpoint
        res_profile = self.client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res_profile.status_code, 200)
        data = res_profile.get_json()
        self.assertEqual(data["profile"]["email"], email)

        # Access user dashboard view
        res_dash = self.client.get("/dashboard")
        self.assertEqual(res_dash.status_code, 200)
        self.assertIn(b"User Dashboard", res_dash.data)

        # Logout
        res_logout = self.client.post("/auth/logout")
        self.assertEqual(res_logout.status_code, 200)

    def test_delete_account_lifecycle(self):
        email = "delete_me@example.com"
        reg = self.client.post(
            "/auth/register",
            json={
                "email": email,
                "password": self.password,
                "consent_terms": True,
                "consent_privacy": True,
            },
        )
        token = reg.get_json()["access_token"]

        # Request cascading deletion
        res_del = self.client.post(
            "/auth/delete-account",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res_del.status_code, 200)
        self.assertTrue(res_del.get_json()["success"])


if __name__ == "__main__":
    unittest.main()
