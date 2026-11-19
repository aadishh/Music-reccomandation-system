"""Abstract base class for pluggable music API providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from music.cache import MetadataTTLCache
from music.exceptions import UnsupportedOperationError
from music.http_client import ResilientHTTPClient
from music.models import (
    PlaybackInfo,
    PlaylistSummary,
    ProviderCapabilities,
    ProviderStatus,
    UnifiedTrack,
)


class BaseMusicProvider(ABC):
    """Standard interface for all music providers.

    Providers must declare capabilities explicitly and raise UnsupportedOperationError
    for methods not supported by their upstream API.
    """

    name: str = "base"

    def __init__(
        self,
        *,
        enabled: bool = True,
        http_client: Optional[ResilientHTTPClient] = None,
        cache: Optional[MetadataTTLCache] = None,
        metadata_ttl: int = 300,
        health_ttl: int = 60,
    ) -> None:
        self.enabled = enabled
        self.http_client = http_client or ResilientHTTPClient(provider_name=self.name)
        self.cache = cache or MetadataTTLCache(default_ttl=metadata_ttl)
        self.metadata_ttl = metadata_ttl
        self.health_ttl = health_ttl

    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """Return declared capabilities for this provider."""

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Return True when the provider is enabled and has required credentials."""

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
            f"Provider '{self.name}' does not support track search.",
            provider=self.name,
        )

    def get_track_details(self, provider_track_id: str) -> UnifiedTrack:
        raise UnsupportedOperationError(
            f"Provider '{self.name}' does not support fetching individual track details.",
            provider=self.name,
        )

    def get_track_stream(self, provider_track_id: str) -> PlaybackInfo:
        raise UnsupportedOperationError(
            f"Provider '{self.name}' does not support resolving track playback streams.",
            provider=self.name,
        )

    def get_playlists(
        self,
        *,
        query: Optional[str] = None,
        mood: Optional[str] = None,
        limit: int = 10,
    ) -> List[PlaylistSummary]:
        raise UnsupportedOperationError(
            f"Provider '{self.name}' does not support playlist listing.",
            provider=self.name,
        )

    def get_recommendations(
        self,
        *,
        mood_tags: Optional[List[str]] = None,
        genres: Optional[List[str]] = None,
        bpm_range: Optional[tuple[float, float]] = None,
        target_energy: Optional[float] = None,
        language: Optional[str] = None,
        limit: int = 20,
    ) -> List[UnifiedTrack]:
        raise UnsupportedOperationError(
            f"Provider '{self.name}' does not support recommendations.",
            provider=self.name,
        )

    @abstractmethod
    def get_provider_status(self, force_refresh: bool = False) -> ProviderStatus:
        """Return current configuration, health, latency, and licensing summary."""

    def normalize_track(self, raw_track: Dict[str, Any]) -> UnifiedTrack:
        """Normalize a raw upstream track payload into UnifiedTrack."""
        raise UnsupportedOperationError(
            f"Provider '{self.name}' does not implement raw track normalization.",
            provider=self.name,
        )
