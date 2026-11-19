"""Provider registry with graceful fallback, licensing enforcement, and health reporting."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from music.cache import MetadataTTLCache
from music.exceptions import (
    LicensingViolationError,
    MusicProviderError,
    ProviderConfigError,
    ProviderUnavailableError,
    StreamExpiredError,
    TrackNotFoundError,
    UnsupportedOperationError,
)
from music.http_client import ResilientHTTPClient
from music.licensing import LicensingValidator
from music.models import (
    DeploymentMode,
    PlaybackInfo,
    PlaylistSummary,
    ProviderStatus,
    UnifiedTrack,
    parse_internal_track_id,
)
from music.providers.audius import AudiusProvider
from music.providers.base import BaseMusicProvider
from music.providers.jamendo import JamendoProvider
from music.providers.mubert import MubertProvider

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """Manages registered music providers and coordinates cross-provider fallback."""

    def __init__(
        self,
        providers: Optional[Dict[str, BaseMusicProvider]] = None,
        licensing_validator: Optional[LicensingValidator] = None,
    ) -> None:
        self._providers: Dict[str, BaseMusicProvider] = {}
        self.licensing_validator = licensing_validator or LicensingValidator(
            DeploymentMode.NON_COMMERCIAL.value
        )
        if providers:
            for provider in providers.values():
                self.register(provider)

    @classmethod
    def from_config(
        cls,
        provider_config: Dict[str, Any],
        http_settings: Dict[str, Any],
        cache_settings: Dict[str, Any],
        deployment_mode: str = DeploymentMode.NON_COMMERCIAL.value,
    ) -> "ProviderRegistry":
        shared_cache = MetadataTTLCache(
            default_ttl=cache_settings.get("metadata_ttl_seconds", 300),
            max_entries=cache_settings.get("max_entries", 1024),
        )
        metadata_ttl = cache_settings.get("metadata_ttl_seconds", 300)
        health_ttl = cache_settings.get("health_ttl_seconds", 60)

        def make_http(name: str) -> ResilientHTTPClient:
            return ResilientHTTPClient(
                provider_name=name,
                connect_timeout=http_settings.get("connect_timeout", 5.0),
                read_timeout=http_settings.get("read_timeout", 10.0),
                max_retries=http_settings.get("max_retries", 2),
                backoff_base_seconds=http_settings.get("backoff_base_seconds", 0.5),
                max_retry_after_seconds=http_settings.get("max_retry_after_seconds", 5.0),
            )

        jam_cfg = provider_config.get("jamendo", {})
        aud_cfg = provider_config.get("audius", {})
        mub_cfg = provider_config.get("mubert", {})

        registry = cls(
            licensing_validator=LicensingValidator(deployment_mode=deployment_mode)
        )
        registry.register(
            JamendoProvider(
                client_id=jam_cfg.get("client_id", ""),
                base_url=jam_cfg.get("base_url", "https://api.jamendo.com/v3.0"),
                audio_format=jam_cfg.get("audio_format", "mp32"),
                commercial_agreement_verified=jam_cfg.get("commercial_agreement_verified", False),
                enabled=jam_cfg.get("enabled", True),
                http_client=make_http("jamendo"),
                cache=shared_cache,
                metadata_ttl=metadata_ttl,
                health_ttl=health_ttl,
            )
        )
        registry.register(
            AudiusProvider(
                api_key=aud_cfg.get("api_key", ""),
                app_name=aud_cfg.get("app_name", "EmotionMusicRecommender"),
                base_url=aud_cfg.get("base_url", "https://api.audius.co/v1"),
                oml_commercial_verified=aud_cfg.get("oml_commercial_verified", False),
                enabled=aud_cfg.get("enabled", True),
                http_client=make_http("audius"),
                cache=shared_cache,
                metadata_ttl=metadata_ttl,
                health_ttl=health_ttl,
            )
        )
        registry.register(
            MubertProvider(
                company_id=mub_cfg.get("company_id", ""),
                license_token=mub_cfg.get("license_token", ""),
                base_url=mub_cfg.get("base_url", "https://music-api.mubert.com/api/v3"),
                stream_base_url=mub_cfg.get("stream_base_url", "https://stream.mubert.com/b2b/v3"),
                default_stream_ttl_seconds=mub_cfg.get("default_stream_ttl_seconds", 900),
                enabled=mub_cfg.get("enabled", True),
                http_client=make_http("mubert"),
                cache=shared_cache,
                metadata_ttl=metadata_ttl,
                health_ttl=health_ttl,
            )
        )
        return registry

    def register(self, provider: BaseMusicProvider) -> None:
        self._providers[provider.name.lower()] = provider

    def unregister(self, name: str) -> None:
        self._providers.pop(name.lower(), None)

    def get_provider(self, name: str) -> BaseMusicProvider:
        key = name.strip().lower()
        provider = self._providers.get(key)
        if provider is None:
            raise TrackNotFoundError(f"Unknown music provider '{name}'.")
        return provider

    def list_provider_names(self) -> List[str]:
        return list(self._providers.keys())

    def get_configured_providers(
        self, requested: Optional[List[str]] = None
    ) -> List[BaseMusicProvider]:
        if requested:
            selected: List[BaseMusicProvider] = []
            for name in requested:
                prov = self._providers.get(name.strip().lower())
                if prov and prov.is_configured:
                    selected.append(prov)
            return selected
        return [p for p in self._providers.values() if p.is_configured]

    def get_all_provider_statuses(self, force_refresh: bool = False) -> List[ProviderStatus]:
        statuses: List[ProviderStatus] = []
        for provider in self._providers.values():
            statuses.append(provider.get_provider_status(force_refresh=force_refresh))
        return statuses

    def search_tracks(
        self,
        query: str = "",
        *,
        providers: Optional[List[str]] = None,
        genre: Optional[str] = None,
        mood: Optional[str] = None,
        language: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        only_playable: bool = True,
    ) -> Tuple[List[UnifiedTrack], List[Dict[str, Any]]]:
        """Search across configured providers with graceful per-provider fallback."""
        target_providers = self.get_configured_providers(providers)
        results: List[UnifiedTrack] = []
        provider_errors: List[Dict[str, Any]] = []

        if not target_providers:
            return [], [{"provider": "all", "error": "No music providers are currently configured."}]

        per_provider_limit = max(5, limit)
        for provider in target_providers:
            if not provider.capabilities.search_tracks:
                if providers:
                    provider_errors.append(
                        {
                            "provider": provider.name,
                            "code": "unsupported_operation",
                            "error": f"Provider '{provider.name}' does not support catalog track search.",
                        }
                    )
                continue
            try:
                tracks = provider.search_tracks(
                    query=query,
                    genre=genre,
                    mood=mood,
                    language=language,
                    limit=per_provider_limit,
                    offset=offset,
                )
                for track in tracks:
                    if only_playable:
                        allowed, _ = self.licensing_validator.is_playable(track)
                        if not allowed:
                            continue
                    results.append(track)
            except (UnsupportedOperationError, ProviderConfigError, MusicProviderError) as exc:
                logger.warning("Search failed on provider '%s': %s", provider.name, exc)
                provider_errors.append(
                    {
                        "provider": provider.name,
                        "code": exc.code,
                        "error": exc.message,
                    }
                )
            except Exception as exc:
                logger.exception("Unexpected search failure on provider '%s'", provider.name)
                provider_errors.append(
                    {
                        "provider": provider.name,
                        "code": "unexpected_error",
                        "error": str(exc),
                    }
                )

        # Interleave results across providers for diversity while respecting limit
        deduped: Dict[str, UnifiedTrack] = {}
        for track in results:
            deduped.setdefault(track.internal_id, track)
        return list(deduped.values())[:limit], provider_errors

    def get_track_details(self, internal_track_id: str) -> UnifiedTrack:
        provider_name, provider_track_id = parse_internal_track_id(internal_track_id)
        provider = self.get_provider(provider_name)
        return provider.get_track_details(provider_track_id)

    def get_playback_info(
        self,
        internal_track_id: str,
        *,
        refresh: bool = False,
    ) -> PlaybackInfo:
        """Resolve an authorized playback URL and enforce licensing compliance."""
        provider_name, provider_track_id = parse_internal_track_id(internal_track_id)
        provider = self.get_provider(provider_name)

        playback = provider.get_track_stream(provider_track_id)

        # Verify stream is not already expired; if expired and refresh requested, re-resolve once
        if playback.is_expired():
            if refresh and playback.refresh_supported:
                playback = provider.get_track_stream(provider_track_id)
            if playback.is_expired():
                raise StreamExpiredError(
                    f"Playback URL for '{internal_track_id}' has expired.",
                    provider=provider.name,
                )

        # Enforce licensing policy before returning stream URL to client
        probe_track = UnifiedTrack(
            internal_id=playback.internal_id,
            provider=playback.provider,
            provider_track_id=playback.provider_track_id,
            title="",
            artist="",
            playback_url=playback.playback_url,
            playback_reference=playback.playback_reference,
            playback_expires_at=playback.expires_at,
            is_available=playback.is_playable,
            licensing=playback.licensing,
        )
        self.licensing_validator.enforce_playback(probe_track)
        return playback

    def get_playlists(
        self,
        *,
        providers: Optional[List[str]] = None,
        query: Optional[str] = None,
        mood: Optional[str] = None,
        limit: int = 10,
    ) -> Tuple[List[PlaylistSummary], List[Dict[str, Any]]]:
        target_providers = self.get_configured_providers(providers)
        playlists: List[PlaylistSummary] = []
        errors: List[Dict[str, Any]] = []
        for provider in target_providers:
            if not provider.capabilities.get_playlists:
                continue
            try:
                playlists.extend(provider.get_playlists(query=query, mood=mood, limit=limit))
            except MusicProviderError as exc:
                logger.warning("Playlist fetch failed on '%s': %s", provider.name, exc)
                errors.append({"provider": provider.name, "code": exc.code, "error": exc.message})
        return playlists[:limit], errors

    def gather_recommendation_candidates(
        self,
        *,
        mood_tags: List[str],
        genres: List[str],
        bpm_range: Optional[Tuple[float, float]] = None,
        target_energy: Optional[float] = None,
        language: Optional[str] = None,
        providers: Optional[List[str]] = None,
        per_provider_limit: int = 20,
    ) -> Tuple[List[UnifiedTrack], List[Dict[str, Any]]]:
        """Gather candidate tracks from all eligible providers with graceful fallback."""
        target_providers = self.get_configured_providers(providers)
        candidates: Dict[str, UnifiedTrack] = {}
        errors: List[Dict[str, Any]] = []

        if not target_providers:
            return [], [{"provider": "all", "code": "no_providers", "error": "No configured music providers."}]

        for provider in target_providers:
            if not provider.capabilities.get_recommendations:
                continue
            try:
                tracks = provider.get_recommendations(
                    mood_tags=mood_tags,
                    genres=genres,
                    bpm_range=bpm_range,
                    target_energy=target_energy,
                    language=language,
                    limit=per_provider_limit,
                )
                for track in tracks:
                    # Strictly exclude unavailable or licensing-blocked tracks from recommendations
                    allowed, _ = self.licensing_validator.is_playable(track)
                    if not allowed:
                        continue
                    candidates.setdefault(track.internal_id, track)
            except (ProviderUnavailableError, MusicProviderError) as exc:
                logger.warning("Recommendation candidate fetch failed on '%s': %s", provider.name, exc)
                errors.append({"provider": provider.name, "code": exc.code, "error": exc.message})
            except Exception as exc:
                logger.exception("Unexpected error gathering candidates from '%s'", provider.name)
                errors.append({"provider": provider.name, "code": "unexpected_error", "error": str(exc)})

        return list(candidates.values()), errors
