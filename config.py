"""Application configuration for the Emotion-Based Multi-Provider Music Recommender."""
from __future__ import annotations

import os
import secrets
from typing import Dict

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# Security & Session Settings
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
APP_API_KEY = os.getenv("APP_API_KEY", "").strip()
SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", False)
REQUIRE_AUTH_FOR_API = _env_bool("REQUIRE_AUTH_FOR_API", True)
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8080").rstrip("/")

# Supabase PostgreSQL & Auth Credentials
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "").strip()
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

# Privacy & Legal Policy Versions
PRIVACY_POLICY_VERSION = os.getenv("PRIVACY_POLICY_VERSION", "2026.1")
TERMS_VERSION = os.getenv("TERMS_VERSION", "2026.1")
CAMERA_CONSENT_VERSION = os.getenv("CAMERA_CONSENT_VERSION", "2026.1")
DEFAULT_JURISDICTION = os.getenv("DEFAULT_JURISDICTION", "IN").upper()

# Deployment & Licensing Policy
# Supported values: "non_commercial" (default for local/demo) or "commercial" (strict commercial checks)
APP_DEPLOYMENT_MODE = os.getenv("APP_DEPLOYMENT_MODE", "non_commercial").strip().lower()
if APP_DEPLOYMENT_MODE not in {"non_commercial", "commercial"}:
    APP_DEPLOYMENT_MODE = "non_commercial"

# Provider Credentials (only configure providers you actually use; never expose to frontend)
PROVIDER_CONFIG = {
    "jamendo": {
        "enabled": _env_bool("JAMENDO_ENABLED", True),
        "client_id": os.getenv("JAMENDO_CLIENT_ID", "").strip(),
        "base_url": os.getenv("JAMENDO_BASE_URL", "https://api.jamendo.com/v3.0").rstrip("/"),
        # Must only be set True when you hold an active Jamendo Licensing / Pro commercial agreement
        "commercial_agreement_verified": _env_bool("JAMENDO_COMMERCIAL_APPROVED", False),
        "audio_format": os.getenv("JAMENDO_AUDIO_FORMAT", "mp32"),
    },
    "audius": {
        "enabled": _env_bool("AUDIUS_ENABLED", True),
        "api_key": os.getenv("AUDIUS_API_KEY", "").strip(),
        "app_name": os.getenv("AUDIUS_APP_NAME", "EmotionMusicRecommender").strip() or "EmotionMusicRecommender",
        "base_url": os.getenv("AUDIUS_BASE_URL", "https://api.audius.co/v1").rstrip("/"),
        # Must only be set True when your commercial usage complies with Audius OML/creator terms
        "oml_commercial_verified": _env_bool("AUDIUS_OML_COMMERCIAL_APPROVED", False),
    },
    "mubert": {
        "enabled": _env_bool("MUBERT_ENABLED", True),
        "company_id": os.getenv("MUBERT_COMPANY_ID", "").strip(),
        "license_token": os.getenv("MUBERT_LICENSE_TOKEN", "").strip(),
        "base_url": os.getenv("MUBERT_BASE_URL", "https://music-api.mubert.com/api/v3").rstrip("/"),
        "stream_base_url": os.getenv("MUBERT_STREAM_BASE_URL", "https://stream.mubert.com/b2b/v3").rstrip("/"),
        "default_stream_ttl_seconds": _env_int("MUBERT_STREAM_TTL_SECONDS", 900),
    },
}

# HTTP Reliability & Caching Settings
HTTP_SETTINGS = {
    "connect_timeout": _env_float("MUSIC_HTTP_CONNECT_TIMEOUT", 5.0),
    "read_timeout": _env_float("MUSIC_HTTP_READ_TIMEOUT", 10.0),
    "max_retries": _env_int("MUSIC_HTTP_MAX_RETRIES", 2),
    "backoff_base_seconds": _env_float("MUSIC_HTTP_BACKOFF_SECONDS", 0.5),
    "max_retry_after_seconds": _env_float("MUSIC_HTTP_MAX_RETRY_AFTER", 5.0),
}

CACHE_SETTINGS = {
    "metadata_ttl_seconds": _env_int("MUSIC_METADATA_CACHE_TTL", 300),
    "health_ttl_seconds": _env_int("MUSIC_HEALTH_CACHE_TTL", 60),
    "max_entries": _env_int("MUSIC_CACHE_MAX_ENTRIES", 1024),
}

# Configurable Recommendation Engine Weights
DEFAULT_RECOMMENDATION_WEIGHTS: Dict[str, float] = {
    "emotion_mood": _env_float("REC_WEIGHT_EMOTION_MOOD", 0.30),
    "user_mood": _env_float("REC_WEIGHT_USER_MOOD", 0.15),
    "genre": _env_float("REC_WEIGHT_GENRE", 0.15),
    "artist": _env_float("REC_WEIGHT_ARTIST", 0.10),
    "language": _env_float("REC_WEIGHT_LANGUAGE", 0.05),
    "bpm": _env_float("REC_WEIGHT_BPM", 0.10),
    "energy": _env_float("REC_WEIGHT_ENERGY", 0.10),
    "history_affinity": _env_float("REC_WEIGHT_HISTORY_AFFINITY", 0.05),
    "like_boost": _env_float("REC_WEIGHT_LIKE_BOOST", 0.20),
    "dislike_penalty": _env_float("REC_WEIGHT_DISLIKE_PENALTY", 0.80),
    "recent_play_penalty": _env_float("REC_WEIGHT_RECENT_PLAY_PENALTY", 0.25),
}

SUPPORTED_EMOTIONS = [
    "happy",
    "sad",
    "angry",
    "neutral",
    "fear",
    "surprise",
    "disgust",
]

# Auto-capture settings (preserved for existing webcam UX)
AUTO_CAPTURE_SETTINGS = {
    "enabled": False,
    "interval_seconds": _env_int("AUTO_CAPTURE_INTERVAL_SECONDS", 30),
    "songs_before_recheck": _env_int("SONGS_BEFORE_RECHECK", 3),
    "auto_play_random_song": True,
}

# Storage & File Paths
DATABASE_PATH = os.getenv("DATABASE_PATH", os.path.join("data", "music_recommender.db"))
CAPTURED_IMAGE_PATH = os.getenv("CAPTURED_IMAGE_PATH", "/tmp/saved_img.jpg")
PROCESSED_IMAGE_PATH = os.getenv("PROCESSED_IMAGE_PATH", "/tmp/saved_img-final.jpg")
