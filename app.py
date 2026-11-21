"""Flask application for the DeepFace Emotion Multi-Provider Music Recommender."""
from __future__ import annotations

import base64
import logging
import os
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from flask import Flask, current_app, jsonify, render_template, request
from flask_cors import CORS

import config
from emotion_fallback import FallbackEmotionDetector
from music.auth import ensure_web_session
from music.models import RecommendationMode, RecommendationRequest
from music.recommendation import EmotionRecommendationEngine
from music.registry import ProviderRegistry
from music.routes import music_bp
from music.storage import MusicStorage

from auth.middleware import get_current_user_from_request, optional_auth
from auth.routes import auth_bp
from dashboard.routes import dashboard_bp
from database.repository import repository
from privacy.consent import consent_manager
from privacy.routes import privacy_bp

# Suppress TensorFlow warnings
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to load OpenCV and NumPy (required for image decoding)
try:
    import cv2
    import numpy as np

    CV2_AVAILABLE = True
except ImportError:
    cv2 = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]
    CV2_AVAILABLE = False
    logger.warning("OpenCV/NumPy not available; falling back to lightweight emotion analysis.")

# Try to load DeepFace + TensorFlow cleanly (fixes unreachable ImportError bug)
DEEPFACE_AVAILABLE = False
try:
    import tensorflow as tf

    tf.get_logger().setLevel("ERROR")
    from deepface import DeepFace

    DEEPFACE_AVAILABLE = True
    logger.info("DeepFace + TensorFlow loaded successfully")
except ImportError as exc:
    DEEPFACE_AVAILABLE = False
    logger.info("DeepFace/TensorFlow not available (%s); using FallbackEmotionDetector", exc)


def convert_to_json_serializable(obj: Any) -> Any:
    """Convert numpy types to JSON serializable Python types."""
    if hasattr(obj, "item"):
        return obj.item()
    if hasattr(obj, "tolist"):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: convert_to_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_to_json_serializable(v) for v in obj]
    return obj


class DeepFaceEmotionSystem:
    """Handles facial emotion detection with DeepFace and automatic fallback."""

    def __init__(self) -> None:
        self.current_emotion: Optional[str] = None
        self.songs_played: int = 0
        self.songs_before_recheck: int = config.AUTO_CAPTURE_SETTINGS["songs_before_recheck"]
        self.last_check_time: Optional[datetime] = None
        self.auto_capture_enabled: bool = config.AUTO_CAPTURE_SETTINGS["enabled"]
        self.auto_capture_interval: int = config.AUTO_CAPTURE_SETTINGS["interval_seconds"]
        self.is_running: bool = False
        self.fallback_detector = FallbackEmotionDetector()

        detector_type = "DeepFace" if DEEPFACE_AVAILABLE else "Fallback"
        logger.info("Emotion System initialized with %s detector", detector_type)

    def analyze_emotion_from_base64(self, image_data: str) -> Dict[str, Any]:
        """Analyze emotion from base64 data URL using DeepFace or FallbackEmotionDetector."""
        if not DEEPFACE_AVAILABLE or not CV2_AVAILABLE:
            result = self.fallback_detector.analyze_emotion_from_base64(image_data)
            self.current_emotion = result.get("dominant_emotion", "neutral")
            self.last_check_time = datetime.now(timezone.utc)
            return result

        try:
            encoded = image_data.split(",", 1)[1] if "," in image_data else image_data
            image_bytes = base64.b64decode(encoded)
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img is None:
                raise ValueError("Could not decode image")

            # Strictly in-memory analysis: frames are never saved to disk or persistent storage
            logger.info("Analyzing emotion with DeepFace (in-memory, no disk persistence)...")
            try:
                predictions = DeepFace.analyze(img, actions=["emotion"], enforce_detection=False)
            finally:
                # Immediate cleanup: prevent image retention in memory or templates
                del nparr, image_bytes
            emotion_data = predictions[0] if isinstance(predictions, list) else predictions

            dominant_emotion = str(emotion_data["dominant_emotion"]).lower()
            emotion_scores_clean = convert_to_json_serializable(emotion_data["emotion"])
            emotion_percentages = {k.lower(): round(float(v), 2) for k, v in emotion_scores_clean.items()}

            # Free raw decoded image array from memory
            del img

            self.current_emotion = dominant_emotion
            self.last_check_time = datetime.now(timezone.utc)
            logger.info("DeepFace detected emotion: %s", dominant_emotion)

            return {
                "dominant_emotion": dominant_emotion,
                "emotion_scores": emotion_percentages,
                "success": True,
                "detector": "DeepFace",
                "confidence": emotion_percentages.get(dominant_emotion, 0.0),
            }
        except Exception as exc:
            logger.error("DeepFace emotion analysis failed: %s", exc)
            fallback_emotion = random.choice(config.SUPPORTED_EMOTIONS)
            self.current_emotion = fallback_emotion
            self.last_check_time = datetime.now(timezone.utc)
            return {
                "dominant_emotion": fallback_emotion,
                "emotion_scores": {fallback_emotion: 85.0, "neutral": 15.0},
                "success": False,
                "error": str(exc),
                "detector": "Fallback (Random)",
                "confidence": 85.0,
                "message": f"DeepFace failed, using fallback: {fallback_emotion}",
            }

    def start_auto_capture(self) -> None:
        self.is_running = True
        self.auto_capture_enabled = True
        logger.info("Client-driven auto-capture mode enabled")

    def stop_auto_capture(self) -> None:
        self.is_running = False
        self.auto_capture_enabled = False
        logger.info("Client-driven auto-capture mode disabled")


def create_app(
    *,
    registry: Optional[ProviderRegistry] = None,
    storage: Optional[MusicStorage] = None,
    recommendation_weights: Optional[Dict[str, float]] = None,
    config_overrides: Optional[Dict[str, Any]] = None,
) -> Flask:
    """Application factory for production and testability."""
    flask_app = Flask(__name__)

    flask_app.config.update(
        SECRET_KEY=config.FLASK_SECRET_KEY,
        APP_API_KEY=config.APP_API_KEY,
        REQUIRE_AUTH_FOR_API=config.REQUIRE_AUTH_FOR_API,
        APP_DEPLOYMENT_MODE=config.APP_DEPLOYMENT_MODE,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=config.SESSION_COOKIE_SECURE,
        PERMANENT_SESSION_LIFETIME=timedelta(days=7),
    )
    if config_overrides:
        flask_app.config.update(config_overrides)

    CORS(flask_app, supports_credentials=True)

    # Initialize multi-provider music subsystem
    active_registry = registry or ProviderRegistry.from_config(
        provider_config=config.PROVIDER_CONFIG,
        http_settings=config.HTTP_SETTINGS,
        cache_settings=config.CACHE_SETTINGS,
        deployment_mode=flask_app.config["APP_DEPLOYMENT_MODE"],
    )
    active_storage = storage or MusicStorage(db_path=config.DATABASE_PATH)
    rec_engine = EmotionRecommendationEngine(
        registry=active_registry,
        storage=active_storage,
        weights=recommendation_weights or config.DEFAULT_RECOMMENDATION_WEIGHTS,
    )
    emotion_sys = DeepFaceEmotionSystem()

    flask_app.extensions["music_registry"] = active_registry
    flask_app.extensions["music_storage"] = active_storage
    flask_app.extensions["recommendation_engine"] = rec_engine
    flask_app.extensions["emotion_system"] = emotion_sys

    flask_app.register_blueprint(music_bp)
    flask_app.register_blueprint(auth_bp)
    flask_app.register_blueprint(privacy_bp)
    flask_app.register_blueprint(dashboard_bp)

    @flask_app.route("/")
    def index():
        """Serve the main web interface and provision a signed session + CSRF token."""
        user_id, csrf_token = ensure_web_session()
        user = get_current_user_from_request()
        has_camera_consent = consent_manager.has_consent(user_id, "camera_processing")
        consents = consent_manager.get_all_consents(user_id)
        return render_template(
            "index.html",
            csrf_token=csrf_token,
            deployment_mode=active_registry.licensing_validator.deployment_mode.value,
            supported_emotions=config.SUPPORTED_EMOTIONS,
            user=user,
            has_camera_consent=has_camera_consent,
            consents=consents,
            policy_version=config.PRIVACY_POLICY_VERSION,
        )

    @flask_app.route("/camera-test")
    def camera_test():
        """Serve camera test page for debugging."""
        return render_template("camera_test.html")

    @flask_app.route("/analyze", methods=["POST"])
    def analyze_emotion():
        """Analyze emotion from uploaded webcam frame and return multi-provider recommendations."""
        try:
            data = request.get_json(silent=True) or {}
            image_data = data.get("image")
            if not image_data:
                return jsonify({"error": "No image data provided"}), 400

            user_id, _ = ensure_web_session()
            sys_inst: DeepFaceEmotionSystem = current_app.extensions["emotion_system"]
            engine: EmotionRecommendationEngine = current_app.extensions["recommendation_engine"]

            # Strict Privacy Gate: Verify camera & facial processing consent before analyzing frames
            has_cam_consent = consent_manager.has_consent(user_id, "camera_processing")
            if not has_cam_consent:
                # Check for just-in-time affirmative consent grant in request payload
                if data.get("camera_consent_granted") is True:
                    consent_manager.record_consent(
                        user_id=user_id,
                        consent_type="camera_processing",
                        accepted=True,
                        jurisdiction=data.get("jurisdiction"),
                        consent_method="jit_modal_affirmation",
                    )
                    has_cam_consent = True
                else:
                    return (
                        jsonify(
                            {
                                "error": "Explicit affirmative consent is required before processing webcam frames.",
                                "consent_required": "camera_processing",
                                "policy_version": config.CAMERA_CONSENT_VERSION,
                                "disclosure": (
                                    "Webcam frames are analyzed strictly in-memory and discarded immediately after inference. "
                                    "No photos, video recordings, or facial biometric templates are ever saved to disk or persistent storage."
                                ),
                            }
                        ),
                        403,
                    )

            result = sys_inst.analyze_emotion_from_base64(image_data)
            dominant_emotion = result.get("dominant_emotion", "neutral")
            confidence = float(result.get("confidence", 75.0))

            # Opt-in Emotion History: Only store detected emotion if user explicitly opted in
            if consent_manager.has_consent(user_id, "emotion_history"):
                try:
                    repository.record_emotion(
                        user_id=user_id,
                        detected_emotion=dominant_emotion,
                        confidence_score=confidence,
                    )
                except Exception as repo_exc:
                    logger.warning("Could not persist emotion event: %s", repo_exc)

            mode = str(data.get("mode") or RecommendationMode.MOOD_MATCHING.value).strip().lower()
            if mode not in {RecommendationMode.MOOD_MATCHING.value, RecommendationMode.MOOD_SHIFTING.value}:
                mode = RecommendationMode.MOOD_MATCHING.value

            rec_request = RecommendationRequest(
                detected_emotion=dominant_emotion,
                emotion_confidence=confidence,
                user_selected_mood=data.get("mood") or None,
                preferred_genres=data.get("genres") or [],
                preferred_artists=data.get("artists") or [],
                language=data.get("language") or None,
                mode=mode,
                limit=int(data.get("limit", 15)),
                providers=data.get("providers") or None,
                user_id=user_id,
            )
            recommendations = engine.recommend(rec_request)

            sys_inst.songs_played += 1
            result["emotion"] = dominant_emotion
            result["songs_played"] = sys_inst.songs_played
            result["recommendations"] = recommendations
            result["recommended_tracks"] = recommendations.get("tracks", [])

            return jsonify(convert_to_json_serializable(result))
        except Exception as exc:
            logger.error("Analysis endpoint error: %s", exc)
            return jsonify({"error": str(exc)}), 500

    @flask_app.route("/auto-capture", methods=["POST"])
    def toggle_auto_capture():
        """Toggle client-driven automatic emotion capture state."""
        try:
            data = request.get_json(silent=True) or {}
            enable = bool(data.get("enable", False))
            sys_inst: DeepFaceEmotionSystem = current_app.extensions["emotion_system"]

            user_id, _ = ensure_web_session()
            if enable and not consent_manager.has_consent(user_id, "camera_processing"):
                if data.get("camera_consent_granted") is True:
                    consent_manager.record_consent(
                        user_id=user_id,
                        consent_type="camera_processing",
                        accepted=True,
                        jurisdiction=data.get("jurisdiction"),
                        consent_method="jit_modal_affirmation",
                    )
                else:
                    return (
                        jsonify(
                            {
                                "error": "Camera processing consent required before enabling auto-capture.",
                                "consent_required": "camera_processing",
                                "disclosure": (
                                    "Webcam frames are analyzed strictly in-memory and discarded immediately after inference."
                                ),
                            }
                        ),
                        403,
                    )

            if enable:
                sys_inst.start_auto_capture()
                message = "Auto-capture started"
            else:
                sys_inst.stop_auto_capture()
                message = "Auto-capture stopped"

            return jsonify(
                {
                    "success": True,
                    "message": message,
                    "auto_capture_enabled": sys_inst.is_running,
                    "interval_seconds": sys_inst.auto_capture_interval,
                }
            )
        except Exception as exc:
            logger.error("Auto-capture toggle error: %s", exc)
            return jsonify({"error": str(exc)}), 500

    @flask_app.route("/settings", methods=["GET", "POST"])
    def settings():
        """Get or update system settings."""
        sys_inst: DeepFaceEmotionSystem = current_app.extensions["emotion_system"]

        if request.method == "GET":
            return jsonify(
                {
                    "songs_before_recheck": sys_inst.songs_before_recheck,
                    "current_emotion": sys_inst.current_emotion,
                    "songs_played": sys_inst.songs_played,
                    "auto_capture_enabled": sys_inst.auto_capture_enabled,
                    "auto_capture_interval": sys_inst.auto_capture_interval,
                    "deployment_mode": active_registry.licensing_validator.deployment_mode.value,
                }
            )

        data = request.get_json(silent=True) or {}
        if "songs_before_recheck" in data:
            sys_inst.songs_before_recheck = max(1, min(20, int(data["songs_before_recheck"])))
        if "auto_capture_enabled" in data:
            sys_inst.auto_capture_enabled = bool(data["auto_capture_enabled"])
        if "auto_capture_interval" in data:
            sys_inst.auto_capture_interval = max(10, min(300, int(data["auto_capture_interval"])))

        return jsonify({"success": True})

    @flask_app.route("/reset", methods=["POST"])
    def reset_counter():
        """Reset the song counter."""
        sys_inst: DeepFaceEmotionSystem = current_app.extensions["emotion_system"]
        sys_inst.songs_played = 0
        return jsonify({"success": True, "songs_played": 0})

    @flask_app.route("/health")
    def health_check():
        """Health check endpoint (safe, exposes no provider secrets)."""
        sys_inst: DeepFaceEmotionSystem = current_app.extensions["emotion_system"]
        reg: ProviderRegistry = current_app.extensions["music_registry"]
        configured = [p.name for p in reg.get_configured_providers()]
        return jsonify(
            {
                "status": "healthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "emotion_detector": "DeepFace" if DEEPFACE_AVAILABLE else "Fallback",
                "version": "4.0-multi-provider",
                "auto_capture": sys_inst.is_running,
                "configured_providers": configured,
                "deployment_mode": reg.licensing_validator.deployment_mode.value,
            }
        )

    @flask_app.route("/test")
    def test_emotion():
        """System capabilities overview endpoint."""
        reg: ProviderRegistry = current_app.extensions["music_registry"]
        return jsonify(
            {
                "message": "DeepFace multi-provider emotion music recommender ready",
                "detector": "DeepFace" if DEEPFACE_AVAILABLE else "Fallback",
                "supported_emotions": config.SUPPORTED_EMOTIONS,
                "providers": reg.list_provider_names(),
                "recommendation_modes": [
                    RecommendationMode.MOOD_MATCHING.value,
                    RecommendationMode.MOOD_SHIFTING.value,
                ],
                "features": [
                    "DeepFace facial emotion detection with fallback",
                    "Multi-provider music API abstraction (Jamendo, Audius, optional Mubert)",
                    "Unified track normalization and strict licensing compliance",
                    "Weighted Mood Matching & Mood Shifting recommendation engine",
                    "Built-in unified HTML5 audio player",
                ],
            }
        )

    return flask_app


# Module-level Flask instance for Gunicorn (`gunicorn app:app`) and `python app.py`
app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info("Starting Emotion Music Recommender (Multi-Provider Edition) on http://localhost:%s", port)
    app.run(host="0.0.0.0", port=port, debug=False)
