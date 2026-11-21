"""Repository layer providing unified data access over Supabase PostgreSQL.

Includes an automatic fallback repository for local/testing execution when Supabase
credentials are not yet configured.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database.connection import SupabaseConnectionManager, db_manager

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LocalFallbackRepository:
    """Thread-safe SQLite repository used in local testing and when Supabase credentials are unset."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            db_path = os.getenv("SQLITE_DB_PATH", "/tmp/music_recommender.db")
        self.db_path = db_path
        self._lock = threading.RLock()
        self._memory_conn: Optional[sqlite3.Connection] = None
        if self.db_path == ":memory:":
            self._memory_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._memory_conn.row_factory = sqlite3.Row
        else:
            self._ensure_parent_dir_and_writable()
        self._init_schema()

    def _ensure_parent_dir_and_writable(self) -> None:
        """Ensure parent directory exists and verify database path writability."""
        parent = os.path.dirname(os.path.abspath(self.db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
            if not os.access(parent, os.W_OK):
                raise PermissionError(
                    f"Parent directory '{parent}' is not writable for SQLite fallback database '{self.db_path}'"
                )
        if os.path.exists(self.db_path) and not os.access(self.db_path, os.W_OK):
            raise PermissionError(f"SQLite fallback database file '{self.db_path}' is not writable")

    def _connect(self) -> sqlite3.Connection:
        if self._memory_conn is not None:
            return self._memory_conn
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _close_if_file(self, conn: sqlite3.Connection) -> None:
        if self._memory_conn is None:
            conn.close()

    def _init_schema(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS profiles (
                        id TEXT PRIMARY KEY,
                        full_name TEXT,
                        email TEXT NOT NULL,
                        avatar_url TEXT,
                        country TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS user_preferences (
                        user_id TEXT PRIMARY KEY REFERENCES profiles(id),
                        preferred_music_provider TEXT DEFAULT 'jamendo',
                        preferred_genres TEXT DEFAULT '[]',
                        preferred_language TEXT DEFAULT '',
                        theme TEXT DEFAULT 'dark',
                        autoplay_enabled INTEGER DEFAULT 1,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS consent_records (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        consent_type TEXT NOT NULL,
                        policy_version TEXT NOT NULL,
                        accepted INTEGER NOT NULL,
                        consent_timestamp TEXT NOT NULL,
                        withdrawn_at TEXT,
                        jurisdiction TEXT NOT NULL,
                        consent_method TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS emotion_history (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        detected_emotion TEXT NOT NULL,
                        confidence_score REAL NOT NULL,
                        detected_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS listening_history (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        track_id TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        track_title TEXT NOT NULL,
                        artist_name TEXT NOT NULL,
                        played_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS favorite_tracks (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        track_id TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        track_title TEXT NOT NULL,
                        artist_name TEXT NOT NULL,
                        thumbnail_url TEXT,
                        created_at TEXT NOT NULL,
                        UNIQUE(user_id, track_id)
                    );

                    CREATE TABLE IF NOT EXISTS policy_versions (
                        id TEXT PRIMARY KEY,
                        policy_type TEXT NOT NULL,
                        version TEXT NOT NULL,
                        content TEXT NOT NULL,
                        effective_date TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        UNIQUE(policy_type, version)
                    );

                    CREATE TABLE IF NOT EXISTS privacy_requests (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        request_type TEXT NOT NULL,
                        status TEXT NOT NULL,
                        requested_at TEXT NOT NULL,
                        completed_at TEXT
                    );

                    CREATE TABLE IF NOT EXISTS security_audit_logs (
                        id TEXT PRIMARY KEY,
                        user_id TEXT,
                        event_type TEXT NOT NULL,
                        ip_address TEXT,
                        user_agent TEXT,
                        details TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    """
                )
                # Seed default policy versions
                now = _now_iso()
                for p_type in ["privacy_policy", "terms_and_conditions", "camera_processing"]:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO policy_versions (id, policy_type, version, content, effective_date, created_at)
                        VALUES (?, ?, '1.0', ?, ?, ?)
                        """,
                        (f"seed-{p_type}", p_type, f"Standard {p_type} v1.0", now, now),
                    )
                conn.commit()
            finally:
                self._close_if_file(conn)

    # --- Profiles ---
    def get_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute("SELECT * FROM profiles WHERE id = ?", (user_id,)).fetchone()
                return dict(row) if row else None
            finally:
                self._close_if_file(conn)

    def get_profile_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM profiles WHERE lower(email) = lower(?)", (email.strip(),)
                ).fetchone()
                return dict(row) if row else None
            finally:
                self._close_if_file(conn)

    def create_profile(
        self,
        user_id: str,
        email: str,
        full_name: str = "",
        avatar_url: str = "",
        country: str = "",
    ) -> Dict[str, Any]:
        return self.upsert_profile(
            user_id,
            {"email": email, "full_name": full_name, "avatar_url": avatar_url, "country": country},
        )

    def update_profile(
        self,
        user_id: str,
        full_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        country: Optional[str] = None,
    ) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        if full_name is not None:
            data["full_name"] = full_name
        if avatar_url is not None:
            data["avatar_url"] = avatar_url
        if country is not None:
            data["country"] = country
        return self.upsert_profile(user_id, data)

    def upsert_profile(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        now = _now_iso()
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO profiles (id, full_name, email, avatar_url, country, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        full_name = COALESCE(excluded.full_name, profiles.full_name),
                        email = COALESCE(excluded.email, profiles.email),
                        avatar_url = COALESCE(excluded.avatar_url, profiles.avatar_url),
                        country = COALESCE(excluded.country, profiles.country),
                        updated_at = excluded.updated_at
                    """,
                    (
                        user_id,
                        data.get("full_name", ""),
                        data.get("email", ""),
                        data.get("avatar_url", ""),
                        data.get("country", ""),
                        now,
                        now,
                    ),
                )
                conn.commit()
                return self.get_profile(user_id) or {}
            finally:
                self._close_if_file(conn)

    # --- Preferences ---
    def get_preferences(self, user_id: str) -> Dict[str, Any]:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute("SELECT * FROM user_preferences WHERE user_id = ?", (user_id,)).fetchone()
                if not row:
                    return {
                        "user_id": user_id,
                        "preferred_music_provider": "jamendo",
                        "preferred_genres": [],
                        "preferred_language": "",
                        "theme": "dark",
                        "autoplay_enabled": True,
                    }
                d = dict(row)
                d["preferred_genres"] = json.loads(d["preferred_genres"] or "[]")
                d["autoplay_enabled"] = bool(d["autoplay_enabled"])
                return d
            finally:
                self._close_if_file(conn)

    def update_preferences(
        self,
        user_id: str,
        data: Optional[Dict[str, Any]] = None,
        preferences: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        data = preferences if preferences is not None else (data or {})
        now = _now_iso()
        genres = json.dumps(data.get("preferred_genres", []))
        provider = data.get("preferred_music_provider", "jamendo")
        lang = data.get("preferred_language", "")
        theme = data.get("theme", "dark")
        autoplay = 1 if data.get("autoplay_enabled", True) else 0

        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO user_preferences
                        (user_id, preferred_music_provider, preferred_genres, preferred_language, theme, autoplay_enabled, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        preferred_music_provider = excluded.preferred_music_provider,
                        preferred_genres = excluded.preferred_genres,
                        preferred_language = excluded.preferred_language,
                        theme = excluded.theme,
                        autoplay_enabled = excluded.autoplay_enabled,
                        updated_at = excluded.updated_at
                    """,
                    (user_id, provider, genres, lang, theme, autoplay, now),
                )
                conn.commit()
                return self.get_preferences(user_id)
            finally:
                self._close_if_file(conn)

    get_user_preferences = get_preferences
    update_user_preferences = update_preferences

    # --- Consent Records ---
    def record_consent(
        self,
        *,
        user_id: str,
        consent_type: str,
        policy_version: str,
        accepted: bool,
        jurisdiction: str = "OTHER",
        consent_method: str = "web_explicit_checkbox",
    ) -> Dict[str, Any]:
        import uuid
        record_id = str(uuid.uuid4())
        now = _now_iso()
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO consent_records
                        (id, user_id, consent_type, policy_version, accepted, consent_timestamp, jurisdiction, consent_method, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record_id,
                        user_id,
                        consent_type,
                        policy_version,
                        1 if accepted else 0,
                        now,
                        jurisdiction,
                        consent_method,
                        now,
                    ),
                )
                conn.commit()
            finally:
                self._close_if_file(conn)
        return {
            "id": record_id,
            "user_id": user_id,
            "consent_type": consent_type,
            "policy_version": policy_version,
            "accepted": accepted,
            "consent_timestamp": now,
            "withdrawn_at": None,
            "jurisdiction": jurisdiction,
            "consent_method": consent_method,
        }

    def withdraw_consent(self, user_id: str, consent_type: str, jurisdiction: str = "OTHER") -> Dict[str, Any]:
        now = _now_iso()
        # Mark recent accepted record as withdrawn and append explicit withdrawal event
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    UPDATE consent_records
                    SET withdrawn_at = ?
                    WHERE user_id = ? AND consent_type = ? AND accepted = 1 AND withdrawn_at IS NULL
                    """,
                    (now, user_id, consent_type),
                )
                conn.commit()
            finally:
                self._close_if_file(conn)

        rec = self.record_consent(
            user_id=user_id,
            consent_type=consent_type,
            policy_version="1.0",
            accepted=False,
            jurisdiction=jurisdiction,
            consent_method="web_modal_button",
        )
        rec["withdrawn_at"] = now
        return rec

    def has_consent(self, user_id: str, consent_type: str) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    """
                    SELECT accepted, withdrawn_at FROM consent_records
                    WHERE user_id = ? AND consent_type = ?
                    ORDER BY consent_timestamp DESC LIMIT 1
                    """,
                    (user_id, consent_type),
                ).fetchone()
                if not row:
                    return False
                return bool(row["accepted"]) and (row["withdrawn_at"] is None)
            finally:
                self._close_if_file(conn)

    def get_consent_status(self, user_id: str) -> Dict[str, bool]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT consent_type, accepted, withdrawn_at FROM (
                        SELECT consent_type, accepted, withdrawn_at,
                               ROW_NUMBER() OVER(PARTITION BY consent_type ORDER BY consent_timestamp DESC) as rn
                        FROM consent_records WHERE user_id = ?
                    ) WHERE rn = 1
                    """,
                    (user_id,),
                ).fetchall()
                status: Dict[str, bool] = {}
                for r in rows:
                    status[r["consent_type"]] = bool(r["accepted"]) and (r["withdrawn_at"] is None)
                return status
            finally:
                self._close_if_file(conn)

    def get_consent_history(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT * FROM consent_records WHERE user_id = ?
                    ORDER BY consent_timestamp DESC LIMIT ?
                    """,
                    (user_id, limit),
                ).fetchall()
                result = []
                for r in rows:
                    item = dict(r)
                    item["accepted"] = bool(item["accepted"])
                    result.append(item)
                return result
            finally:
                self._close_if_file(conn)

    # --- Emotion History ---
    def record_emotion(self, user_id: str, detected_emotion: str, confidence_score: float) -> Optional[Dict[str, Any]]:
        if not self.has_consent(user_id, "emotion_history"):
            logger.info("Emotion record skipped: user '%s' has not consented to emotion_history.", user_id)
            return None

        import uuid
        record_id = str(uuid.uuid4())
        now = _now_iso()
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO emotion_history (id, user_id, detected_emotion, confidence_score, detected_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (record_id, user_id, detected_emotion, float(confidence_score), now),
                )
                conn.commit()
            finally:
                self._close_if_file(conn)
        return {
            "id": record_id,
            "user_id": user_id,
            "detected_emotion": detected_emotion,
            "confidence_score": confidence_score,
            "detected_at": now,
        }

    def get_emotion_history(self, user_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM emotion_history WHERE user_id = ? ORDER BY detected_at DESC LIMIT ?",
                    (user_id, limit),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                self._close_if_file(conn)

    def delete_emotion_history(self, user_id: str) -> int:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute("DELETE FROM emotion_history WHERE user_id = ?", (user_id,))
                conn.commit()
                return cur.rowcount
            finally:
                self._close_if_file(conn)

    clear_emotion_history = delete_emotion_history

    # --- Listening History ---
    def record_listen(
        self,
        *,
        user_id: str,
        track_id: str,
        provider: str,
        track_title: str,
        artist_name: str,
    ) -> Dict[str, Any]:
        import uuid
        record_id = str(uuid.uuid4())
        now = _now_iso()
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO listening_history (id, user_id, track_id, provider, track_title, artist_name, played_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (record_id, user_id, track_id, provider, track_title, artist_name, now),
                )
                conn.commit()
            finally:
                self._close_if_file(conn)
        return {
            "id": record_id,
            "user_id": user_id,
            "track_id": track_id,
            "provider": provider,
            "track_title": track_title,
            "artist_name": artist_name,
            "played_at": now,
        }

    def get_listening_history(self, user_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM listening_history WHERE user_id = ? ORDER BY played_at DESC LIMIT ?",
                    (user_id, limit),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                self._close_if_file(conn)

    def delete_listening_history(self, user_id: str) -> int:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute("DELETE FROM listening_history WHERE user_id = ?", (user_id,))
                conn.commit()
                return cur.rowcount
            finally:
                self._close_if_file(conn)

    clear_listening_history = delete_listening_history

    # --- Favorites ---
    def set_favorite(
        self,
        *,
        user_id: str,
        track_id: str,
        provider: str,
        track_title: str,
        artist_name: str,
        thumbnail_url: Optional[str] = None,
        is_favorite: bool = True,
    ) -> Dict[str, Any]:
        import uuid
        now = _now_iso()
        with self._lock:
            conn = self._connect()
            try:
                if is_favorite:
                    conn.execute(
                        """
                        INSERT INTO favorite_tracks (id, user_id, track_id, provider, track_title, artist_name, thumbnail_url, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(user_id, track_id) DO UPDATE SET
                            track_title = excluded.track_title,
                            artist_name = excluded.artist_name,
                            thumbnail_url = excluded.thumbnail_url
                        """,
                        (str(uuid.uuid4()), user_id, track_id, provider, track_title, artist_name, thumbnail_url or "", now),
                    )
                else:
                    conn.execute(
                        "DELETE FROM favorite_tracks WHERE user_id = ? AND track_id = ?",
                        (user_id, track_id),
                    )
                conn.commit()
            finally:
                self._close_if_file(conn)
        return {"track_id": track_id, "is_favorite": is_favorite, "updated_at": now}

    def get_favorites(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM favorite_tracks WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                    (user_id, limit),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                self._close_if_file(conn)

    # --- Policy Versions ---
    def get_policy_version(self, policy_type: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM policy_versions WHERE policy_type = ? ORDER BY effective_date DESC LIMIT 1",
                    (policy_type,),
                ).fetchone()
                return dict(row) if row else None
            finally:
                self._close_if_file(conn)

    def list_policies(self) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute("SELECT * FROM policy_versions ORDER BY policy_type, effective_date DESC").fetchall()
                return [dict(r) for r in rows]
            finally:
                self._close_if_file(conn)

    # --- Privacy Requests, Data Export & Deletion ---
    def create_privacy_request(self, user_id: str, request_type: str) -> Dict[str, Any]:
        import uuid
        req_id = str(uuid.uuid4())
        now = _now_iso()
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT INTO privacy_requests (id, user_id, request_type, status, requested_at) VALUES (?, ?, ?, 'pending', ?)",
                    (req_id, user_id, request_type, now),
                )
                conn.commit()
            finally:
                self._close_if_file(conn)
        return {"id": req_id, "user_id": user_id, "request_type": request_type, "status": "pending", "requested_at": now}

    def get_privacy_requests(self, user_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute("SELECT * FROM privacy_requests WHERE user_id = ? ORDER BY requested_at DESC", (user_id,)).fetchall()
                return [dict(r) for r in rows]
            finally:
                self._close_if_file(conn)

    def export_user_data(self, user_id: str) -> Dict[str, Any]:
        """Compile a complete JSON bundle of all personal data held for the user."""
        profile = self.get_profile(user_id) or {}
        preferences = self.get_preferences(user_id)
        consents = self.get_consent_history(user_id, limit=500)
        emotions = self.get_emotion_history(user_id, limit=1000)
        listens = self.get_listening_history(user_id, limit=1000)
        favorites = self.get_favorites(user_id, limit=1000)
        privacy_reqs = self.get_privacy_requests(user_id)

        now = _now_iso()
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE privacy_requests SET status = 'completed', completed_at = ? WHERE user_id = ? AND request_type = 'data_export' AND status = 'pending'",
                    (now, user_id),
                )
                conn.commit()
            finally:
                self._close_if_file(conn)

        return {
            "user_id": user_id,
            "exported_at": now,
            "export_metadata": {
                "user_id": user_id,
                "exported_at": now,
                "format_version": "1.0",
                "application": "DeepFace Emotion Music Recommender",
            },
            "profile": profile,
            "preferences": preferences,
            "consents": consents,
            "consent_audit_trail": consents,
            "emotion_history": emotions,
            "listening_history": listens,
            "favorites": favorites,
            "favorite_tracks": favorites,
            "privacy_requests": privacy_reqs,
        }

    def delete_user_account(self, user_id: str) -> Dict[str, Any]:
        """Cascade delete all user data across all tables."""
        now = _now_iso()
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("DELETE FROM user_preferences WHERE user_id = ?", (user_id,))
                conn.execute("DELETE FROM emotion_history WHERE user_id = ?", (user_id,))
                conn.execute("DELETE FROM listening_history WHERE user_id = ?", (user_id,))
                conn.execute("DELETE FROM favorite_tracks WHERE user_id = ?", (user_id,))
                conn.execute("DELETE FROM consent_records WHERE user_id = ?", (user_id,))
                conn.execute("DELETE FROM privacy_requests WHERE user_id = ?", (user_id,))
                conn.execute("DELETE FROM profiles WHERE id = ?", (user_id,))
                conn.commit()
            finally:
                self._close_if_file(conn)
        return {"success": True, "user_id": user_id, "deleted_at": now}

    # --- Security Audit ---
    def log_security_event(
        self,
        *,
        user_id: Optional[str],
        event_type: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        import uuid
        record_id = str(uuid.uuid4())
        now = _now_iso()
        detail_json = json.dumps(details or {})
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO security_audit_logs (id, user_id, event_type, ip_address, user_agent, details, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (record_id, user_id, event_type, ip_address or "", user_agent or "", detail_json, now),
                )
                conn.commit()
            finally:
                self._close_if_file(conn)


class SupabaseRepository:
    """Production repository executing queries against Supabase PostgreSQL via SDK."""

    def __init__(
        self,
        manager: Optional[SupabaseConnectionManager] = None,
        fallback: Optional[LocalFallbackRepository] = None,
    ) -> None:
        self.manager = manager or db_manager
        self._fallback: Optional[LocalFallbackRepository] = fallback
        self._fallback_lock = threading.RLock()

    @property
    def fallback(self) -> LocalFallbackRepository:
        """Lazily initialize fallback repository only when needed."""
        if self._fallback is None:
            with self._fallback_lock:
                if self._fallback is None:
                    self._fallback = self._init_fallback()
        return self._fallback

    @fallback.setter
    def fallback(self, value: Optional[LocalFallbackRepository]) -> None:
        self._fallback = value

    def _init_fallback(self) -> LocalFallbackRepository:
        """Initialize the local SQLite fallback repository with graceful error handling."""
        try:
            return LocalFallbackRepository()
        except Exception as exc:
            logger.error("Failed to initialize SQLite fallback repository at configured path: %s", exc)
            # If primary Supabase is configured and operational, attempt in-memory fallback
            # so operations needing fallback can continue without crashing the worker
            if self.manager.is_configured:
                try:
                    logger.warning("Attempting in-memory SQLite fallback repository as resilient safety net")
                    return LocalFallbackRepository(db_path=":memory:")
                except Exception as mem_exc:
                    logger.error("In-memory SQLite fallback also failed: %s", mem_exc)
            raise

    def _client(self, user_jwt: Optional[str] = None):
        client = self.manager.get_client(user_jwt)
        return client

    def _admin_client(self):
        admin = self.manager.get_admin_client()
        return admin or self._client()

    # --- Profiles ---
    def get_profile(self, user_id: str, user_jwt: Optional[str] = None) -> Optional[Dict[str, Any]]:
        client = self._client(user_jwt)
        if client is None:
            return self.fallback.get_profile(user_id)
        try:
            res = client.table("profiles").select("*").eq("id", user_id).limit(1).execute()
            data = res.data or []
            return data[0] if data else None
        except Exception as exc:
            logger.error("Supabase get_profile error: %s", exc)
            return self.fallback.get_profile(user_id)

    def get_profile_by_email(self, email: str, user_jwt: Optional[str] = None) -> Optional[Dict[str, Any]]:
        admin = self._admin_client() or self._client(user_jwt)
        if admin is None:
            return self.fallback.get_profile_by_email(email)
        try:
            res = admin.table("profiles").select("*").ilike("email", email.strip()).limit(1).execute()
            data = res.data or []
            return data[0] if data else None
        except Exception as exc:
            logger.error("Supabase get_profile_by_email error: %s", exc)
            return self.fallback.get_profile_by_email(email)

    def create_profile(
        self,
        user_id: str,
        email: str,
        full_name: str = "",
        avatar_url: str = "",
        country: str = "",
        user_jwt: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.upsert_profile(
            user_id,
            {"email": email, "full_name": full_name, "avatar_url": avatar_url, "country": country},
            user_jwt=user_jwt,
        )

    def update_profile(
        self,
        user_id: str,
        full_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        country: Optional[str] = None,
        user_jwt: Optional[str] = None,
    ) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        if full_name is not None:
            data["full_name"] = full_name
        if avatar_url is not None:
            data["avatar_url"] = avatar_url
        if country is not None:
            data["country"] = country
        return self.upsert_profile(user_id, data, user_jwt=user_jwt)

    def upsert_profile(self, user_id: str, data: Dict[str, Any], user_jwt: Optional[str] = None) -> Dict[str, Any]:
        client = self._client(user_jwt) or self._admin_client()
        if client is None:
            return self.fallback.upsert_profile(user_id, data)
        try:
            payload = {
                "id": user_id,
                "full_name": data.get("full_name", ""),
                "email": data.get("email", ""),
                "avatar_url": data.get("avatar_url", ""),
                "country": data.get("country", ""),
                "updated_at": _now_iso(),
            }
            res = client.table("profiles").upsert(payload).execute()
            return (res.data or [payload])[0]
        except Exception as exc:
            logger.error("Supabase upsert_profile error: %s", exc)
            return self.fallback.upsert_profile(user_id, data)

    # --- Preferences ---
    def get_preferences(self, user_id: str, user_jwt: Optional[str] = None) -> Dict[str, Any]:
        client = self._client(user_jwt)
        if client is None:
            return self.fallback.get_preferences(user_id)
        try:
            res = client.table("user_preferences").select("*").eq("user_id", user_id).limit(1).execute()
            data = res.data or []
            if data:
                return data[0]
            # Create default preferences row if not present
            default_pref = {
                "user_id": user_id,
                "preferred_music_provider": "jamendo",
                "preferred_genres": [],
                "preferred_language": "",
                "theme": "dark",
                "autoplay_enabled": True,
            }
            client.table("user_preferences").insert(default_pref).execute()
            return default_pref
        except Exception as exc:
            logger.error("Supabase get_preferences error: %s", exc)
            return self.fallback.get_preferences(user_id)

    def update_preferences(
        self,
        user_id: str,
        data: Optional[Dict[str, Any]] = None,
        preferences: Optional[Dict[str, Any]] = None,
        user_jwt: Optional[str] = None,
    ) -> Dict[str, Any]:
        data = preferences if preferences is not None else (data or {})
        client = self._client(user_jwt) or self._admin_client()
        if client is None:
            return self.fallback.update_preferences(user_id, data)
        try:
            payload = {
                "user_id": user_id,
                "preferred_music_provider": data.get("preferred_music_provider", "jamendo"),
                "preferred_genres": data.get("preferred_genres", []),
                "preferred_language": data.get("preferred_language", ""),
                "theme": data.get("theme", "dark"),
                "autoplay_enabled": bool(data.get("autoplay_enabled", True)),
                "updated_at": _now_iso(),
            }
            res = client.table("user_preferences").upsert(payload).execute()
            return (res.data or [payload])[0]
        except Exception as exc:
            logger.error("Supabase update_preferences error: %s", exc)
            return self.fallback.update_preferences(user_id, data)

    get_user_preferences = get_preferences
    update_user_preferences = update_preferences


    # --- Consent Records ---
    def record_consent(
        self,
        *,
        user_id: str,
        consent_type: str,
        policy_version: str,
        accepted: bool,
        jurisdiction: str = "OTHER",
        consent_method: str = "web_explicit_checkbox",
        user_jwt: Optional[str] = None,
    ) -> Dict[str, Any]:
        client = self._client(user_jwt) or self._admin_client()
        if client is None:
            return self.fallback.record_consent(
                user_id=user_id,
                consent_type=consent_type,
                policy_version=policy_version,
                accepted=accepted,
                jurisdiction=jurisdiction,
                consent_method=consent_method,
            )
        try:
            payload = {
                "user_id": user_id,
                "consent_type": consent_type,
                "policy_version": policy_version,
                "accepted": bool(accepted),
                "consent_timestamp": _now_iso(),
                "jurisdiction": jurisdiction,
                "consent_method": consent_method,
            }
            res = client.table("consent_records").insert(payload).execute()
            return (res.data or [payload])[0]
        except Exception as exc:
            logger.error("Supabase record_consent error: %s", exc)
            return self.fallback.record_consent(
                user_id=user_id,
                consent_type=consent_type,
                policy_version=policy_version,
                accepted=accepted,
                jurisdiction=jurisdiction,
                consent_method=consent_method,
            )

    def withdraw_consent(self, user_id: str, consent_type: str, jurisdiction: str = "OTHER", user_jwt: Optional[str] = None) -> Dict[str, Any]:
        client = self._client(user_jwt) or self._admin_client()
        if client is None:
            return self.fallback.withdraw_consent(user_id, consent_type, jurisdiction)
        try:
            now = _now_iso()
            # Update previous accepted records with withdrawn_at
            client.table("consent_records").update({"withdrawn_at": now}).eq("user_id", user_id).eq("consent_type", consent_type).eq("accepted", True).is_("withdrawn_at", "null").execute()
            # Insert explicit withdrawal event record into audit log
            rec = self.record_consent(
                user_id=user_id,
                consent_type=consent_type,
                policy_version="1.0",
                accepted=False,
                jurisdiction=jurisdiction,
                consent_method="web_modal_button",
                user_jwt=user_jwt,
            )
            rec["withdrawn_at"] = now
            return rec
        except Exception as exc:
            logger.error("Supabase withdraw_consent error: %s", exc)
            return self.fallback.withdraw_consent(user_id, consent_type, jurisdiction)

    def has_consent(self, user_id: str, consent_type: str, user_jwt: Optional[str] = None) -> bool:
        client = self._client(user_jwt)
        if client is None:
            return self.fallback.has_consent(user_id, consent_type)
        try:
            res = (
                client.table("consent_records")
                .select("accepted, withdrawn_at")
                .eq("user_id", user_id)
                .eq("consent_type", consent_type)
                .order("consent_timestamp", desc=True)
                .limit(1)
                .execute()
            )
            data = res.data or []
            if not data:
                return False
            row = data[0]
            return bool(row.get("accepted")) and (row.get("withdrawn_at") is None)
        except Exception as exc:
            logger.error("Supabase has_consent error: %s", exc)
            return self.fallback.has_consent(user_id, consent_type)

    def get_consent_status(self, user_id: str, user_jwt: Optional[str] = None) -> Dict[str, bool]:
        client = self._client(user_jwt)
        if client is None:
            return self.fallback.get_consent_status(user_id)
        try:
            res = (
                client.table("consent_records")
                .select("consent_type, accepted, withdrawn_at, consent_timestamp")
                .eq("user_id", user_id)
                .order("consent_timestamp", desc=True)
                .execute()
            )
            status: Dict[str, bool] = {}
            for r in res.data or []:
                ctype = r["consent_type"]
                if ctype not in status:
                    status[ctype] = bool(r["accepted"]) and (r.get("withdrawn_at") is None)
            return status
        except Exception as exc:
            logger.error("Supabase get_consent_status error: %s", exc)
            return self.fallback.get_consent_status(user_id)

    def get_consent_history(self, user_id: str, limit: int = 50, user_jwt: Optional[str] = None) -> List[Dict[str, Any]]:
        client = self._client(user_jwt)
        if client is None:
            return self.fallback.get_consent_history(user_id, limit)
        try:
            res = (
                client.table("consent_records")
                .select("*")
                .eq("user_id", user_id)
                .order("consent_timestamp", desc=True)
                .limit(limit)
                .execute()
            )
            return res.data or []
        except Exception as exc:
            logger.error("Supabase get_consent_history error: %s", exc)
            return self.fallback.get_consent_history(user_id, limit)

    # --- Emotion History ---
    def record_emotion(self, user_id: str, detected_emotion: str, confidence_score: float, user_jwt: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if not self.has_consent(user_id, "emotion_history", user_jwt=user_jwt):
            logger.info("Emotion recording skipped: user '%s' has not opted into emotion_history.", user_id)
            return None

        client = self._client(user_jwt) or self._admin_client()
        if client is None:
            return self.fallback.record_emotion(user_id, detected_emotion, confidence_score)
        try:
            payload = {
                "user_id": user_id,
                "detected_emotion": detected_emotion,
                "confidence_score": float(confidence_score),
                "detected_at": _now_iso(),
            }
            res = client.table("emotion_history").insert(payload).execute()
            return (res.data or [payload])[0]
        except Exception as exc:
            logger.error("Supabase record_emotion error: %s", exc)
            return self.fallback.record_emotion(user_id, detected_emotion, confidence_score)

    def get_emotion_history(self, user_id: str, limit: int = 30, user_jwt: Optional[str] = None) -> List[Dict[str, Any]]:
        client = self._client(user_jwt)
        if client is None:
            return self.fallback.get_emotion_history(user_id, limit)
        try:
            res = client.table("emotion_history").select("*").eq("user_id", user_id).order("detected_at", desc=True).limit(limit).execute()
            return res.data or []
        except Exception as exc:
            logger.error("Supabase get_emotion_history error: %s", exc)
            return self.fallback.get_emotion_history(user_id, limit)

    def delete_emotion_history(self, user_id: str, user_jwt: Optional[str] = None) -> int:
        client = self._client(user_jwt) or self._admin_client()
        if client is None:
            return self.fallback.delete_emotion_history(user_id)
        try:
            res = client.table("emotion_history").delete().eq("user_id", user_id).execute()
            return len(res.data or [])
        except Exception as exc:
            logger.error("Supabase delete_emotion_history error: %s", exc)
            return self.fallback.delete_emotion_history(user_id)

    clear_emotion_history = delete_emotion_history

    # --- Listening History ---
    def record_listen(
        self,
        *,
        user_id: str,
        track_id: str,
        provider: str,
        track_title: str,
        artist_name: str,
        user_jwt: Optional[str] = None,
    ) -> Dict[str, Any]:
        client = self._client(user_jwt) or self._admin_client()
        if client is None:
            return self.fallback.record_listen(
                user_id=user_id,
                track_id=track_id,
                provider=provider,
                track_title=track_title,
                artist_name=artist_name,
            )
        try:
            payload = {
                "user_id": user_id,
                "track_id": track_id,
                "provider": provider,
                "track_title": track_title,
                "artist_name": artist_name,
                "played_at": _now_iso(),
            }
            res = client.table("listening_history").insert(payload).execute()
            return (res.data or [payload])[0]
        except Exception as exc:
            logger.error("Supabase record_listen error: %s", exc)
            return self.fallback.record_listen(
                user_id=user_id,
                track_id=track_id,
                provider=provider,
                track_title=track_title,
                artist_name=artist_name,
            )

    def get_listening_history(self, user_id: str, limit: int = 30, user_jwt: Optional[str] = None) -> List[Dict[str, Any]]:
        client = self._client(user_jwt)
        if client is None:
            return self.fallback.get_listening_history(user_id, limit)
        try:
            res = client.table("listening_history").select("*").eq("user_id", user_id).order("played_at", desc=True).limit(limit).execute()
            return res.data or []
        except Exception as exc:
            logger.error("Supabase get_listening_history error: %s", exc)
            return self.fallback.get_listening_history(user_id, limit)

    def delete_listening_history(self, user_id: str, user_jwt: Optional[str] = None) -> int:
        client = self._client(user_jwt) or self._admin_client()
        if client is None:
            return self.fallback.delete_listening_history(user_id)
        try:
            res = client.table("listening_history").delete().eq("user_id", user_id).execute()
            return len(res.data or [])
        except Exception as exc:
            logger.error("Supabase delete_listening_history error: %s", exc)
            return self.fallback.delete_listening_history(user_id)

    clear_listening_history = delete_listening_history

    # --- Favorites ---
    def set_favorite(
        self,
        *,
        user_id: str,
        track_id: str,
        provider: str,
        track_title: str,
        artist_name: str,
        thumbnail_url: Optional[str] = None,
        is_favorite: bool = True,
        user_jwt: Optional[str] = None,
    ) -> Dict[str, Any]:
        client = self._client(user_jwt) or self._admin_client()
        if client is None:
            return self.fallback.set_favorite(
                user_id=user_id,
                track_id=track_id,
                provider=provider,
                track_title=track_title,
                artist_name=artist_name,
                thumbnail_url=thumbnail_url,
                is_favorite=is_favorite,
            )
        try:
            if is_favorite:
                payload = {
                    "user_id": user_id,
                    "track_id": track_id,
                    "provider": provider,
                    "track_title": track_title,
                    "artist_name": artist_name,
                    "thumbnail_url": thumbnail_url or "",
                    "created_at": _now_iso(),
                }
                client.table("favorite_tracks").upsert(payload, on_conflict="user_id,track_id").execute()
            else:
                client.table("favorite_tracks").delete().eq("user_id", user_id).eq("track_id", track_id).execute()
            return {"track_id": track_id, "is_favorite": is_favorite, "updated_at": _now_iso()}
        except Exception as exc:
            logger.error("Supabase set_favorite error: %s", exc)
            return self.fallback.set_favorite(
                user_id=user_id,
                track_id=track_id,
                provider=provider,
                track_title=track_title,
                artist_name=artist_name,
                thumbnail_url=thumbnail_url,
                is_favorite=is_favorite,
            )

    def get_favorites(self, user_id: str, limit: int = 100, user_jwt: Optional[str] = None) -> List[Dict[str, Any]]:
        client = self._client(user_jwt)
        if client is None:
            return self.fallback.get_favorites(user_id, limit)
        try:
            res = client.table("favorite_tracks").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(limit).execute()
            return res.data or []
        except Exception as exc:
            logger.error("Supabase get_favorites error: %s", exc)
            return self.fallback.get_favorites(user_id, limit)

    # --- Policy Versions ---
    def get_policy_version(self, policy_type: str) -> Optional[Dict[str, Any]]:
        client = self._client()
        if client is None:
            return self.fallback.get_policy_version(policy_type)
        try:
            res = client.table("policy_versions").select("*").eq("policy_type", policy_type).order("effective_date", desc=True).limit(1).execute()
            data = res.data or []
            return data[0] if data else None
        except Exception as exc:
            logger.error("Supabase get_policy_version error: %s", exc)
            return self.fallback.get_policy_version(policy_type)

    def list_policies(self) -> List[Dict[str, Any]]:
        client = self._client()
        if client is None:
            return self.fallback.list_policies()
        try:
            res = client.table("policy_versions").select("*").order("policy_type").order("effective_date", desc=True).execute()
            return res.data or []
        except Exception as exc:
            logger.error("Supabase list_policies error: %s", exc)
            return self.fallback.list_policies()

    # --- Privacy Requests, Data Export & Cascade Account Deletion ---
    def create_privacy_request(self, user_id: str, request_type: str, user_jwt: Optional[str] = None) -> Dict[str, Any]:
        client = self._client(user_jwt) or self._admin_client()
        if client is None:
            return self.fallback.create_privacy_request(user_id, request_type)
        try:
            payload = {
                "user_id": user_id,
                "request_type": request_type,
                "status": "pending",
                "requested_at": _now_iso(),
            }
            res = client.table("privacy_requests").insert(payload).execute()
            return (res.data or [payload])[0]
        except Exception as exc:
            logger.error("Supabase create_privacy_request error: %s", exc)
            return self.fallback.create_privacy_request(user_id, request_type)

    def get_privacy_requests(self, user_id: str, user_jwt: Optional[str] = None) -> List[Dict[str, Any]]:
        client = self._client(user_jwt)
        if client is None:
            return self.fallback.get_privacy_requests(user_id)
        try:
            res = client.table("privacy_requests").select("*").eq("user_id", user_id).order("requested_at", desc=True).execute()
            return res.data or []
        except Exception as exc:
            logger.error("Supabase get_privacy_requests error: %s", exc)
            return self.fallback.get_privacy_requests(user_id)

    def export_user_data(self, user_id: str, user_jwt: Optional[str] = None) -> Dict[str, Any]:
        profile = self.get_profile(user_id, user_jwt) or {}
        preferences = self.get_preferences(user_id, user_jwt)
        consents = self.get_consent_history(user_id, limit=500, user_jwt=user_jwt)
        emotions = self.get_emotion_history(user_id, limit=1000, user_jwt=user_jwt)
        listens = self.get_listening_history(user_id, limit=1000, user_jwt=user_jwt)
        favorites = self.get_favorites(user_id, limit=1000, user_jwt=user_jwt)
        privacy_reqs = self.get_privacy_requests(user_id, user_jwt)

        now = _now_iso()
        client = self._client(user_jwt) or self._admin_client()
        if client is not None:
            try:
                client.table("privacy_requests").update({"status": "completed", "completed_at": now}).eq("user_id", user_id).eq("request_type", "data_export").eq("status", "pending").execute()
            except Exception:
                pass

        return {
            "user_id": user_id,
            "exported_at": now,
            "export_metadata": {
                "user_id": user_id,
                "exported_at": now,
                "format_version": "1.0",
                "application": "DeepFace Emotion Music Recommender",
                "disclaimer": "This archive contains personal data held pursuant to applicable privacy laws (India DPDP 2023, US State Privacy Laws).",
            },
            "profile": profile,
            "preferences": preferences,
            "consents": consents,
            "consent_audit_trail": consents,
            "emotion_history": emotions,
            "listening_history": listens,
            "favorites": favorites,
            "favorite_tracks": favorites,
            "privacy_requests": privacy_reqs,
        }

    def delete_user_account(self, user_id: str) -> Dict[str, Any]:
        """Cascade delete all user data across all tables and delete Supabase Auth user via admin client."""
        admin = self.manager.get_admin_client()
        if admin is None:
            return self.fallback.delete_user_account(user_id)

        now = _now_iso()
        try:
            # 1. Delete user data across all tables (or rely on foreign key ON DELETE CASCADE)
            admin.table("user_preferences").delete().eq("user_id", user_id).execute()
            admin.table("emotion_history").delete().eq("user_id", user_id).execute()
            admin.table("listening_history").delete().eq("user_id", user_id).execute()
            admin.table("favorite_tracks").delete().eq("user_id", user_id).execute()
            admin.table("consent_records").delete().eq("user_id", user_id).execute()
            admin.table("privacy_requests").delete().eq("user_id", user_id).execute()
            admin.table("profiles").delete().eq("id", user_id).execute()

            # 2. Delete auth user from Supabase Auth
            try:
                admin.auth.admin.delete_user(user_id)
            except Exception as auth_exc:
                logger.warning("Could not delete user from auth.users: %s", auth_exc)

            self.fallback.delete_user_account(user_id)
            return {"success": True, "user_id": user_id, "deleted_at": now}
        except Exception as exc:
            logger.error("Supabase delete_user_account error: %s", exc)
            return self.fallback.delete_user_account(user_id)

    # --- Security Audit ---
    def log_security_event(
        self,
        *,
        user_id: Optional[str],
        event_type: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        admin = self._admin_client()
        if admin is None:
            self.fallback.log_security_event(
                user_id=user_id,
                event_type=event_type,
                ip_address=ip_address,
                user_agent=user_agent,
                details=details,
            )
            return
        try:
            payload = {
                "user_id": user_id,
                "event_type": event_type,
                "ip_address": ip_address or "",
                "user_agent": user_agent or "",
                "details": details or {},
                "created_at": _now_iso(),
            }
            admin.table("security_audit_logs").insert(payload).execute()
        except Exception as exc:
            logger.warning("Could not write to Supabase security_audit_logs: %s", exc)
            self.fallback.log_security_event(
                user_id=user_id,
                event_type=event_type,
                ip_address=ip_address,
                user_agent=user_agent,
                details=details,
            )


# Default global repository
repository = SupabaseRepository()
