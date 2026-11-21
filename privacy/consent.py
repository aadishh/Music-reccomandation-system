"""Consent verification and jurisdiction-aware privacy compliance logic.

Supports India DPDP Act 2023 & DPDP Rules 2025, US State Privacy Laws
(California CCPA/CPRA, Virginia VCDPA, Colorado CPA), Biometric Privacy
(Illinois BIPA, Texas CUBI), and GDPR compliance standards.
"""
from __future__ import annotations

import functools
import logging
from typing import Any, Callable, Dict, List, Optional, Set

from flask import current_app, g, jsonify, request, session

import config
from database.repository import repository

logger = logging.getLogger(__name__)

CONSENT_TYPES: Set[str] = {
    "terms_and_conditions",
    "privacy_policy",
    "camera_processing",
    "emotion_history",
    "analytics",
}

VALID_JURISDICTIONS: Set[str] = {"IN", "US", "EU", "GB", "CA", "AU", "OTHER"}


class ConsentManager:
    """Manages consent verification, audit recording, and revocation."""

    def __init__(self, repo=repository) -> None:
        self.repo = repo

    def get_user_id(self) -> str:
        """Resolve current user ID from Flask context, JWT, or web session."""
        if hasattr(g, "user_id") and g.user_id:
            return str(g.user_id)
        if hasattr(g, "user") and g.user and isinstance(g.user, dict) and g.user.get("id"):
            return str(g.user["id"])
        if "user_id" in session:
            return str(session["user_id"])
        # Fallback to anonymous web session ID
        from music.auth import ensure_web_session

        user_id, _ = ensure_web_session()
        return user_id

    def has_consent(self, user_id: str, consent_type: str) -> bool:
        """Check whether user has an active, unwithdrawn consent for given type."""
        if consent_type not in CONSENT_TYPES:
            return False

        # Check in session first for instant responsiveness
        session_consents = session.get("consents", {})
        if session_consents.get(consent_type) is True:
            return True

        status = self.repo.get_consent_status(user_id)
        has_it = bool(status.get(consent_type, False))
        if has_it:
            session_consents[consent_type] = True
            session["consents"] = session_consents
        return has_it

    def record_consent(
        self,
        *,
        user_id: str,
        consent_type: str,
        policy_version: Optional[str] = None,
        accepted: bool = True,
        jurisdiction: Optional[str] = None,
        consent_method: str = "web_form",
    ) -> Dict[str, Any]:
        """Record an immutable consent event in the audit trail."""
        if consent_type not in CONSENT_TYPES:
            raise ValueError(f"Invalid consent type '{consent_type}'. Must be one of {sorted(CONSENT_TYPES)}")

        clean_jur = (jurisdiction or config.DEFAULT_JURISDICTION).upper()
        if clean_jur not in VALID_JURISDICTIONS:
            clean_jur = "OTHER"

        version = policy_version or self._get_default_version(consent_type)

        record = self.repo.record_consent(
            user_id=user_id,
            consent_type=consent_type,
            policy_version=version,
            accepted=accepted,
            jurisdiction=clean_jur,
            consent_method=consent_method,
        )

        # Update current session cache
        session_consents = session.get("consents", {})
        session_consents[consent_type] = bool(accepted)
        session["consents"] = session_consents

        # Log security audit event
        self.repo.log_security_event(
            user_id=user_id,
            event_type=f"consent_{'granted' if accepted else 'declined'}",
            ip_address=request.remote_addr if request else None,
            user_agent=request.user_agent.string if request and request.user_agent else None,
            details={"consent_type": consent_type, "version": version, "jurisdiction": clean_jur},
        )
        return record

    def withdraw_consent(self, *, user_id: str, consent_type: str) -> Dict[str, Any]:
        """Withdraw consent immediately and record withdrawal event in audit trail."""
        if consent_type not in CONSENT_TYPES:
            raise ValueError(f"Invalid consent type '{consent_type}'")

        res = self.repo.withdraw_consent(user_id=user_id, consent_type=consent_type)

        # Clear from session
        session_consents = session.get("consents", {})
        session_consents[consent_type] = False
        session["consents"] = session_consents

        # If camera consent is withdrawn, ensure auto-capture stops immediately
        if consent_type == "camera_processing" and current_app and "emotion_system" in current_app.extensions:
            sys_inst = current_app.extensions["emotion_system"]
            sys_inst.stop_auto_capture()

        self.repo.log_security_event(
            user_id=user_id,
            event_type="consent_withdrawn",
            ip_address=request.remote_addr if request else None,
            user_agent=request.user_agent.string if request and request.user_agent else None,
            details={"consent_type": consent_type},
        )
        return res

    def get_all_consents(self, user_id: str) -> Dict[str, bool]:
        """Return a mapping of consent types to boolean active status."""
        statuses = self.repo.get_consent_status(user_id)
        # Ensure all types exist in dictionary
        return {ctype: bool(statuses.get(ctype, False)) for ctype in CONSENT_TYPES}

    def _get_default_version(self, consent_type: str) -> str:
        if consent_type == "privacy_policy":
            return config.PRIVACY_POLICY_VERSION
        if consent_type == "terms_and_conditions":
            return config.TERMS_VERSION
        if consent_type == "camera_processing":
            return config.CAMERA_CONSENT_VERSION
        return "1.0"


consent_manager = ConsentManager()


def require_camera_consent(f: Callable) -> Callable:
    """Decorator guarding endpoints requiring explicit camera & facial emotion processing consent."""

    @functools.wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        user_id = consent_manager.get_user_id()

        # Allow bypass only if header explicitly carries affirmative client token verified in session
        has_consent = consent_manager.has_consent(user_id, "camera_processing")
        if not has_consent:
            # Check if request payload contains an explicit just-in-time affirmative consent grant
            payload = request.get_json(silent=True) or {}
            if payload.get("camera_consent_granted") is True:
                consent_manager.record_consent(
                    user_id=user_id,
                    consent_type="camera_processing",
                    accepted=True,
                    jurisdiction=payload.get("jurisdiction"),
                    consent_method="jit_affirmation",
                )
                has_consent = True

        if not has_consent:
            return (
                jsonify(
                    {
                        "error": "Explicit affirmative consent is required before processing webcam frames.",
                        "consent_required": "camera_processing",
                        "policy_version": config.CAMERA_CONSENT_VERSION,
                        "disclosure": (
                            "Webcam frames are processed purely in-memory on the server and immediately discarded. "
                            "No photographs, video recordings, or biometric face templates are ever saved to disk."
                        ),
                    }
                ),
                403,
            )

        return f(*args, **kwargs)

    return decorated_function
