"""Unified domain models for tracks, licensing, playback, providers, and recommendations."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class DeploymentMode(str, Enum):
    NON_COMMERCIAL = "non_commercial"
    COMMERCIAL = "commercial"


class LicensingVerificationStatus(str, Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    RESTRICTED = "restricted"
    BLOCKED = "blocked"


class RecommendationMode(str, Enum):
    MOOD_MATCHING = "mood_matching"
    MOOD_SHIFTING = "mood_shifting"


@dataclass
class LicensingMetadata:
    """Structured licensing & rights compliance record for a track."""

    license_type: str
    license_source: str
    permitted_playback_type: str  # e.g., "direct_stream", "time_limited_stream", "preview_only", "none"
    commercial_use_allowed: bool
    redistribution_allowed: bool = False
    attribution_required: bool = True
    attribution_text: Optional[str] = None
    license_url: Optional[str] = None
    verification_status: str = LicensingVerificationStatus.UNVERIFIED.value
    restriction_reason: Optional[str] = None
    commercial_approval_required: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UnifiedTrack:
    """Provider-independent normalized track schema."""

    internal_id: str
    provider: str
    provider_track_id: str
    title: str
    artist: str
    album: Optional[str] = None
    genre: Optional[str] = None
    duration: Optional[int] = None  # Duration in seconds
    bpm: Optional[float] = None
    energy: Optional[float] = None  # Normalized 0.0 - 1.0 when available/estimated
    mood_tags: List[str] = field(default_factory=list)
    language: Optional[str] = None
    artwork: Optional[str] = None
    preview_url: Optional[str] = None
    playback_url: Optional[str] = None
    playback_reference: Optional[str] = None
    playback_expires_at: Optional[str] = None  # ISO-8601 UTC timestamp if stream URL expires
    is_available: bool = True
    licensing: LicensingMetadata = field(
        default_factory=lambda: LicensingMetadata(
            license_type="unknown",
            license_source="unknown",
            permitted_playback_type="none",
            commercial_use_allowed=False,
            redistribution_allowed=False,
            attribution_required=True,
            verification_status=LicensingVerificationStatus.UNVERIFIED.value,
        )
    )
    provider_metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def license_type(self) -> str:
        return self.licensing.license_type

    @property
    def license_source(self) -> str:
        return self.licensing.license_source

    @property
    def commercial_usage_status(self) -> str:
        if self.licensing.verification_status == LicensingVerificationStatus.BLOCKED.value:
            return "blocked"
        if self.licensing.commercial_use_allowed and self.licensing.verification_status == LicensingVerificationStatus.VERIFIED.value:
            return "allowed"
        if self.licensing.commercial_approval_required:
            return "requires_commercial_approval"
        return "non_commercial_only"

    @property
    def attribution_requirements(self) -> Dict[str, Any]:
        return {
            "required": self.licensing.attribution_required,
            "text": self.licensing.attribution_text,
            "license_url": self.licensing.license_url,
        }

    def is_stream_expired(self, now: Optional[datetime] = None) -> bool:
        if not self.playback_expires_at:
            return False
        now = now or datetime.now(timezone.utc)
        try:
            expires = datetime.fromisoformat(self.playback_expires_at.replace("Z", "+00:00"))
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            return now >= expires
        except ValueError:
            return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "internal_id": self.internal_id,
            "provider": self.provider,
            "provider_track_id": self.provider_track_id,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "genre": self.genre,
            "duration": self.duration,
            "bpm": self.bpm,
            "energy": self.energy,
            "mood_tags": list(self.mood_tags),
            "language": self.language,
            "artwork": self.artwork,
            "preview_url": self.preview_url,
            "playback_url": self.playback_url,
            "playback_reference": self.playback_reference,
            "playback_expires_at": self.playback_expires_at,
            "is_available": self.is_available,
            "license_type": self.license_type,
            "license_source": self.license_source,
            "commercial_usage_status": self.commercial_usage_status,
            "attribution_requirements": self.attribution_requirements,
            "licensing": self.licensing.to_dict(),
            "provider_metadata": dict(self.provider_metadata),
        }


@dataclass
class PlaybackInfo:
    """Authorized playback resolution payload returned to the client player."""

    internal_id: str
    provider: str
    provider_track_id: str
    playback_url: Optional[str]
    playback_reference: Optional[str]
    playback_type: str
    expires_at: Optional[str]
    is_playable: bool
    licensing: LicensingMetadata
    attribution_text: Optional[str] = None
    refresh_supported: bool = True

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        if not self.expires_at:
            return False
        now = now or datetime.now(timezone.utc)
        try:
            expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            return now >= expires
        except ValueError:
            return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "internal_id": self.internal_id,
            "provider": self.provider,
            "provider_track_id": self.provider_track_id,
            "playback_url": self.playback_url,
            "playback_reference": self.playback_reference,
            "playback_type": self.playback_type,
            "expires_at": self.expires_at,
            "is_playable": self.is_playable,
            "refresh_supported": self.refresh_supported,
            "attribution_text": self.attribution_text,
            "licensing": self.licensing.to_dict(),
        }


@dataclass
class PlaylistSummary:
    """Normalized playlist / channel summary."""

    internal_id: str
    provider: str
    provider_playlist_id: str
    name: str
    description: Optional[str] = None
    artwork: Optional[str] = None
    track_count: Optional[int] = None
    tags: List[str] = field(default_factory=list)
    provider_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ProviderCapabilities:
    """Declares which standardized methods a provider supports."""

    search_tracks: bool = True
    get_track_details: bool = True
    get_track_stream: bool = True
    get_playlists: bool = True
    get_recommendations: bool = True
    commercial_tier_available: bool = False
    requires_paid_plan_for_commercial: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ProviderStatus:
    """Health, configuration, and licensing summary for a provider (no secrets)."""

    provider: str
    configured: bool
    healthy: bool
    status: str  # "healthy", "degraded", "unconfigured", "unavailable"
    message: str
    capabilities: ProviderCapabilities
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    latency_ms: Optional[float] = None
    licensing_notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["capabilities"] = self.capabilities.to_dict()
        return data


@dataclass
class RecommendationRequest:
    """Inputs for the AI emotion recommendation engine."""

    detected_emotion: str = "neutral"
    emotion_confidence: float = 0.75  # 0.0 - 1.0 (or 0 - 100 normalized internally)
    user_selected_mood: Optional[str] = None
    preferred_genres: List[str] = field(default_factory=list)
    preferred_artists: List[str] = field(default_factory=list)
    language: Optional[str] = None
    mode: str = RecommendationMode.MOOD_MATCHING.value
    limit: int = 15
    providers: Optional[List[str]] = None
    user_id: Optional[str] = None


@dataclass
class ScoredTrack:
    """A recommended UnifiedTrack with explainable scoring breakdown."""

    track: UnifiedTrack
    score: float
    score_breakdown: Dict[str, float]
    recommendation_mode: str
    target_profile: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        data = self.track.to_dict()
        data["recommendation_score"] = round(self.score, 4)
        data["score_breakdown"] = {k: round(v, 4) for k, v in self.score_breakdown.items()}
        data["recommendation_mode"] = self.recommendation_mode
        data["target_profile"] = self.target_profile
        return data


def make_internal_track_id(provider: str, provider_track_id: str) -> str:
    return f"{provider.strip().lower()}:{str(provider_track_id).strip()}"


def parse_internal_track_id(internal_id: str) -> tuple[str, str]:
    if ":" not in internal_id:
        raise ValueError(f"Invalid internal track ID '{internal_id}'; expected '<provider>:<track_id>'")
    provider, provider_track_id = internal_id.split(":", 1)
    provider = provider.strip().lower()
    provider_track_id = provider_track_id.strip()
    if not provider or not provider_track_id:
        raise ValueError(f"Invalid internal track ID '{internal_id}'")
    return provider, provider_track_id
