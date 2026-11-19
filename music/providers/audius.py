"""Audius REST API v1 provider integration.

Verified endpoints (https://api.audius.co/v1):
- GET /v1/tracks/search
- GET /v1/tracks/{track_id}
- GET /v1/tracks/{track_id}/stream
- GET /v1/tracks/trending
- GET /v1/playlists/trending
- GET /v1/playlists/search

Licensing & Access notes:
- Public read operations support `app_name` and optional Bearer API key (`AUDIUS_API_KEY`) for higher rate limits.
- Respects `is_streamable`, `is_unlisted`, `stream_conditions` (gated tracks), and artist-configured `license`.
- Never bypasses gated `stream_conditions` or caches/proxies audio bytes.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from music.cache import MetadataTTLCache
from music.exceptions import (
    LicensingViolationError,
    MusicProviderError,
    ProviderConfigError,
    TrackNotFoundError,
)
from music.http_client import ResilientHTTPClient
from music.licensing import build_audius_licensing
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

# Mood -> estimated energy heuristic when only mood + bpm are available
AUDIUS_MOOD_ENERGY = {
    "peaceful": 0.25,
    "melancholy": 0.28,
    "sad": 0.25,
    "tender": 0.32,
    "easygoing": 0.42,
    "chill": 0.35,
    "romantic": 0.40,
    "cool": 0.50,
    "sophisticated": 0.48,
    "yearning": 0.45,
    "sentimental": 0.35,
    "brooding": 0.45,
    "serious": 0.50,
    "gritty": 0.68,
    "stirring": 0.62,
    "upbeat": 0.78,
    "empowering": 0.76,
    "excited": 0.85,
    "energizing": 0.88,
    "rowdy": 0.88,
    "fiery": 0.90,
    "aggressive": 0.92,
    "defiant": 0.82,
    "lively": 0.80,
}


class AudiusProvider(BaseMusicProvider):
    """Audius REST API v1 implementation."""

    name = "audius"

    def __init__(
        self,
        *,
        api_key: str = "",
        app_name: str = "EmotionMusicRecommender",
        base_url: str = "https://api.audius.co/v1",
        oml_commercial_verified: bool = False,
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
        self.api_key = api_key.strip()
        self.app_name = app_name.strip() or "EmotionMusicRecommender"
        self.base_url = base_url.rstrip("/")
        self.oml_commercial_verified = bool(oml_commercial_verified)

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            search_tracks=True,
            get_track_details=True,
            get_track_stream=True,
            get_playlists=True,
            get_recommendations=True,
            commercial_tier_available=True,
            requires_paid_plan_for_commercial=False,  # Depends on per-track CC/OML license terms
        )

    @property
    def is_configured(self) -> bool:
        # Audius public read API works with app_name; AUDIUS_API_KEY adds higher developer quota
        return bool(self.enabled)

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise ProviderConfigError("Audius provider is disabled.", provider=self.name)

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _request_audius(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        allow_404_none: bool = False,
    ) -> Optional[Dict[str, Any]]:
        self._require_enabled()
        query_params = {"app_name": self.app_name, **(params or {})}
        payload = self.http_client.request_json(
            "GET",
            f"{self.base_url}/{path.lstrip('/')}",
            params=query_params,
            headers=self._headers(),
            allow_404_none=allow_404_none,
        )
        if payload is None:
            return None
        if not isinstance(payload, dict):
            raise MusicProviderError("Unexpected Audius response format", provider=self.name)
        return payload

    def _build_stream_url(self, provider_track_id: str) -> str:
        # Never embed private API keys in browser-facing stream URLs; include app_name only.
        query = urlencode({"app_name": self.app_name})
        return f"{self.base_url}/tracks/{provider_track_id}/stream?{query}"

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
        self._require_enabled()
        limit = max(1, min(int(limit), 50))
        offset = max(0, int(offset))

        cache_key = f"audius:search:{query}:{genre}:{mood}:{limit}:{offset}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        search_query = " ".join(part for part in [query.strip(), mood or "", genre or ""] if part).strip()
        if not search_query:
            params: Dict[str, Any] = {"limit": limit}
            if genre:
                params["genre"] = genre
            payload = self._request_audius("tracks/trending", params) or {}
        else:
            params = {"query": search_query, "limit": limit, "offset": offset}
            if genre:
                params["genre"] = genre
            if mood:
                params["mood"] = mood
            payload = self._request_audius("tracks/search", params) or {}

        raw_tracks = payload.get("data") or []
        tracks = [self.normalize_track(item) for item in raw_tracks if isinstance(item, dict)]
        self.cache.set(cache_key, tracks, ttl=self.metadata_ttl)
        return tracks

    def get_track_details(self, provider_track_id: str) -> UnifiedTrack:
        self._require_enabled()
        track_id = str(provider_track_id).strip()
        cache_key = f"audius:track:{track_id}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        payload = self._request_audius(f"tracks/{track_id}", allow_404_none=True)
        raw_track = (payload or {}).get("data")
        if not isinstance(raw_track, dict):
            raise TrackNotFoundError(
                f"Audius track '{track_id}' not found.",
                provider=self.name,
            )

        track = self.normalize_track(raw_track)
        self.cache.set(cache_key, track, ttl=self.metadata_ttl)
        return track

    def get_track_stream(self, provider_track_id: str) -> PlaybackInfo:
        self._require_enabled()
        track_id = str(provider_track_id).strip()

        # Fetch fresh track metadata to verify is_streamable and stream_conditions
        payload = self._request_audius(f"tracks/{track_id}", allow_404_none=True)
        raw_track = (payload or {}).get("data")
        if not isinstance(raw_track, dict):
            raise TrackNotFoundError(
                f"Audius track '{track_id}' not found.",
                provider=self.name,
            )
        track = self.normalize_track(raw_track)

        if not track.is_available or track.licensing.permitted_playback_type == "none":
            raise LicensingViolationError(
                track.licensing.restriction_reason or "Track is not streamable on Audius.",
                provider=self.name,
                reason=track.licensing.restriction_reason,
            )

        stream_endpoint = self._build_stream_url(track_id)
        resolved_url = stream_endpoint
        # Attempt lightweight HEAD check to resolve redirect target cleanly without downloading bytes
        try:
            status_code, location = self.http_client.resolve_redirect_url(
                f"{self.base_url}/tracks/{track_id}/stream",
                params={"app_name": self.app_name},
                headers=self._headers(),
            )
            if status_code in (301, 302, 303, 307, 308) and location:
                resolved_url = location
            elif status_code in (401, 403, 404):
                raise LicensingViolationError(
                    f"Audius stream endpoint declined playback (HTTP {status_code}).",
                    provider=self.name,
                )
        except LicensingViolationError:
            raise
        except MusicProviderError as exc:
            logger.debug("Audius HEAD check fallback to direct stream endpoint: %s", exc)

        return PlaybackInfo(
            internal_id=track.internal_id,
            provider=self.name,
            provider_track_id=track.provider_track_id,
            playback_url=resolved_url,
            playback_reference=stream_endpoint,
            playback_type=track.licensing.permitted_playback_type,
            expires_at=None,
            is_playable=True,
            licensing=track.licensing,
            attribution_text=track.licensing.attribution_text,
            refresh_supported=True,
        )

    def get_playlists(
        self,
        *,
        query: Optional[str] = None,
        mood: Optional[str] = None,
        limit: int = 10,
    ) -> List[PlaylistSummary]:
        self._require_enabled()
        limit = max(1, min(int(limit), 30))
        cache_key = f"audius:playlists:{query}:{mood}:{limit}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        search_term = query or mood
        if search_term:
            payload = self._request_audius("playlists/search", {"query": search_term, "limit": limit}) or {}
        else:
            payload = self._request_audius("playlists/trending", {"limit": limit}) or {}

        summaries: List[PlaylistSummary] = []
        for item in payload.get("data") or []:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            pid = str(item["id"])
            artwork_obj = item.get("artwork") if isinstance(item.get("artwork"), dict) else {}
            artwork = artwork_obj.get("480x480") or artwork_obj.get("150x150") or artwork_obj.get("1000x1000")
            summaries.append(
                PlaylistSummary(
                    internal_id=make_internal_track_id(self.name, pid),
                    provider=self.name,
                    provider_playlist_id=pid,
                    name=str(item.get("playlist_name") or "Untitled Playlist"),
                    description=item.get("description"),
                    artwork=artwork,
                    track_count=item.get("track_count"),
                    tags=[mood] if mood else [],
                    provider_metadata={
                        "permalink": item.get("permalink"),
                        "is_album": item.get("is_album"),
                        "favorite_count": item.get("favorite_count"),
                    },
                )
            )
        self.cache.set(cache_key, summaries, ttl=self.metadata_ttl)
        return summaries

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
        self._require_enabled()
        limit = max(1, min(int(limit), 50))
        mood_list = [m.strip() for m in (mood_tags or []) if m and m.strip()]
        genre_list = [g.strip() for g in (genres or []) if g and g.strip()]

        cache_key = f"audius:recs:{mood_list}:{genre_list}:{bpm_range}:{limit}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        collected: Dict[str, UnifiedTrack] = {}

        # 1. Search by primary mood / genre if provided
        if mood_list or genre_list:
            query = " ".join((mood_list[:2] + genre_list[:2]))
            search_params: Dict[str, Any] = {"query": query, "limit": limit}
            if genre_list:
                search_params["genre"] = genre_list[0].title()
            if mood_list:
                search_params["mood"] = mood_list[0].title()
            if bpm_range:
                search_params["bpm_min"] = int(bpm_range[0])
                search_params["bpm_max"] = int(bpm_range[1])

            payload = self._request_audius("tracks/search", search_params) or {}
            for item in payload.get("data") or []:
                if isinstance(item, dict):
                    track = self.normalize_track(item)
                    collected[track.internal_id] = track

        # 2. Supplement from trending tracks when search yields fewer items than requested
        if len(collected) < limit:
            trending_params: Dict[str, Any] = {"limit": limit}
            if genre_list:
                trending_params["genre"] = genre_list[0].title()
            payload = self._request_audius("tracks/trending", trending_params) or {}
            for item in payload.get("data") or []:
                if isinstance(item, dict):
                    track = self.normalize_track(item)
                    collected.setdefault(track.internal_id, track)

        tracks = list(collected.values())[:limit]
        self.cache.set(cache_key, tracks, ttl=self.metadata_ttl)
        return tracks

    def get_provider_status(self, force_refresh: bool = False) -> ProviderStatus:
        licensing_notes = (
            "Audius tracks carry creator-selected licenses (All Rights Reserved, Creative Commons, or "
            "Open Music License) plus is_streamable and stream_conditions flags. Gated and non-commercial "
            "tracks are enforced strictly."
        )
        if not self.enabled:
            return ProviderStatus(
                provider=self.name,
                configured=False,
                healthy=False,
                status="unconfigured",
                message="Audius provider is disabled via configuration.",
                capabilities=self.capabilities,
                licensing_notes=licensing_notes,
            )

        cache_key = "audius:health"
        if not force_refresh:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached

        started = time.monotonic()
        try:
            self._request_audius("tracks/trending", {"limit": 1})
            latency_ms = round((time.monotonic() - started) * 1000.0, 2)
            key_note = "authenticated with API key" if self.api_key else "public read mode (set AUDIUS_API_KEY for higher quota)"
            status = ProviderStatus(
                provider=self.name,
                configured=True,
                healthy=True,
                status="healthy",
                message=f"Audius REST API v1 is healthy ({key_note}).",
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

    def normalize_track(self, raw_track: Dict[str, Any]) -> UnifiedTrack:
        provider_track_id = str(raw_track.get("id") or "").strip()
        title = str(raw_track.get("title") or "Untitled Track").strip()
        user_obj = raw_track.get("user") if isinstance(raw_track.get("user"), dict) else {}
        artist = str(user_obj.get("name") or user_obj.get("handle") or "Unknown Artist").strip()
        genre = (raw_track.get("genre") or "").strip() or None
        mood = (raw_track.get("mood") or "").strip() or None

        duration_raw = raw_track.get("duration")
        duration = int(duration_raw) if isinstance(duration_raw, (int, float)) else None

        bpm_raw = raw_track.get("bpm")
        bpm = float(bpm_raw) if isinstance(bpm_raw, (int, float)) and bpm_raw > 0 else None

        energy = self._estimate_energy(mood=mood, bpm=bpm)

        tags_raw = raw_track.get("tags") or ""
        parsed_tags: List[str] = []
        if isinstance(tags_raw, str):
            parsed_tags = [t.strip().lower() for t in tags_raw.split(",") if t.strip()]
        elif isinstance(tags_raw, list):
            parsed_tags = [str(t).strip().lower() for t in tags_raw if t]

        mood_tags: List[str] = []
        if mood:
            mood_tags.append(mood.lower())
        if genre:
            mood_tags.append(genre.lower())
        mood_tags.extend(parsed_tags)
        mood_tags = list(dict.fromkeys(mood_tags))

        artwork_obj = raw_track.get("artwork") if isinstance(raw_track.get("artwork"), dict) else {}
        artwork = (
            artwork_obj.get("480x480")
            or artwork_obj.get("150x150")
            or artwork_obj.get("1000x1000")
            or (raw_track.get("artwork") if isinstance(raw_track.get("artwork"), str) else None)
        )

        is_streamable = bool(raw_track.get("is_streamable", True))
        stream_conditions = raw_track.get("stream_conditions")
        is_unlisted = bool(raw_track.get("is_unlisted", False))
        license_str = raw_track.get("license")

        licensing = build_audius_licensing(
            title=title,
            artist=artist,
            license_str=license_str,
            is_streamable=is_streamable,
            stream_conditions=stream_conditions if isinstance(stream_conditions, dict) and stream_conditions else None,
            is_unlisted=is_unlisted,
            oml_commercial_verified=self.oml_commercial_verified,
        )

        available = bool(
            provider_track_id
            and is_streamable
            and not is_unlisted
            and not (isinstance(stream_conditions, dict) and bool(stream_conditions))
        )
        stream_url = self._build_stream_url(provider_track_id) if available else None

        return UnifiedTrack(
            internal_id=make_internal_track_id(self.name, provider_track_id),
            provider=self.name,
            provider_track_id=provider_track_id,
            title=title,
            artist=artist,
            album=None,
            genre=genre.lower() if genre else None,
            duration=duration,
            bpm=bpm,
            energy=energy,
            mood_tags=mood_tags,
            language=None,
            artwork=artwork,
            preview_url=stream_url,
            playback_url=stream_url,
            playback_reference=raw_track.get("permalink") or stream_url,
            playback_expires_at=None,
            is_available=available,
            licensing=licensing,
            provider_metadata={
                "audius_user_id": user_obj.get("id"),
                "audius_handle": user_obj.get("handle"),
                "permalink": raw_track.get("permalink"),
                "play_count": raw_track.get("play_count"),
                "favorite_count": raw_track.get("favorite_count"),
                "repost_count": raw_track.get("repost_count"),
                "is_streamable": is_streamable,
                "is_unlisted": is_unlisted,
                "stream_conditions": stream_conditions,
                "raw_license": license_str,
                "musical_key": raw_track.get("musical_key"),
            },
        )

    @staticmethod
    def _estimate_energy(*, mood: Optional[str], bpm: Optional[float]) -> Optional[float]:
        scores: List[float] = []
        if mood and mood.strip().lower() in AUDIUS_MOOD_ENERGY:
            scores.append(AUDIUS_MOOD_ENERGY[mood.strip().lower()])
        if bpm is not None and bpm > 0:
            # Map typical 60-170 BPM range to 0.15 - 0.95
            bpm_energy = max(0.15, min(0.95, (bpm - 50.0) / 120.0))
            scores.append(bpm_energy)
        if not scores:
            return None
        return round(sum(scores) / len(scores), 3)
