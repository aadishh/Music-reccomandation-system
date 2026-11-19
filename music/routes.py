"""Flask Blueprint for multi-provider music API endpoints (/api/music/*)."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from flask import Blueprint, current_app, g, jsonify, request

from music.auth import require_api_auth
from music.exceptions import (
    LicensingViolationError,
    MusicProviderError,
    StreamExpiredError,
    TrackNotFoundError,
    UnsupportedOperationError,
)
from music.models import (
    RecommendationMode,
    RecommendationRequest,
    parse_internal_track_id,
)

logger = logging.getLogger(__name__)

music_bp = Blueprint("music_api", __name__, url_prefix="/api/music")


def _parse_csv_param(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _safe_int(value: Optional[str], default: int, minimum: int = 1, maximum: int = 50) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _safe_float(value: Optional[str], default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _get_services():
    registry = current_app.extensions["music_registry"]
    engine = current_app.extensions["recommendation_engine"]
    storage = current_app.extensions["music_storage"]
    return registry, engine, storage


@music_bp.route("/providers", methods=["GET"])
@require_api_auth
def list_providers():
    """Return provider capabilities, health status, and licensing mode (never credentials)."""
    registry, _, _ = _get_services()
    force_refresh = request.args.get("refresh", "false").strip().lower() in {"1", "true", "yes"}
    statuses = registry.get_all_provider_statuses(force_refresh=force_refresh)
    return jsonify(
        {
            "deployment_mode": registry.licensing_validator.deployment_mode.value,
            "providers": [status.to_dict() for status in statuses],
        }
    )


@music_bp.route("/search", methods=["GET"])
@require_api_auth
def search_music():
    """Search normalized tracks across one or more configured providers."""
    registry, _, _ = _get_services()
    query = request.args.get("q", request.args.get("query", "")).strip()
    providers = _parse_csv_param(request.args.get("provider") or request.args.get("providers"))
    genre = request.args.get("genre", "").strip() or None
    mood = request.args.get("mood", "").strip() or None
    language = request.args.get("language", "").strip() or None
    limit = _safe_int(request.args.get("limit"), default=20, minimum=1, maximum=50)
    offset = _safe_int(request.args.get("offset"), default=0, minimum=0, maximum=200)

    tracks, provider_errors = registry.search_tracks(
        query=query,
        providers=providers or None,
        genre=genre,
        mood=mood,
        language=language,
        limit=limit,
        offset=offset,
        only_playable=True,
    )
    return jsonify(
        {
            "query": query,
            "count": len(tracks),
            "tracks": [t.to_dict() for t in tracks],
            "provider_errors": provider_errors,
            "deployment_mode": registry.licensing_validator.deployment_mode.value,
        }
    )


@music_bp.route("/track/<string:track_id>", methods=["GET"])
@require_api_auth
def get_track(track_id: str):
    """Retrieve normalized UnifiedTrack details by internal track ID (<provider>:<id>)."""
    registry, _, _ = _get_services()
    try:
        track = registry.get_track_details(track_id)
        allowed, reason = registry.licensing_validator.is_playable(track)
        data = track.to_dict()
        data["playable_under_current_policy"] = allowed
        data["policy_reason"] = reason
        return jsonify(data)
    except ValueError as exc:
        return jsonify({"error": str(exc), "code": "invalid_track_id"}), 400
    except TrackNotFoundError as exc:
        return jsonify({"error": exc.message, "code": exc.code, "provider": exc.provider}), 404
    except UnsupportedOperationError as exc:
        return jsonify({"error": exc.message, "code": exc.code, "provider": exc.provider}), 501
    except MusicProviderError as exc:
        return (
            jsonify({"error": exc.message, "code": exc.code, "provider": exc.provider}),
            exc.status_code or 502,
        )


@music_bp.route("/playback/<string:track_id>", methods=["GET"])
@require_api_auth
def get_playback(track_id: str):
    """Resolve an authorized playback stream URL after enforcing licensing validation."""
    registry, _, storage = _get_services()
    refresh = request.args.get("refresh", "true").strip().lower() in {"1", "true", "yes"}
    record_play = request.args.get("record_history", "true").strip().lower() in {"1", "true", "yes"}
    emotion = request.args.get("emotion", "").strip() or None
    mode = request.args.get("mode", "").strip() or None

    try:
        playback = registry.get_playback_info(track_id, refresh=refresh)

        if record_play and storage is not None:
            track_snapshot = None
            title = request.args.get("title", "")
            artist = request.args.get("artist", "")
            genre = request.args.get("genre")
            try:
                track_obj = registry.get_track_details(track_id)
                track_snapshot = track_obj.to_dict()
                title = track_obj.title
                artist = track_obj.artist
                genre = track_obj.genre
            except (UnsupportedOperationError, MusicProviderError):
                pass

            storage.record_play(
                user_id=g.user_id,
                track_id=playback.internal_id,
                provider=playback.provider,
                title=title,
                artist=artist,
                genre=genre,
                emotion=emotion,
                recommendation_mode=mode,
                track_data=track_snapshot,
            )

        return jsonify(playback.to_dict())
    except ValueError as exc:
        return jsonify({"error": str(exc), "code": "invalid_track_id"}), 400
    except LicensingViolationError as exc:
        return (
            jsonify(
                {
                    "error": exc.message,
                    "code": exc.code,
                    "provider": exc.provider,
                    "reason": exc.reason,
                }
            ),
            403,
        )
    except StreamExpiredError as exc:
        return jsonify({"error": exc.message, "code": exc.code, "provider": exc.provider}), 410
    except TrackNotFoundError as exc:
        return jsonify({"error": exc.message, "code": exc.code, "provider": exc.provider}), 404
    except UnsupportedOperationError as exc:
        return jsonify({"error": exc.message, "code": exc.code, "provider": exc.provider}), 501
    except MusicProviderError as exc:
        return (
            jsonify({"error": exc.message, "code": exc.code, "provider": exc.provider}),
            exc.status_code or 502,
        )


@music_bp.route("/recommendations", methods=["GET"])
@require_api_auth
def get_recommendations():
    """Return weighted emotion-aware music recommendations across configured providers."""
    _, engine, _ = _get_services()

    emotion = request.args.get("emotion", "neutral").strip().lower() or "neutral"
    confidence = _safe_float(request.args.get("confidence"), default=0.75)
    mood = request.args.get("mood", "").strip() or None
    mode = request.args.get("mode", RecommendationMode.MOOD_MATCHING.value).strip().lower()
    if mode not in {RecommendationMode.MOOD_MATCHING.value, RecommendationMode.MOOD_SHIFTING.value}:
        return (
            jsonify(
                {
                    "error": "Invalid recommendation mode. Expected 'mood_matching' or 'mood_shifting'.",
                    "code": "invalid_mode",
                }
            ),
            400,
        )

    preferred_genres = _parse_csv_param(request.args.get("genres") or request.args.get("genre"))
    preferred_artists = _parse_csv_param(request.args.get("artists") or request.args.get("artist"))
    language = request.args.get("language", "").strip() or None
    providers = _parse_csv_param(request.args.get("providers") or request.args.get("provider"))
    limit = _safe_int(request.args.get("limit"), default=15, minimum=1, maximum=50)

    rec_request = RecommendationRequest(
        detected_emotion=emotion,
        emotion_confidence=confidence,
        user_selected_mood=mood,
        preferred_genres=preferred_genres,
        preferred_artists=preferred_artists,
        language=language,
        mode=mode,
        limit=limit,
        providers=providers or None,
        user_id=g.user_id,
    )
    result = engine.recommend(rec_request)
    return jsonify(result)


@music_bp.route("/feedback", methods=["POST"])
@require_api_auth
def submit_feedback():
    """Record user like/dislike/skip/neutral feedback for a track."""
    _, _, storage = _get_services()
    data = request.get_json(silent=True) or {}
    track_id = str(data.get("track_id") or "").strip()
    feedback = str(data.get("feedback") or "").strip().lower()

    if not track_id:
        return jsonify({"error": "track_id is required.", "code": "missing_track_id"}), 400
    try:
        parse_internal_track_id(track_id)
    except ValueError as exc:
        return jsonify({"error": str(exc), "code": "invalid_track_id"}), 400

    try:
        record = storage.record_feedback(
            user_id=g.user_id,
            track_id=track_id,
            feedback=feedback,
            artist=data.get("artist"),
            genre=data.get("genre"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc), "code": "invalid_feedback"}), 400

    return jsonify({"success": True, **record})


@music_bp.route("/history", methods=["GET"])
@require_api_auth
def get_history():
    """Return recently played tracks for the authenticated user."""
    _, _, storage = _get_services()
    limit = _safe_int(request.args.get("limit"), default=30, minimum=1, maximum=200)
    items = storage.get_history(user_id=g.user_id, limit=limit)
    return jsonify({"count": len(items), "history": items})


@music_bp.route("/favorites", methods=["GET", "POST"])
@require_api_auth
def manage_favorites():
    """List or add/remove favorite tracks for the authenticated user."""
    registry, _, storage = _get_services()

    if request.method == "GET":
        limit = _safe_int(request.args.get("limit"), default=100, minimum=1, maximum=500)
        items = storage.get_favorites(user_id=g.user_id, limit=limit)
        return jsonify({"count": len(items), "favorites": items})

    data = request.get_json(silent=True) or {}
    track_id = str(data.get("track_id") or "").strip()
    if not track_id:
        return jsonify({"error": "track_id is required.", "code": "missing_track_id"}), 400

    try:
        provider_name, _ = parse_internal_track_id(track_id)
    except ValueError as exc:
        return jsonify({"error": str(exc), "code": "invalid_track_id"}), 400

    action = str(data.get("action") or "add").strip().lower()
    is_favorite = action != "remove"
    if "is_favorite" in data:
        is_favorite = bool(data["is_favorite"])

    track_data: Dict[str, Any] = data.get("track") if isinstance(data.get("track"), dict) else {}
    if is_favorite and not track_data:
        try:
            track_data = registry.get_track_details(track_id).to_dict()
        except (UnsupportedOperationError, MusicProviderError):
            track_data = {
                "internal_id": track_id,
                "provider": provider_name,
                "title": data.get("title", "Unknown Track"),
                "artist": data.get("artist", "Unknown Artist"),
            }

    result = storage.set_favorite(
        user_id=g.user_id,
        track_id=track_id,
        provider=provider_name,
        track_data=track_data,
        is_favorite=is_favorite,
    )
    return jsonify({"success": True, **result})


@music_bp.route("/preferences", methods=["GET", "POST"])
@require_api_auth
def manage_preferences():
    """Read or persist user genre/artist/language/mode preferences."""
    _, _, storage = _get_services()
    if request.method == "GET":
        return jsonify(storage.get_preferences(g.user_id))

    data = request.get_json(silent=True) or {}
    saved = storage.save_preferences(
        user_id=g.user_id,
        preferred_genres=data.get("preferred_genres"),
        preferred_artists=data.get("preferred_artists"),
        language=data.get("language"),
        recommendation_mode=data.get("recommendation_mode"),
    )
    return jsonify({"success": True, **saved})
