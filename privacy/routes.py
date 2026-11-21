"""Flask routes for Privacy Policy, Terms, Consent Management, and Data Rights."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import config
from database.repository import repository
from music.auth import ensure_web_session
from privacy.consent import CONSENT_TYPES, consent_manager

logger = logging.getLogger(__name__)

privacy_bp = Blueprint("privacy", __name__, url_prefix="/privacy")


def _resolve_user_id() -> str:
    """Resolve user ID from g, session, or anonymous web token."""
    if hasattr(g, "user_id") and g.user_id:
        return str(g.user_id)
    if "user_id" in session:
        return str(session["user_id"])
    user_id, _ = ensure_web_session()
    return user_id


@privacy_bp.route("/policy", methods=["GET"])
def privacy_policy():
    """Render comprehensive Privacy Policy page."""
    user_id = _resolve_user_id()
    consents = consent_manager.get_all_consents(user_id)
    return render_template(
        "privacy/policy.html",
        policy_version=config.PRIVACY_POLICY_VERSION,
        consents=consents,
    )


@privacy_bp.route("/terms", methods=["GET"])
def terms_and_conditions():
    """Render comprehensive Terms and Conditions page."""
    user_id = _resolve_user_id()
    consents = consent_manager.get_all_consents(user_id)
    return render_template(
        "privacy/terms.html",
        terms_version=config.TERMS_VERSION,
        consents=consents,
    )


@privacy_bp.route("/camera-consent", methods=["GET"])
def camera_consent():
    """Render standalone camera permission and emotion-processing disclosure."""
    user_id = _resolve_user_id()
    has_consent = consent_manager.has_consent(user_id, "camera_processing")
    return render_template(
        "privacy/camera_consent.html",
        camera_consent_version=config.CAMERA_CONSENT_VERSION,
        has_consent=has_consent,
    )


@privacy_bp.route("/status", methods=["GET"])
def consent_status():
    """Get current active consents and history summary for user."""
    user_id = _resolve_user_id()
    statuses = consent_manager.get_all_consents(user_id)
    history = repository.get_consent_history(user_id)
    return jsonify(
        {
            "user_id": user_id,
            "consents": statuses,
            "history_count": len(history),
            "policy_version": config.PRIVACY_POLICY_VERSION,
            "camera_consent_version": config.CAMERA_CONSENT_VERSION,
        }
    )


@privacy_bp.route("/consent", methods=["POST"])
def record_consent_endpoint():
    """Record affirmative consent for a specific category."""
    try:
        user_id = _resolve_user_id()
        data = request.get_json(silent=True) or request.form.to_dict() or {}

        consent_type = str(data.get("consent_type", "")).strip().lower()
        if consent_type not in CONSENT_TYPES:
            return jsonify({"error": f"Invalid consent_type. Must be one of: {sorted(CONSENT_TYPES)}"}), 400

        accepted = bool(data.get("accepted", True))
        jurisdiction = str(data.get("jurisdiction") or config.DEFAULT_JURISDICTION).strip().upper()
        consent_method = str(data.get("consent_method", "web_interface")).strip()

        rec = consent_manager.record_consent(
            user_id=user_id,
            consent_type=consent_type,
            accepted=accepted,
            jurisdiction=jurisdiction,
            consent_method=consent_method,
        )

        return jsonify(
            {
                "success": True,
                "message": f"Consent for '{consent_type}' recorded successfully.",
                "record": rec,
                "current_consents": consent_manager.get_all_consents(user_id),
            }
        )
    except Exception as exc:
        logger.error("Failed to record consent: %s", exc)
        return jsonify({"error": str(exc)}), 500


@privacy_bp.route("/withdraw", methods=["POST"])
def withdraw_consent_endpoint():
    """Withdraw consent for a category immediately."""
    try:
        user_id = _resolve_user_id()
        data = request.get_json(silent=True) or request.form.to_dict() or {}

        consent_type = str(data.get("consent_type", "")).strip().lower()
        if consent_type not in CONSENT_TYPES:
            return jsonify({"error": f"Invalid consent_type. Must be one of: {sorted(CONSENT_TYPES)}"}), 400

        res = consent_manager.withdraw_consent(user_id=user_id, consent_type=consent_type)

        return jsonify(
            {
                "success": True,
                "message": f"Consent for '{consent_type}' has been withdrawn immediately.",
                "withdrawal": res,
                "current_consents": consent_manager.get_all_consents(user_id),
            }
        )
    except Exception as exc:
        logger.error("Failed to withdraw consent: %s", exc)
        return jsonify({"error": str(exc)}), 500


@privacy_bp.route("/export", methods=["GET"])
def export_user_data_endpoint():
    """Download personal data export as structured JSON (GDPR / CCPA / DPDP Data Portability)."""
    try:
        user_id = _resolve_user_id()
        export_bundle = repository.export_user_data(user_id)

        # Log security audit event for data portability request
        repository.log_security_event(
            user_id=user_id,
            event_type="data_export_downloaded",
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string if request.user_agent else None,
        )

        json_data = json.dumps(export_bundle, indent=2, default=str)
        filename = f"music_recommender_data_{user_id[:8]}_{export_bundle.get('exported_at', '')[:10]}.json"

        return Response(
            json_data,
            mimetype="application/json",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as exc:
        logger.error("Data export failed: %s", exc)
        return jsonify({"error": str(exc)}), 500


@privacy_bp.route("/delete-data", methods=["POST"])
def delete_specific_data():
    """Request selective deletion of personal data categories (e.g., emotion_history)."""
    try:
        user_id = _resolve_user_id()
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        category = str(data.get("category", "")).strip().lower()

        if category == "emotion_history":
            deleted_count = repository.clear_emotion_history(user_id)
            repository.create_privacy_request(
                user_id=user_id,
                request_type="delete_emotion_history",
                status="completed",
                details={"deleted_count": deleted_count},
            )
            return jsonify(
                {"success": True, "message": f"Deleted {deleted_count} emotion history records."}
            )

        if category == "listening_history":
            deleted_count = repository.clear_listening_history(user_id)
            repository.create_privacy_request(
                user_id=user_id,
                request_type="delete_listening_history",
                status="completed",
                details={"deleted_count": deleted_count},
            )
            return jsonify(
                {"success": True, "message": f"Deleted {deleted_count} listening history records."}
            )

        return jsonify({"error": "Unsupported deletion category"}), 400
    except Exception as exc:
        logger.error("Delete data failed: %s", exc)
        return jsonify({"error": str(exc)}), 500
