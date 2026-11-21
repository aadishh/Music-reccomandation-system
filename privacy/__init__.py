"""Privacy compliance and consent management package."""
from privacy.consent import (
    CONSENT_TYPES,
    ConsentManager,
    consent_manager,
    require_camera_consent,
)
from privacy.routes import privacy_bp

__all__ = [
    "CONSENT_TYPES",
    "ConsentManager",
    "consent_manager",
    "require_camera_consent",
    "privacy_bp",
]
