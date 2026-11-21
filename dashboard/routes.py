"""Dashboard views for User Profile and Privacy Controls."""
from __future__ import annotations

import logging
from flask import Blueprint, g, render_template, session

import config
from auth.middleware import optional_auth, require_auth
from database.repository import repository
from music.auth import ensure_web_session
from privacy.consent import consent_manager

logger = logging.getLogger(__name__)

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


def _get_active_user_id() -> str:
    if hasattr(g, "user_id") and g.user_id:
        return str(g.user_id)
    if "user_id" in session:
        return str(session["user_id"])
    user_id, _ = ensure_web_session()
    return user_id


@dashboard_bp.route("", methods=["GET"])
@dashboard_bp.route("/", methods=["GET"])
@require_auth
def user_dashboard():
    """Render the main User Dashboard: profile, music history, favorites, emotion timeline."""
    user_id = g.user_id
    profile = repository.get_profile(user_id) or {"id": user_id, "email": g.user.get("email")}
    preferences = repository.get_user_preferences(user_id)
    consents = consent_manager.get_all_consents(user_id)

    listening_history = repository.get_listening_history(user_id, limit=25)
    favorites = repository.get_favorites(user_id, limit=50)

    # Emotion history is strictly gated on active emotion_history consent
    emotion_opted_in = consents.get("emotion_history", False)
    emotion_history = repository.get_emotion_history(user_id, limit=30) if emotion_opted_in else []

    return render_template(
        "dashboard/user_dashboard.html",
        user=g.user,
        profile=profile,
        preferences=preferences,
        consents=consents,
        listening_history=listening_history,
        favorites=favorites,
        emotion_opted_in=emotion_opted_in,
        emotion_history=emotion_history,
        supported_emotions=config.SUPPORTED_EMOTIONS,
    )


@dashboard_bp.route("/privacy", methods=["GET"])
@optional_auth
def privacy_dashboard():
    """Render the User Privacy Dashboard: consent toggles, audit trail, export, deletion."""
    user_id = _get_active_user_id()
    is_authenticated = bool(hasattr(g, "user_id") and g.user_id)

    consents = consent_manager.get_all_consents(user_id)
    history = repository.get_consent_history(user_id, limit=100)
    requests = repository.get_privacy_requests(user_id) if is_authenticated else []

    return render_template(
        "dashboard/privacy_dashboard.html",
        user_id=user_id,
        is_authenticated=is_authenticated,
        consents=consents,
        consent_history=history,
        privacy_requests=requests,
        policy_version=config.PRIVACY_POLICY_VERSION,
        terms_version=config.TERMS_VERSION,
        camera_version=config.CAMERA_CONSENT_VERSION,
    )
