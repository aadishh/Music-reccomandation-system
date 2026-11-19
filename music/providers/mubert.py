"""Mubert API v3 provider integration (optional future / B2B generative audio integration).

Verified architecture (https://music-api.mubert.com/api/v3):
- Service layer (/api/v3/service/*): requires company-id and license-token headers (paid B2B/API plan).
  - GET /api/v3/service/licenses — verifies active license & quota.
  - POST /api/v3/service/customers — provisions customer-id and access-token for public layer calls.
- Public layer (/api/v3/public/*): requires customer-id and access-token headers.
  - GET /api/v3/public/playlists — retrieves mood/activity generative channels.
  - POST /api/v3/public/streaming/get-link — retrieves a time-limited authorized stream URL.

Unsupported operations (explicitly declared):
- search_tracks() — Mubert is a generative channel/stream API, not a static song catalog search API.
- get_track_details() — Static catalog track lookup is not supported; raises UnsupportedOperationError.

Commercial & Licensing notes:
- Requires an active paid Mubert commercial/API plan.
- DSP distribution, Content ID registration, and stock library resale are strictly prohibited on all plans.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from music.cache import MetadataTTLCache
from music.exceptions import (
    MusicProviderError,
    ProviderConfigError,
    UnsupportedOperationError,
)
from music.http_client import ResilientHTTPClient
from music.licensing import build_mubert_licensing
from music.models import (
    PlaybackInfo,
    PlaylistSummary,
    ProviderCapabilities,
    ProviderStatus,
    UnifiedTrack,
    make_internal_track_id,
)
from music.providers.base import BaseMusicProvider

logger = logging.getLogger(__name__)


class MubertProvider(BaseMusicProvider):
    """Mubert API v3 optional integration."""

    name = "mubert"

    def __init__(
        self,
        *,
        company_id: str = "",
        license_token: str = "",
        base_url: str = "https://music-api.mubert.com/api/v3",
        stream_base_url: str = "https://stream.mubert.com/b2b/v3",
        default_stream_ttl_seconds: int = 900,
        enabled: bool = True,
        http_client: Optional[ResilientHTTPClient] = None,
        cache: Optional[MetadataTTLCache] = None,
        metadata_ttl: int = 300,
        health_ttl: int = 60,
    ) -> None:
        super().__init__(
            enabled=enabled,
            http_client=http_client,
            cache=cache,
            metadata_ttl=metadata_ttl,
            health_ttl=health_ttl,
        )
        self.company_id = company_id.strip()
        self.license_token = license_token.strip()
        self.base_url = base_url.rstrip("/")
        self.stream_base_url = stream_base_url.rstrip("/")
        self.default_stream_ttl_seconds = max(60, int(default_stream_ttl_seconds))
        self._customer_credentials: Optional[Tuple[str, str]] = None
        self._verified_plan_name: Optional[str] = None
        self._license_verified: bool = False

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            search_tracks=False,
            get_track_details=False,
            get_track_stream=True,
            get_playlists=True,
            get_recommendations=True,
            commercial_tier_available=True,
            requires_paid_plan_for_commercial=True,
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.enabled and self.company_id and self.license_token)

    def _require_configured(self) -> None:
        if not self.enabled:
            raise ProviderConfigError("Mubert provider is disabled.", provider=self.name)
        if not (self.company_id and self.license_token):
            raise ProviderConfigError(
                "MUBERT_COMPANY_ID and MUBERT_LICENSE_TOKEN are required for Mubert API v3.",
                provider=self.name,
            )

    def _service_headers(self) -> Dict[str, str]:
        return {
            "company-id": self.company_id,
            "license-token": self.license_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _ensure_customer_headers(self) -> Dict[str, str]:
        self._require_configured()
        if self._customer_credentials is None:
            payload = self.http_client.request_json(
                "POST",
                f"{self.base_url}/service/customers",
                headers=self._service_headers(),
                json_body={"custom_id": "emotion-music-recommender-service"},
            )
            data = (payload or {}).get("data") if isinstance(payload, dict) else {}
            customer_id = str((data or {}).get("id") or (data or {}).get("customer_id") or "").strip()
            access_token = str((data or {}).get("access_token") or (data or {}).get("token") or "").strip()
            if not customer_id or not access_token:
                raise MusicProviderError(
                    "Mubert customer credential provisioning did not return customer_id and access_token.",
                    provider=self.name,
                )
            self._customer_credentials = (customer_id, access_token)

        customer_id, access_token = self._customer_credentials
        return {
            "customer-id": customer_id,
            "access-token": access_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def verify_license(self) -> Dict[str, Any]:
        """Verify active Mubert commercial license & quotas via /api/v3/service/licenses."""
        self._require_configured()
        payload = self.http_client.request_json(
            "GET",
            f"{self.base_url}/service/licenses",
            headers=self._service_headers(),
        )
        if not isinstance(payload, dict):
            raise MusicProviderError("Unexpected Mubert license response.", provider=self.name)

        data = payload.get("data")
        licenses = data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])
        active_license = next(
            (lic for lic in licenses if isinstance(lic, dict) and lic.get("is_active", True)),
            None,
        )
        self._license_verified = active_license is not None
        self._verified_plan_name = (
            str(active_license.get("name") or active_license.get("plan") or "B2B")
            if active_license
            else None
        )
        return {
            "verified": self._license_verified,
            "plan": self._verified_plan_name,
            "licenses": licenses,
        }

    def search_tracks(
        self,
        query: str = "",
        *,
        genre: Optional[str] = None,
        mood: Optional[str] = None,
        language: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[UnifiedTrack]:
        raise UnsupportedOperationError(
            "Mubert API v3 provides generative mood/channel streams and does not support static track search.",
            provider=self.name,
        )

    def get_track_details(self, provider_track_id: str) -> UnifiedTrack:
        raise UnsupportedOperationError(
            "Mubert API v3 does not expose static catalog track detail lookups; use get_playlists() or get_track_stream().",
            provider=self.name,
        )

    def get_playlists(
        self,
        *,
        query: Optional[str] = None,
        mood: Optional[str] = None,
        limit: int = 10,
    ) -> List[PlaylistSummary]:
        self._require_configured()
        limit = max(1, min(int(limit), 30))
        cache_key = f"mubert:playlists:{query}:{mood}:{limit}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        payload = self.http_client.request_json(
            "GET",
            f"{self.base_url}/public/playlists",
            headers=self._ensure_customer_headers(),
        ) or {}
        raw_channels = payload.get("data") or payload.get("categories") or []
        filter_term = (query or mood or "").strip().lower()

        summaries: List[PlaylistSummary] = []
        for item in raw_channels:
            if not isinstance(item, dict):
                continue
            channel_id = str(item.get("playlist_index") or item.get("id") or "").strip()
            name = str(item.get("name") or item.get("title") or "Mubert Channel").strip()
            if not channel_id:
                continue
            if filter_term and filter_term not in name.lower():
                continue
            summaries.append(
                PlaylistSummary(
                    internal_id=make_internal_track_id(self.name, channel_id),
                    provider=self.name,
                    provider_playlist_id=channel_id,
                    name=name,
                    description=item.get("description") or "Mubert generative audio channel",
                    artwork=item.get("image") or None,
                    track_count=None,
                    tags=[str(t).lower() for t in (item.get("tags") or []) if t],
                    provider_metadata=dict(item),
                )
            )
            if len(summaries) >= limit:
                break

        self.cache.set(cache_key, summaries, ttl=self.metadata_ttl)
        return summaries

    def get_track_stream(self, provider_track_id: str) -> PlaybackInfo:
        """Resolve a fresh, time-limited Mubert generative stream link for a playlist/channel index."""
        self._require_configured()
        if not self._license_verified:
            self.verify_license()

        channel_index = str(provider_track_id).strip()
        payload = self.http_client.request_json(
            "POST",
            f"{self.base_url}/public/streaming/get-link",
            headers=self._ensure_customer_headers(),
            json_body={
                "playlist_index": channel_index,
                "bitrate": 128,
                "intensity": "medium",
            },
        ) or {}
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        stream_url = (data.get("link") or data.get("url") or "").strip() or None
        ttl_seconds = int(data.get("expires_in") or self.default_stream_ttl_seconds)
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        ).isoformat()

        licensing = build_mubert_licensing(
            title=f"Mubert Channel {channel_index}",
            b2b_license_verified=self._license_verified,
            plan_name=self._verified_plan_name,
        )

        return PlaybackInfo(
            internal_id=make_internal_track_id(self.name, channel_index),
            provider=self.name,
            provider_track_id=channel_index,
            playback_url=stream_url,
            playback_reference=channel_index,
            playback_type=licensing.permitted_playback_type,
            expires_at=expires_at if stream_url else None,
            is_playable=bool(stream_url and self._license_verified),
            licensing=licensing,
            attribution_text=licensing.attribution_text,
            refresh_supported=True,
        )

    def get_recommendations(
        self,
        *,
        mood_tags: Optional[List[str]] = None,
        genres: Optional[List[str]] = None,
        bpm_range: Optional[tuple[float, float]] = None,
        target_energy: Optional[float] = None,
        language: Optional[str] = None,
        limit: int = 10,
    ) -> List[UnifiedTrack]:
        self._require_configured()
        if not self._license_verified:
            self.verify_license()

        primary_mood = (mood_tags or [None])[0]
        channels = self.get_playlists(mood=primary_mood, limit=min(limit, 5))
        if not channels:
            channels = self.get_playlists(limit=min(limit, 5))

        tracks: List[UnifiedTrack] = []
        for channel in channels:
            licensing = build_mubert_licensing(
                title=channel.name,
                b2b_license_verified=self._license_verified,
                plan_name=self._verified_plan_name,
            )
            tracks.append(
                UnifiedTrack(
                    internal_id=make_internal_track_id(self.name, channel.provider_playlist_id),
                    provider=self.name,
                    provider_track_id=channel.provider_playlist_id,
                    title=channel.name,
                    artist="Mubert Generative AI",
                    album="Mubert Stream Channels",
                    genre=(genres[0].lower() if genres else "electronic"),
                    duration=None,
                    bpm=None,
                    energy=target_energy,
                    mood_tags=list(dict.fromkeys((channel.tags or []) + (mood_tags or []))),
                    language=None,
                    artwork=channel.artwork,
                    preview_url=None,
                    playback_url=None,  # Resolved lazily on demand via get_track_stream() so URLs don't expire unused
                    playback_reference=channel.provider_playlist_id,
                    playback_expires_at=None,
                    is_available=self._license_verified,
                    licensing=licensing,
                    provider_metadata={
                        "playlist_index": channel.provider_playlist_id,
                        "generative_stream": True,
                        "plan": self._verified_plan_name,
                    },
                )
            )
        return tracks

    def get_provider_status(self, force_refresh: bool = False) -> ProviderStatus:
        licensing_notes = (
            "Mubert API v3 requires a paid commercial/API license (MUBERT_COMPANY_ID + MUBERT_LICENSE_TOKEN). "
            "DSP uploads, Content ID registration, and stock resale are prohibited on all plans."
        )
        if not self.enabled:
            return ProviderStatus(
                provider=self.name,
                configured=False,
                healthy=False,
                status="unconfigured",
                message="Mubert provider is disabled via configuration.",
                capabilities=self.capabilities,
                licensing_notes=licensing_notes,
            )
        if not (self.company_id and self.license_token):
            return ProviderStatus(
                provider=self.name,
                configured=False,
                healthy=False,
                status="unconfigured",
                message="Optional provider not configured (set MUBERT_COMPANY_ID and MUBERT_LICENSE_TOKEN when licensed).",
                capabilities=self.capabilities,
                licensing_notes=licensing_notes,
            )

        cache_key = "mubert:health"
        if not force_refresh:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached

        started = time.monotonic()
        try:
            lic_info = self.verify_license()
            latency_ms = round((time.monotonic() - started) * 1000.0, 2)
            healthy = bool(lic_info["verified"])
            status = ProviderStatus(
                provider=self.name,
                configured=True,
                healthy=healthy,
                status="healthy" if healthy else "degraded",
                message=(
                    f"Mubert API v3 active license verified ({lic_info['plan']})."
                    if healthy
                    else "Mubert credentials connected, but no active commercial license found."
                ),
                capabilities=self.capabilities,
                latency_ms=latency_ms,
                licensing_notes=licensing_notes,
            )
        except Exception as exc:
            latency_ms = round((time.monotonic() - started) * 1000.0, 2)
            status = ProviderStatus(
                provider=self.name,
                configured=True,
                healthy=False,
                status="unavailable",
                message=str(exc),
                capabilities=self.capabilities,
                latency_ms=latency_ms,
                licensing_notes=licensing_notes,
            )

        self.cache.set(cache_key, status, ttl=self.health_ttl)
        return status
