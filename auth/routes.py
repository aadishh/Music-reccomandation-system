"""Authentication routes implementing Supabase Auth, OAuth, Sessions, and Account Lifecycle."""
from __future__ import annotations

import logging
import os
import secrets
from typing import Any, Dict

from flask import (
    Blueprint,
    flash,
    g,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import config
from auth.middleware import get_current_user_from_request, optional_auth, require_auth
from database.connection import db_manager
from database.repository import repository
from privacy.consent import consent_manager

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _set_auth_session(user_id: str, email: str, access_token: str = "", refresh_token: str = ""):
    session["user_id"] = user_id
    session["user"] = {"id": user_id, "email": email}
    if access_token:
        session["access_token"] = access_token
    if refresh_token:
        session["refresh_token"] = refresh_token


def _clear_auth_session():
    session.pop("user_id", None)
    session.pop("user", None)
    session.pop("access_token", None)
    session.pop("refresh_token", None)
    session.pop("consents", None)


# -----------------------------------------------------------------------------
# Views: Register, Login, Forgot, Reset
# -----------------------------------------------------------------------------


@auth_bp.route("/register", methods=["GET", "POST"])
def register_view():
    """Handle user registration with unbundled, affirmative consent."""
    if request.method == "GET":
        if get_current_user_from_request():
            return redirect(url_for("index"))
        return render_template(
            "auth/register.html",
            default_jurisdiction=config.DEFAULT_JURISDICTION,
            privacy_version=config.PRIVACY_POLICY_VERSION,
            terms_version=config.TERMS_VERSION,
            camera_version=config.CAMERA_CONSENT_VERSION,
        )

    # POST registration
    data = request.form.to_dict() if request.form else (request.get_json(silent=True) or {})
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", "")).strip()
    full_name = str(data.get("full_name", "")).strip()
    country = str(data.get("country", config.DEFAULT_JURISDICTION)).strip().upper()

    # Consents
    terms_consent = bool(data.get("consent_terms"))
    privacy_consent = bool(data.get("consent_privacy"))
    camera_consent = bool(data.get("consent_camera"))
    emotion_history_consent = bool(data.get("consent_emotion_history"))

    # Validation
    if not email or "@" not in email:
        error_msg = "Please provide a valid email address."
        if request.is_json:
            return jsonify({"error": error_msg}), 400
        flash(error_msg, "error")
        return render_template("auth/register.html"), 400

    if len(password) < 8:
        error_msg = "Password must be at least 8 characters long."
        if request.is_json:
            return jsonify({"error": error_msg}), 400
        flash(error_msg, "error")
        return render_template("auth/register.html"), 400

    # Unbundled Terms & Privacy acceptance check
    if not (terms_consent and privacy_consent):
        error_msg = "You must read and agree to the Terms and Conditions and Privacy Policy to register."
        if request.is_json:
            return jsonify({"error": error_msg}), 400
        flash(error_msg, "error")
        return render_template("auth/register.html"), 400

    user_id = None
    access_token = ""
    refresh_token = ""

    # 1. Supabase Auth Registration
    if db_manager.is_configured:
        try:
            client = db_manager.get_client()
            if client:
                auth_res = client.auth.sign_up(
                    {
                        "email": email,
                        "password": password,
                        "options": {
                            "data": {"full_name": full_name, "country": country},
                            "email_redirect_to": f"{config.APP_BASE_URL}/auth/callback",
                        },
                    }
                )
                if auth_res and auth_res.user:
                    user_id = auth_res.user.id
                    if auth_res.session:
                        access_token = auth_res.session.access_token
                        refresh_token = auth_res.session.refresh_token
        except Exception as exc:
            logger.error("Supabase sign_up failed: %s", exc)
            error_text = str(exc)
            if "already registered" in error_text.lower():
                error_msg = "An account with this email already exists."
                if request.is_json:
                    return jsonify({"error": error_msg}), 400
                flash(error_msg, "error")
                return render_template("auth/register.html"), 400
            elif any(
                err in error_text.lower()
                for err in ["nodename nor servname", "connection", "timeout", "network", "name resolution"]
            ):
                logger.warning("Supabase network unavailable during registration; falling back to local registration.")
            else:
                error_msg = f"Registration error: {error_text}"
                if request.is_json:
                    return jsonify({"error": error_msg}), 400
                flash(error_msg, "error")
                return render_template("auth/register.html"), 400

    # Fallback local registration if Supabase is unconfigured
    if not user_id:
        user_id = f"usr_{secrets.token_hex(12)}"
        access_token = f"local-token-{user_id}"

    # 2. Create profile & initial preferences
    repository.create_profile(
        user_id=user_id,
        email=email,
        full_name=full_name,
        country=country,
    )
    repository.update_user_preferences(user_id=user_id, preferences={"preferred_music_provider": "jamendo"})

    # 3. Record individual, auditable consent records (never bundled)
    consent_manager.record_consent(
        user_id=user_id,
        consent_type="terms_and_conditions",
        policy_version=config.TERMS_VERSION,
        accepted=True,
        jurisdiction=country,
        consent_method="registration_form",
    )
    consent_manager.record_consent(
        user_id=user_id,
        consent_type="privacy_policy",
        policy_version=config.PRIVACY_POLICY_VERSION,
        accepted=True,
        jurisdiction=country,
        consent_method="registration_form",
    )
    if camera_consent:
        consent_manager.record_consent(
            user_id=user_id,
            consent_type="camera_processing",
            policy_version=config.CAMERA_CONSENT_VERSION,
            accepted=True,
            jurisdiction=country,
            consent_method="registration_form",
        )
    if emotion_history_consent:
        consent_manager.record_consent(
            user_id=user_id,
            consent_type="emotion_history",
            policy_version="1.0",
            accepted=True,
            jurisdiction=country,
            consent_method="registration_form",
        )

    # 4. Set session
    _set_auth_session(user_id, email, access_token, refresh_token)

    repository.log_security_event(
        user_id=user_id,
        event_type="registration_success",
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None,
        details={"email": email, "country": country},
    )

    if request.is_json:
        return jsonify(
            {
                "success": True,
                "message": "Registration successful.",
                "user_id": user_id,
                "access_token": access_token,
            }
        )

    flash("Account registered successfully! Welcome to Emotion Music Recommender.", "success")
    resp = make_response(redirect(url_for("index")))
    if access_token:
        resp.set_cookie(
            "sb_access_token",
            access_token,
            httponly=True,
            samesite="Lax",
            secure=config.SESSION_COOKIE_SECURE,
        )
    return resp


@auth_bp.route("/login", methods=["GET", "POST"])
def login_view():
    """Handle user email/password login and redirect."""
    next_url = request.args.get("next") or url_for("index")

    if request.method == "GET":
        if get_current_user_from_request():
            return redirect(next_url)
        return render_template("auth/login.html", next_url=next_url)

    data = request.form.to_dict() if request.form else (request.get_json(silent=True) or {})
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", "")).strip()

    if not email or not password:
        error_msg = "Please provide both email and password."
        if request.is_json:
            return jsonify({"error": error_msg}), 400
        flash(error_msg, "error")
        return render_template("auth/login.html", next_url=next_url), 400

    user_id = None
    access_token = ""
    refresh_token = ""

    if db_manager.is_configured:
        try:
            client = db_manager.get_client()
            if client:
                res = client.auth.sign_in_with_password({"email": email, "password": password})
                if res and res.user:
                    user_id = res.user.id
                    if res.session:
                        access_token = res.session.access_token
                        refresh_token = res.session.refresh_token
        except Exception as exc:
            logger.warning("Supabase login failed for %s: %s", email, exc)
            error_text = str(exc).lower()
            is_connection_error = any(
                err in error_text
                for err in ["nodename nor servname", "connection", "timeout", "network", "name resolution"]
            )
            if not is_connection_error:
                repository.log_security_event(
                    user_id=None,
                    event_type="login_failure",
                    ip_address=request.remote_addr,
                    user_agent=request.user_agent.string if request.user_agent else None,
                    details={"email": email, "reason": str(exc)},
                )
                error_msg = "Invalid email or password."
                if request.is_json:
                    return jsonify({"error": error_msg}), 401
                flash(error_msg, "error")
                return render_template("auth/login.html", next_url=next_url), 401
            logger.warning("Supabase network unavailable during login; checking local fallback repository.")

    if not user_id:
        # Check local fallback repository
        profile = repository.get_profile_by_email(email) if hasattr(repository, "get_profile_by_email") else None
        if profile:
            user_id = profile["id"]
            access_token = f"local-token-{user_id}"
        else:
            # Create a session for local testing
            user_id = f"usr_{secrets.token_hex(12)}"
            access_token = f"local-token-{user_id}"
            repository.create_profile(user_id=user_id, email=email, full_name=email.split("@")[0])

    _set_auth_session(user_id, email, access_token, refresh_token)

    repository.log_security_event(
        user_id=user_id,
        event_type="login_success",
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None,
        details={"email": email},
    )

    if request.is_json:
        return jsonify(
            {
                "success": True,
                "message": "Logged in successfully.",
                "user_id": user_id,
                "access_token": access_token,
            }
        )

    flash("Logged in successfully.", "success")
    resp = make_response(redirect(next_url))
    if access_token:
        resp.set_cookie(
            "sb_access_token",
            access_token,
            httponly=True,
            samesite="Lax",
            secure=config.SESSION_COOKIE_SECURE,
        )
    return resp


@auth_bp.route("/google")
def google_oauth():
    """Initiate Google OAuth with Supabase."""
    if not db_manager.is_configured:
        flash("Google OAuth is not configured in this environment.", "warning")
        return redirect(url_for("auth.login_view"))

    try:
        client = db_manager.get_client()
        redirect_to = f"{config.APP_BASE_URL}/auth/callback"
        res = client.auth.sign_in_with_oauth(
            {"provider": "google", "options": {"redirect_to": redirect_to}}
        )
        if res and res.url:
            return redirect(res.url)
        flash("Could not initiate Google authentication.", "error")
        return redirect(url_for("auth.login_view"))
    except Exception as exc:
        logger.error("Google OAuth error: %s", exc)
        flash(f"OAuth initialization failed: {exc}", "error")
        return redirect(url_for("auth.login_view"))


@auth_bp.route("/callback")
def auth_callback():
    """Handle OAuth redirect and email verification callback."""
    # Supabase redirect carries code or access_token in URL / hash
    code = request.args.get("code")
    error = request.args.get("error_description") or request.args.get("error")
    if error:
        flash(f"Authentication error: {error}", "error")
        return redirect(url_for("auth.login_view"))

    if code and db_manager.is_configured:
        try:
            client = db_manager.get_client()
            res = client.auth.exchange_code_for_session({"auth_code": code})
            if res and res.user:
                user_id = res.user.id
                email = res.user.email or ""
                access_token = res.session.access_token if res.session else ""
                refresh_token = res.session.refresh_token if res.session else ""

                # Ensure profile exists
                existing = repository.get_profile(user_id)
                if not existing:
                    full_name = res.user.user_metadata.get("full_name") or res.user.user_metadata.get("name") or ""
                    avatar_url = res.user.user_metadata.get("avatar_url") or ""
                    repository.create_profile(user_id=user_id, email=email, full_name=full_name, avatar_url=avatar_url)

                _set_auth_session(user_id, email, access_token, refresh_token)
                flash("Signed in successfully via Google.", "success")
                resp = make_response(redirect(url_for("index")))
                if access_token:
                    resp.set_cookie(
                        "sb_access_token",
                        access_token,
                        httponly=True,
                        samesite="Lax",
                        secure=config.SESSION_COOKIE_SECURE,
                    )
                return resp
        except Exception as exc:
            logger.error("Callback code exchange error: %s", exc)
            flash(f"Failed to complete login: {exc}", "error")

    # Render callback page that handles client-side hash fragments if present
    return render_template("auth/callback.html")


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    """Sign out the current user and revoke Supabase session."""
    user = get_current_user_from_request()
    user_id = user["id"] if user else session.get("user_id")

    if user_id:
        repository.log_security_event(
            user_id=user_id,
            event_type="logout",
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string if request.user_agent else None,
        )

    if db_manager.is_configured and session.get("access_token"):
        try:
            client = db_manager.get_client()
            if client:
                client.auth.sign_out()
        except Exception as exc:
            logger.debug("Supabase sign_out error: %s", exc)

    _clear_auth_session()

    if request.is_json or request.headers.get("Accept") == "application/json" or request.headers.get("Authorization") or request.method == "POST":
        return jsonify({"success": True, "message": "Logged out successfully."})

    flash("You have been signed out.", "info")
    resp = make_response(redirect(url_for("index")))
    resp.delete_cookie("sb_access_token")
    return resp


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Request password reset link via Supabase Auth."""
    if request.method == "GET":
        return render_template("auth/forgot_password.html")

    data = request.form.to_dict() if request.form else (request.get_json(silent=True) or {})
    email = str(data.get("email", "")).strip().lower()

    if not email:
        error_msg = "Please enter your email address."
        if request.is_json:
            return jsonify({"error": error_msg}), 400
        flash(error_msg, "error")
        return render_template("auth/forgot_password.html"), 400

    if db_manager.is_configured:
        try:
            client = db_manager.get_client()
            if client:
                redirect_to = f"{config.APP_BASE_URL}/auth/reset-password"
                client.auth.reset_password_email(email, {"redirect_to": redirect_to})
        except Exception as exc:
            logger.warning("Supabase reset_password_email failed for %s: %s", email, exc)

    repository.log_security_event(
        user_id=None,
        event_type="password_reset_requested",
        ip_address=request.remote_addr,
        details={"email": email},
    )

    success_msg = "If an account with that email exists, password reset instructions have been sent."
    if request.is_json:
        return jsonify({"success": True, "message": success_msg})

    flash(success_msg, "info")
    return render_template("auth/forgot_password.html")


@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    """Set a new password after following reset link."""
    if request.method == "GET":
        return render_template("auth/reset_password.html")

    data = request.form.to_dict() if request.form else (request.get_json(silent=True) or {})
    password = str(data.get("password", "")).strip()

    if len(password) < 8:
        error_msg = "Password must be at least 8 characters long."
        if request.is_json:
            return jsonify({"error": error_msg}), 400
        flash(error_msg, "error")
        return render_template("auth/reset_password.html"), 400

    user = get_current_user_from_request()
    if not user:
        error_msg = "Reset token expired or invalid. Please request a new password reset."
        if request.is_json:
            return jsonify({"error": error_msg}), 400
        flash(error_msg, "error")
        return redirect(url_for("auth.forgot_password"))

    if db_manager.is_configured:
        try:
            client = db_manager.get_client(g.user_jwt)
            if client:
                client.auth.update_user({"password": password})
        except Exception as exc:
            logger.error("Supabase update_user password failed: %s", exc)
            if request.is_json:
                return jsonify({"error": str(exc)}), 400
            flash(f"Failed to reset password: {exc}", "error")
            return render_template("auth/reset_password.html"), 400

    repository.log_security_event(
        user_id=user["id"],
        event_type="password_reset_completed",
        ip_address=request.remote_addr,
    )

    if request.is_json:
        return jsonify({"success": True, "message": "Password updated successfully."})

    flash("Your password has been updated. You may now log in.", "success")
    return redirect(url_for("auth.login_view"))


# -----------------------------------------------------------------------------
# User Profile, Preferences & Cascading Deletion
# -----------------------------------------------------------------------------


@auth_bp.route("/me", methods=["GET"])
@require_auth
def get_current_user_profile():
    """Return profile and preferences for authenticated user."""
    user_id = g.user_id
    profile = repository.get_profile(user_id) or {"id": user_id, "email": g.user.get("email")}
    preferences = repository.get_user_preferences(user_id)
    consents = consent_manager.get_all_consents(user_id)
    return jsonify({"profile": profile, "preferences": preferences, "consents": consents})


@auth_bp.route("/profile", methods=["POST"])
@require_auth
def update_profile():
    """Update profile details (name, avatar, country)."""
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    user_id = g.user_id

    profile = repository.update_profile(
        user_id=user_id,
        full_name=data.get("full_name"),
        avatar_url=data.get("avatar_url"),
        country=data.get("country"),
    )
    return jsonify({"success": True, "profile": profile})


@auth_bp.route("/preferences", methods=["POST"])
@require_auth
def update_preferences():
    """Update user music settings."""
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    user_id = g.user_id

    updated = repository.update_user_preferences(user_id=user_id, preferences=data)
    return jsonify({"success": True, "preferences": updated})


@auth_bp.route("/delete-account", methods=["POST"])
@require_auth
def delete_account():
    """Permanently delete user account and cascade across all tables & Supabase Auth."""
    user_id = g.user_id
    email = g.user.get("email", "")

    # Perform cascading deletion in repository and Supabase Auth
    result = repository.delete_user_account(user_id)

    # Log security audit event
    repository.log_security_event(
        user_id=user_id,
        event_type="account_deleted",
        ip_address=request.remote_addr,
        details={"email": email, "cascade_result": result},
    )

    _clear_auth_session()

    if request.is_json or request.headers.get("Accept") == "application/json" or request.headers.get("Authorization"):
        return jsonify(
            {
                "success": True,
                "message": "Your account and all associated personal data have been permanently deleted.",
                "deleted": result,
            }
        )

    flash("Your account and all associated data have been permanently deleted.", "info")
    resp = make_response(redirect(url_for("index")))
    resp.delete_cookie("sb_access_token")
    return resp
