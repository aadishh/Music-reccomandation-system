"""Lightweight SQLite persistence for listening history, feedback, favorites, and preferences."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set


class MusicStorage:
    """Thread-safe SQLite store scoped per user_id."""

    def __init__(self, db_path: str = "data/music_recommender.db") -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        if db_path != ":memory:":
            parent = os.path.dirname(os.path.abspath(db_path))
            if parent:
                os.makedirs(parent, exist_ok=True)
        # Keep persistent connection for :memory: databases
        self._memory_conn: Optional[sqlite3.Connection] = None
        if db_path == ":memory:":
            self._memory_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._memory_conn.row_factory = sqlite3.Row
        self._initialize_schema()

    def _connect(self) -> sqlite3.Connection:
        if self._memory_conn is not None:
            return self._memory_conn
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _close_if_not_memory(self, conn: sqlite3.Connection) -> None:
        if self._memory_conn is None:
            conn.close()

    def _initialize_schema(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS listening_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        track_id TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        title TEXT,
                        artist TEXT,
                        genre TEXT,
                        emotion TEXT,
                        recommendation_mode TEXT,
                        track_json TEXT,
                        played_at TEXT NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_history_user_time
                        ON listening_history (user_id, played_at DESC);

                    CREATE TABLE IF NOT EXISTS track_feedback (
                        user_id TEXT NOT NULL,
                        track_id TEXT NOT NULL,
                        feedback TEXT NOT NULL,
                        artist TEXT,
                        genre TEXT,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (user_id, track_id)
                    );

                    CREATE TABLE IF NOT EXISTS favorites (
                        user_id TEXT NOT NULL,
                        track_id TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        track_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        PRIMARY KEY (user_id, track_id)
                    );

                    CREATE TABLE IF NOT EXISTS user_preferences (
                        user_id TEXT PRIMARY KEY,
                        preferred_genres TEXT DEFAULT '[]',
                        preferred_artists TEXT DEFAULT '[]',
                        language TEXT DEFAULT '',
                        recommendation_mode TEXT DEFAULT 'mood_matching',
                        updated_at TEXT NOT NULL
                    );
                    """
                )
                conn.commit()
            finally:
                self._close_if_not_memory(conn)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    # --- Listening History ---

    def record_play(
        self,
        *,
        user_id: str,
        track_id: str,
        provider: str,
        title: str = "",
        artist: str = "",
        genre: Optional[str] = None,
        emotion: Optional[str] = None,
        recommendation_mode: Optional[str] = None,
        track_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        played_at = self._now_iso()
        serialized = json.dumps(track_data) if track_data else None
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO listening_history
                        (user_id, track_id, provider, title, artist, genre, emotion, recommendation_mode, track_json, played_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        track_id,
                        provider,
                        title,
                        artist,
                        genre or "",
                        emotion or "",
                        recommendation_mode or "",
                        serialized,
                        played_at,
                    ),
                )
                conn.commit()
            finally:
                self._close_if_not_memory(conn)
        return {
            "track_id": track_id,
            "provider": provider,
            "played_at": played_at,
        }

    def get_history(self, user_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT track_id, provider, title, artist, genre, emotion, recommendation_mode, track_json, played_at
                    FROM listening_history
                    WHERE user_id = ?
                    ORDER BY played_at DESC, id DESC
                    LIMIT ?
                    """,
                    (user_id, limit),
                ).fetchall()
            finally:
                self._close_if_not_memory(conn)

        history: List[Dict[str, Any]] = []
        for row in rows:
            track_snapshot = None
            if row["track_json"]:
                try:
                    track_snapshot = json.loads(row["track_json"])
                except ValueError:
                    track_snapshot = None
            history.append(
                {
                    "track_id": row["track_id"],
                    "provider": row["provider"],
                    "title": row["title"],
                    "artist": row["artist"],
                    "genre": row["genre"] or None,
                    "emotion": row["emotion"] or None,
                    "recommendation_mode": row["recommendation_mode"] or None,
                    "played_at": row["played_at"],
                    "track": track_snapshot,
                }
            )
        return history

    def get_recently_played_ids(self, user_id: str, limit: int = 25) -> List[str]:
        rows = self.get_history(user_id, limit=limit)
        return [r["track_id"] for r in rows]

    # --- Feedback (Like / Dislike / Skip) ---

    def record_feedback(
        self,
        *,
        user_id: str,
        track_id: str,
        feedback: str,
        artist: Optional[str] = None,
        genre: Optional[str] = None,
    ) -> Dict[str, Any]:
        feedback_norm = feedback.strip().lower()
        if feedback_norm not in {"like", "dislike", "neutral", "skip"}:
            raise ValueError("Feedback must be one of: 'like', 'dislike', 'neutral', 'skip'.")

        updated_at = self._now_iso()
        with self._lock:
            conn = self._connect()
            try:
                if feedback_norm == "neutral":
                    conn.execute(
                        "DELETE FROM track_feedback WHERE user_id = ? AND track_id = ?",
                        (user_id, track_id),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO track_feedback (user_id, track_id, feedback, artist, genre, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(user_id, track_id) DO UPDATE SET
                            feedback = excluded.feedback,
                            artist = COALESCE(NULLIF(excluded.artist, ''), track_feedback.artist),
                            genre = COALESCE(NULLIF(excluded.genre, ''), track_feedback.genre),
                            updated_at = excluded.updated_at
                        """,
                        (user_id, track_id, feedback_norm, artist or "", genre or "", updated_at),
                    )
                conn.commit()
            finally:
                self._close_if_not_memory(conn)

        return {
            "track_id": track_id,
            "feedback": feedback_norm,
            "updated_at": updated_at,
        }

    def get_feedback_summary(self, user_id: str) -> Dict[str, Any]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT track_id, feedback, artist, genre FROM track_feedback WHERE user_id = ?",
                    (user_id,),
                ).fetchall()
            finally:
                self._close_if_not_memory(conn)

        liked_ids: Set[str] = set()
        disliked_ids: Set[str] = set()
        liked_artists: Set[str] = set()
        liked_genres: Set[str] = set()
        disliked_artists: Set[str] = set()

        for row in rows:
            fb = row["feedback"]
            if fb == "like":
                liked_ids.add(row["track_id"])
                if row["artist"]:
                    liked_artists.add(row["artist"].lower())
                if row["genre"]:
                    liked_genres.add(row["genre"].lower())
            elif fb == "dislike":
                disliked_ids.add(row["track_id"])
                if row["artist"]:
                    disliked_artists.add(row["artist"].lower())

        return {
            "liked_ids": liked_ids,
            "disliked_ids": disliked_ids,
            "liked_artists": liked_artists,
            "liked_genres": liked_genres,
            "disliked_artists": disliked_artists,
        }

    # --- Favorites ---

    def set_favorite(
        self,
        *,
        user_id: str,
        track_id: str,
        provider: str,
        track_data: Dict[str, Any],
        is_favorite: bool = True,
    ) -> Dict[str, Any]:
        now = self._now_iso()
        with self._lock:
            conn = self._connect()
            try:
                if is_favorite:
                    conn.execute(
                        """
                        INSERT INTO favorites (user_id, track_id, provider, track_json, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(user_id, track_id) DO UPDATE SET
                            track_json = excluded.track_json,
                            created_at = excluded.created_at
                        """,
                        (user_id, track_id, provider, json.dumps(track_data), now),
                    )
                else:
                    conn.execute(
                        "DELETE FROM favorites WHERE user_id = ? AND track_id = ?",
                        (user_id, track_id),
                    )
                conn.commit()
            finally:
                self._close_if_not_memory(conn)
        return {
            "track_id": track_id,
            "is_favorite": is_favorite,
            "updated_at": now,
        }

    def get_favorites(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT track_id, provider, track_json, created_at
                    FROM favorites
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (user_id, limit),
                ).fetchall()
            finally:
                self._close_if_not_memory(conn)

        favorites: List[Dict[str, Any]] = []
        for row in rows:
            try:
                track_obj = json.loads(row["track_json"])
            except ValueError:
                track_obj = {"internal_id": row["track_id"], "provider": row["provider"]}
            favorites.append(
                {
                    "track_id": row["track_id"],
                    "provider": row["provider"],
                    "created_at": row["created_at"],
                    "track": track_obj,
                }
            )
        return favorites

    # --- User Preferences ---

    def get_preferences(self, user_id: str) -> Dict[str, Any]:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    """
                    SELECT preferred_genres, preferred_artists, language, recommendation_mode, updated_at
                    FROM user_preferences
                    WHERE user_id = ?
                    """,
                    (user_id,),
                ).fetchone()
            finally:
                self._close_if_not_memory(conn)

        if not row:
            return {
                "preferred_genres": [],
                "preferred_artists": [],
                "language": "",
                "recommendation_mode": "mood_matching",
            }
        return {
            "preferred_genres": json.loads(row["preferred_genres"] or "[]"),
            "preferred_artists": json.loads(row["preferred_artists"] or "[]"),
            "language": row["language"] or "",
            "recommendation_mode": row["recommendation_mode"] or "mood_matching",
            "updated_at": row["updated_at"],
        }

    def save_preferences(
        self,
        *,
        user_id: str,
        preferred_genres: Optional[List[str]] = None,
        preferred_artists: Optional[List[str]] = None,
        language: Optional[str] = None,
        recommendation_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        current = self.get_preferences(user_id)
        genres = (
            [g.strip().lower() for g in preferred_genres if g and g.strip()]
            if preferred_genres is not None
            else current["preferred_genres"]
        )
        artists = (
            [a.strip() for a in preferred_artists if a and a.strip()]
            if preferred_artists is not None
            else current["preferred_artists"]
        )
        lang = language.strip().lower() if language is not None else current["language"]
        mode = (
            recommendation_mode.strip().lower()
            if recommendation_mode in {"mood_matching", "mood_shifting"}
            else current["recommendation_mode"]
        )
        updated_at = self._now_iso()

        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO user_preferences
                        (user_id, preferred_genres, preferred_artists, language, recommendation_mode, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        preferred_genres = excluded.preferred_genres,
                        preferred_artists = excluded.preferred_artists,
                        language = excluded.language,
                        recommendation_mode = excluded.recommendation_mode,
                        updated_at = excluded.updated_at
                    """,
                    (user_id, json.dumps(genres), json.dumps(artists), lang, mode, updated_at),
                )
                conn.commit()
            finally:
                self._close_if_not_memory(conn)

        return {
            "preferred_genres": genres,
            "preferred_artists": artists,
            "language": lang,
            "recommendation_mode": mode,
            "updated_at": updated_at,
        }
