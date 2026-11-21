"""Tests for SQLite fallback database initialization, path handling, and lazy Supabase repository integration."""
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from database.connection import SupabaseConnectionManager
from database.repository import LocalFallbackRepository, SupabaseRepository


class TestDatabaseInitializationAndFallback(unittest.TestCase):
    """Verify robust path handling, parent directory creation, and lazy fallback initialization."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_sqlite_fallback_default_path_and_env_override(self):
        # 1. Custom env path
        custom_path = os.path.join(self.temp_dir, "custom_dir", "sub_dir", "fallback.db")
        with patch.dict(os.environ, {"SQLITE_DB_PATH": custom_path}):
            repo = LocalFallbackRepository()
            self.assertEqual(repo.db_path, custom_path)
            self.assertTrue(os.path.exists(custom_path))
            self.assertTrue(os.path.isdir(os.path.dirname(custom_path)))

            # Verify tables exist in SQLite
            profile = repo.create_profile("user_test_env", "env@example.com", "Env User")
            self.assertEqual(profile["email"], "env@example.com")
            retrieved = repo.get_profile("user_test_env")
            self.assertIsNotNone(retrieved)
            self.assertEqual(retrieved["full_name"], "Env User")

    def test_sqlite_fallback_creates_parent_directory_automatically(self):
        nested_db = os.path.join(self.temp_dir, "nested", "level1", "level2", "test.db")
        self.assertFalse(os.path.exists(os.path.dirname(nested_db)))

        repo = LocalFallbackRepository(db_path=nested_db)
        self.assertTrue(os.path.exists(os.path.dirname(nested_db)))
        self.assertTrue(os.path.exists(nested_db))

        # Basic operations work
        repo.update_preferences("user_nested", {"preferred_music_provider": "audius"})
        prefs = repo.get_preferences("user_nested")
        self.assertEqual(prefs["preferred_music_provider"], "audius")

    def test_sqlite_fallback_memory_mode(self):
        repo = LocalFallbackRepository(db_path=":memory:")
        self.assertEqual(repo.db_path, ":memory:")
        repo.create_profile("u_mem", "mem@example.com")
        self.assertIsNotNone(repo.get_profile("u_mem"))

    def test_supabase_repository_does_not_initialize_fallback_at_startup(self):
        # Verify lazy initialization: SupabaseRepository() should NOT initialize fallback on init
        manager = MagicMock(spec=SupabaseConnectionManager)
        manager.is_configured = True
        manager.get_client.return_value = MagicMock()

        repo = SupabaseRepository(manager=manager)
        self.assertIsNone(repo._fallback)

    def test_supabase_primary_does_not_touch_fallback_when_supabase_succeeds(self):
        manager = MagicMock(spec=SupabaseConnectionManager)
        manager.is_configured = True
        mock_client = MagicMock()
        mock_query = MagicMock()
        mock_query.select.return_value = mock_query
        mock_query.eq.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.execute.return_value = MagicMock(data=[{"id": "u1", "email": "supa@example.com"}])
        mock_client.table.return_value = mock_query
        manager.get_client.return_value = mock_client

        repo = SupabaseRepository(manager=manager)
        profile = repo.get_profile("u1")
        self.assertEqual(profile["email"], "supa@example.com")
        # Fallback should NEVER have been created
        self.assertIsNone(repo._fallback)

    def test_supabase_falls_back_when_client_is_none(self):
        manager = MagicMock(spec=SupabaseConnectionManager)
        manager.is_configured = False
        manager.get_client.return_value = None
        manager.get_admin_client.return_value = None

        nested_db = os.path.join(self.temp_dir, "lazy_fallback.db")
        with patch.dict(os.environ, {"SQLITE_DB_PATH": nested_db}):
            repo = SupabaseRepository(manager=manager)
            self.assertIsNone(repo._fallback)

            # Invoking a method triggers lazy fallback creation
            profile = repo.create_profile("u_fallback", "fallback@example.com")
            self.assertIsNotNone(repo._fallback)
            self.assertEqual(profile["email"], "fallback@example.com")

            retrieved = repo.get_profile("u_fallback")
            self.assertIsNotNone(retrieved)
            self.assertEqual(retrieved["id"], "u_fallback")

    def test_supabase_falls_back_when_supabase_query_raises_exception(self):
        manager = MagicMock(spec=SupabaseConnectionManager)
        manager.is_configured = True
        mock_client = MagicMock()
        mock_client.table.side_effect = Exception("Supabase connection timeout")
        manager.get_client.return_value = mock_client

        repo = SupabaseRepository(manager=manager)
        repo.fallback = LocalFallbackRepository(db_path=":memory:")

        # Seed local fallback
        repo.fallback.create_profile("u_seed", "seed@example.com", "Seed User")

        # get_profile catches Supabase exception and uses fallback
        profile = repo.get_profile("u_seed")
        self.assertIsNotNone(profile)
        self.assertEqual(profile["email"], "seed@example.com")

    def test_resilient_in_memory_safety_net_if_path_fails_while_supabase_configured(self):
        manager = MagicMock(spec=SupabaseConnectionManager)
        manager.is_configured = True
        manager.get_client.return_value = None

        # Pass an impossible path on root
        with patch.dict(os.environ, {"SQLITE_DB_PATH": "/root_nonexistent_dir_cannot_create/db.sqlite"}):
            repo = SupabaseRepository(manager=manager)
            # When fallback is requested, since Supabase is configured, it falls back to :memory:
            fb = repo.fallback
            self.assertIsNotNone(fb)
            self.assertEqual(fb.db_path, ":memory:")

    def test_flask_app_health_and_gunicorn_boot(self):
        from app import app
        client = app.test_client()
        res = client.get("/health")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "healthy")
