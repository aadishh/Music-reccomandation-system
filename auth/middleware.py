"""Authentication middleware supporting Supabase JWTs, HTTP-only cookies, and Flask sessions."""
from __future__ import annotations

import functools
import logging
from typing import Any, Callable, Dict, Optional

from flask import g, jsonify, redirect, request, session, url_for

import config
from database.connection import db_manager
from database.repository import repository

logger = logging.getLogger(__name__)


def get_current_user_from_request() -> Optional[Dict[str, Any]]:
    """Extract authenticated user details from Authorization header, cookies, or session."""
    auth_header = request.headers.get("Authorization", "").strip()
    token: Optional[str] = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()

    if not token:
        token = request.cookies.get("sb_access_token") or session.get("access_token")

    # If Supabase is configured, verify via Supabase Auth
    if db_manager.is_configured and token:
        try:
            client = db_manager.get_client()
            if client:
                resp = client.auth.get_user(token)
                if resp and resp.user:
                    user_dict = {
                        "id": resp.user.id,
                        "email": resp.user.email,
                        "user_metadata": resp.user.user_metadata or {},
                        "app_metadata": resp.user.app_metadata or {},
                    }
                    g.user = user_dict
                    g.user_id = resp.user.id
                    g.user_jwt = token
                    return user_dict
        except Exception as exc:
            logger.debug("Supabase token verification failed: %s", exc)
            # Check if we can refresh using refresh_token in session
            refresh_token = session.get("refresh_token")
            if refresh_token:
                try:
                    refreshed = client.auth.refresh_session(refresh_token)
                    if refreshed and refreshed.session:
                        session["access_token"] = refreshed.session.access_token
                        session["refresh_token"] = refreshed.session.refresh_token
                        user_dict = {
                            "id": refreshed.user.id,
                            "email": refreshed.user.email,
                            "user_metadata": refreshed.user.user_metadata or {},
                        }
                        g.user = user_dict
                        g.user_id = refreshed.user.id
                        g.user_jwt = refreshed.session.access_token
                        return user_dict
                except Exception as ref_exc:
                    logger.debug("Session token refresh failed: %s", ref_exc)

    # Local development / fallback session lookup
    if "user" in session and session.get("user_id"):
        user_dict = session["user"]
        g.user = user_dict
        g.user_id = session["user_id"]
        g.user_jwt = session.get("access_token")
        return user_dict

    # Check for test-mode token
    if token and token.startswith("test-token-"):
        uid = token.replace("test-token-", "")
        profile = repository.get_profile(uid)
        email = profile.get("email") if profile else f"{uid}@example.com"
        user_dict = {"id": uid, "email": email, "user_metadata": {}}
        g.user = user_dict
        g.user_id = uid
        g.user_jwt = token
        return user_dict

    return None


def require_auth(f: Callable) -> Callable:
    """Ensure user is authenticated before accessing endpoint."""

    @functools.wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Any:
        user = get_current_user_from_request()
        if not user:
            # Check if this is an API call or JSON request
            if request.is_json or request.path.startswith("/api/") or "/api" in request.path:
                return jsonify({"error": "Authentication required. Please log in."}), 401
            # Otherwise redirect to login page with return parameter
            return redirect(url_for("auth.login_view", next=request.full_path or request.path))
        return f(*args, **kwargs)

    return decorated


def optional_auth(f: Callable) -> Callable:
    """Populate g.user and g.user_id if present, but do not block unauthenticated users."""

    @functools.wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Any:
        get_current_user_from_request()
        return f(*args, **kwargs)

    return decorated
