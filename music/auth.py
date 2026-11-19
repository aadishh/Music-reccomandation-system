"""Secure session and API-key authentication & CSRF protection for /api/music/* endpoints."""
from __future__ import annotations

import hmac
import re
import secrets
import uuid
from functools import wraps
from typing import Any, Callable, Optional

from flask import current_app, g, jsonify, request, session

SAFE_USER_ID_RE = re.compile(r"^[a-zA-Z0-9_\-]{3,64}$")


def ensure_web_session() -> tuple[str, str]:
    """Provision a signed browser session identity and per-session CSRF token."""
    user_id = session.get("user_id")
    if not user_id:
        user_id = f"web-{uuid.uuid4().hex[:16]}"
        session["user_id"] = user_id
        session.permanent = True

    csrf_token = session.get("csrf_token")
    if not csrf_token:
        csrf_token = secrets.token_urlsafe(32)
        session["csrf_token"] = csrf_token

    return user_id, csrf_token


def _extract_bearer_or_api_key() -> Optional[str]:
    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip() or None
    api_key_header = request.headers.get("X-API-Key", "").strip()
    return api_key_header or None


def _validate_api_key(provided_key: str) -> bool:
    configured_key = (current_app.config.get("APP_API_KEY") or "").strip()
    if not configured_key or not provided_key:
        return False
    return hmac.compare_digest(provided_key, configured_key)


def require_api_auth(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Authenticate /api/music/* requests via signed Flask session or Bearer API key.

    - Browser clients authenticate via signed HttpOnly session cookie + X-CSRF-Token on writes.
    - Programmatic clients authenticate via Authorization: Bearer <APP_API_KEY> or X-API-Key.
    - Unauthenticated requests receive 401; invalid CSRF on write requests receives 403.
    """

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        require_auth = current_app.config.get("REQUIRE_AUTH_FOR_API", True)

        # 1. Check programmatic API key authentication first
        provided_key = _extract_bearer_or_api_key()
        if provided_key is not None:
            if not _validate_api_key(provided_key):
                return (
                    jsonify(
                        {
                            "error": "Invalid API credentials.",
                            "code": "invalid_api_key",
                        }
                    ),
                    401,
                )
            requested_user = request.headers.get("X-User-Id", "").strip()
            if requested_user and SAFE_USER_ID_RE.match(requested_user):
                g.user_id = f"api-{requested_user}"
            else:
                g.user_id = "api-client"
            g.auth_method = "api_key"
            return fn(*args, **kwargs)

        # 2. Check signed browser session cookie
        session_user_id = session.get("user_id")
        session_csrf = session.get("csrf_token")
        if session_user_id and session_csrf:
            if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
                sent_csrf = (
                    request.headers.get("X-CSRF-Token", "").strip()
                    or (request.get_json(silent=True) or {}).get("csrf_token", "")
                )
                if not sent_csrf or not hmac.compare_digest(str(sent_csrf), str(session_csrf)):
                    return (
                        jsonify(
                            {
                                "error": "Missing or invalid CSRF token.",
                                "code": "invalid_csrf_token",
                            }
                        ),
                        403,
                    )
            g.user_id = session_user_id
            g.auth_method = "session"
            return fn(*args, **kwargs)

        # 3. Allow unauthenticated only if explicitly disabled via config (not default)
        if not require_auth:
            g.user_id = "anonymous"
            g.auth_method = "disabled"
            return fn(*args, **kwargs)

        return (
            jsonify(
                {
                    "error": "Authentication required. Load the web app session or provide a valid Bearer API key.",
                    "code": "unauthorized",
                }
            ),
            401,
        )

    return wrapper
