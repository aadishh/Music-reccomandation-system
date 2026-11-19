"""Jamendo API v3.0 provider integration.

Verified endpoints:
- GET /v3.0/tracks/ (search, fuzzytags, tags, speed, include=musicinfo+licenses+stats, audioformat=mp32)
- GET /v3.0/playlists/
- GET /v3.0/playlists/tracks/

Licensing notes:
- Free Jamendo API tier (35,000 requests/month) is restricted to non-commercial applications.
- Individual tracks carry Creative Commons licenses (license_ccurl) and optional Jamendo Pro info (prourl).
- Commercial streaming requires an approved Jamendo Licensing / Pro commercial agreement.
- Audio streams must be played directly from Jamendo's CDN URL; caching/redistributing audio is prohibited.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from music.cache import MetadataTTLCache
from music.exceptions import (
    MusicProviderError,
    ProviderAuthError,
    ProviderConfigError,
    ProviderRateLimitError,
    TrackNotFoundError,
)
from music.http_client import ResilientHTTPClient
from music.licensing import build_jamendo_licensing
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

# Jamendo speed enum -> estimated energy & midpoint BPM for scoring when explicit BPM is absent
JAMENDO_SPEED_PROFILE = {
    "verylow": (0.20, 68.0),
    "low": (0.38, 86.0),
    "medium": (0.58, 108.0),
    "high": (0.78, 128.0),
    "veryhigh": (0.93, 148.0),
}


class JamendoProvider(BaseMusicProvider):
    """Jamendo API v3.0 implementation."""

    name = "jamendo"

    def __init__(
        self,
        *,
        client_id: str = "",
        base_url: str = "https://api.jamendo.com/v3.0",
        audio_format: str = "mp32",
        commercial_agreement_verified: bool = False,
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
        self.client_id = client_id.strip()
        self.base_url = base_url.rstrip("/")
        self.audio_format = audio_format or "mp32"
        self.commercial_agreement_verified = bool(commercial_agreement_verified)

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            search_tracks=True,
            get_track_details=True,
            get_track_stream=True,
            get_playlists=True,
            get_recommendations=True,
            commercial_tier_available=True,
            requires_paid_plan_for_commercial=True,
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.enabled and self.client_id)

    def _require_configured(self) -> None:
        if not self.enabled:
            raise ProviderConfigError("Jamendo provider is disabled.", provider=self.name)
        if not self.client_id:
            raise ProviderConfigError(
                "JAMENDO_CLIENT_ID is not configured.",
                provider=self.name,
            )

    def _request_jamendo(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        self._require_configured()
        query_params = {
            "client_id": self.client_id,
            "format": "json",
            **params,
        }
        payload = self.http_client.request_json(
            "GET",
            f"{self.base_url}/{path.lstrip('/')}",
            params=query_params,
        )
        if not isinstance(payload, dict):
            raise MusicProviderError("Unexpected Jamendo response format", provider=self.name)

        headers = payload.get("headers") or {}
        if headers.get("status") == "failed":
            code = headers.get("code")
            error_msg = headers.get("error_message") or "Jamendo API error"
            if code in (4, 5, 13):  # Invalid client_id / auth errors in Jamendo v3.0
                raise ProviderAuthError(f"Jamendo auth error ({code}): {error_msg}", provider=self.name)
            if code in (12, 22):  # Rate limit / quota exceeded
                raise ProviderRateLimitError(f"Jamendo quota/rate limit ({code}): {error_msg}", provider=self.name)
            raise MusicProviderError(f"Jamendo error ({code}): {error_msg}", provider=self.name)

        return payload

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
        self._require_configured()
        limit = max(1, min(int(limit), 50))
        offset = max(0, int(offset))

        cache_key = f"jamendo:search:{query}:{genre}:{mood}:{language}:{limit}:{offset}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        params: Dict[str, Any] = {
            "limit": limit,
            "offset": offset,
            "include": "musicinfo+licenses+stats",
            "audioformat": self.audio_format,
            "order": "popularity_week",
        }
        if query:
            params["search"] = query.strip()

        fuzzy_terms: List[str] = []
        if genre:
            fuzzy_terms.append(genre.strip().lower())
        if mood:
            fuzzy_terms.append(mood.strip().lower())
        if fuzzy_terms:
            params["fuzzytags"] = "+".join(fuzzy_terms)

        if language:
            params["lang"] = language.strip().lower()[:2]

        payload = self._request_jamendo("tracks/", params)
        results = payload.get("results") or []
        tracks = [self.normalize_track(item) for item in results if isinstance(item, dict)]
        self.cache.set(cache_key, tracks, ttl=self.metadata_ttl)
        return tracks

    def get_track_details(self, provider_track_id: str) -> UnifiedTrack:
        self._require_configured()
        track_id = str(provider_track_id).strip()
        cache_key = f"jamendo:track:{track_id}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        payload = self._request_jamendo(
            "tracks/",
            {
                "id": track_id,
                "include": "musicinfo+licenses+stats",
                "audioformat": self.audio_format,
            },
        )
        results = payload.get("results") or []
        if not results:
            raise TrackNotFoundError(
                f"Jamendo track '{track_id}' not found.",
                provider=self.name,
            )
        track = self.normalize_track(results[0])
        self.cache.set(cache_key, track, ttl=self.metadata_ttl)
        return track

    def get_track_stream(self, provider_track_id: str) -> PlaybackInfo:
        # Fetch fresh track details bypassing cache so stream availability & URL are current
        self._require_configured()
        track_id = str(provider_track_id).strip()
        payload = self._request_jamendo(
            "tracks/",
            {
                "id": track_id,
                "include": "musicinfo+licenses",
                "audioformat": self.audio_format,
            },
        )
        results = payload.get("results") or []
        if not results:
            raise TrackNotFoundError(
                f"Jamendo track '{track_id}' not found.",
                provider=self.name,
            )
        track = self.normalize_track(results[0])
        return PlaybackInfo(
            internal_id=track.internal_id,
            provider=self.name,
            provider_track_id=track.provider_track_id,
            playback_url=track.playback_url,
            playback_reference=track.playback_reference,
            playback_type=track.licensing.permitted_playback_type,
            expires_at=track.playback_expires_at,
            is_playable=bool(track.is_available and track.playback_url),
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
        self._require_configured()
        limit = max(1, min(int(limit), 30))
        cache_key = f"jamendo:playlists:{query}:{mood}:{limit}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        params: Dict[str, Any] = {"limit": limit, "order": "creationdate_desc"}
        search_term = query or mood
        if search_term:
            params["namesearch"] = search_term.strip()

        payload = self._request_jamendo("playlists/", params)
        summaries: List[PlaylistSummary] = []
        for item in payload.get("results") or []:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            pid = str(item["id"])
            summaries.append(
                PlaylistSummary(
                    internal_id=make_internal_track_id(self.name, pid),
                    provider=self.name,
                    provider_playlist_id=pid,
                    name=str(item.get("name") or "Untitled Playlist"),
                    description=item.get("user_name") and f"Curated by {item['user_name']}",
                    artwork=item.get("image") or None,
                    track_count=None,
                    tags=[mood] if mood else [],
                    provider_metadata={
                        "creationdate": item.get("creationdate"),
                        "shareurl": item.get("shareurl"),
                        "user_id": item.get("user_id"),
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
        self._require_configured()
        limit = max(1, min(int(limit), 50))
        tags_list = [t.strip().lower() for t in (mood_tags or []) if t and t.strip()]
        genre_list = [g.strip().lower() for g in (genres or []) if g and g.strip()]

        speed_param = self._speed_filter_for_targets(bpm_range=bpm_range, target_energy=target_energy)
        cache_key = f"jamendo:recs:{tags_list}:{genre_list}:{speed_param}:{language}:{limit}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        params: Dict[str, Any] = {
            "limit": limit,
            "include": "musicinfo+licenses+stats",
            "audioformat": self.audio_format,
            "order": "popularity_week",
        }
        combined_tags = (tags_list[:4] + genre_list[:3])[:6]
        if combined_tags:
            params["fuzzytags"] = "+".join(combined_tags)
        if speed_param:
            params["speed"] = speed_param
        if language:
            params["lang"] = language.strip().lower()[:2]

        payload = self._request_jamendo("tracks/", params)
        results = payload.get("results") or []

        # Broaden query if strict speed/language filter returned too few tracks
        if len(results) < max(3, limit // 3) and ("speed" in params or "lang" in params):
            broad_params = {
                k: v for k, v in params.items() if k not in {"speed", "lang"}
            }
            payload = self._request_jamendo("tracks/", broad_params)
            results = payload.get("results") or []

        tracks = [self.normalize_track(item) for item in results if isinstance(item, dict)]
        self.cache.set(cache_key, tracks, ttl=self.metadata_ttl)
        return tracks

    def get_provider_status(self, force_refresh: bool = False) -> ProviderStatus:
        licensing_notes = (
            "Jamendo API v3.0 free tier (35k req/mo) is non-commercial only. "
            "Commercial streaming requires Jamendo Licensing / Pro approval."
        )
        if not self.enabled:
            return ProviderStatus(
                provider=self.name,
                configured=False,
                healthy=False,
                status="unconfigured",
                message="Jamendo provider is disabled via configuration.",
                capabilities=self.capabilities,
                licensing_notes=licensing_notes,
            )
        if not self.client_id:
            return ProviderStatus(
                provider=self.name,
                configured=False,
                healthy=False,
                status="unconfigured",
                message="Set JAMENDO_CLIENT_ID to enable Jamendo API v3.0.",
                capabilities=self.capabilities,
                licensing_notes=licensing_notes,
            )

        cache_key = "jamendo:health"
        if not force_refresh:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached

        started = time.monotonic()
        try:
            self._request_jamendo("tracks/", {"limit": 1, "order": "popularity_week"})
            latency_ms = round((time.monotonic() - started) * 1000.0, 2)
            status = ProviderStatus(
                provider=self.name,
                configured=True,
                healthy=True,
                status="healthy",
                message="Jamendo API v3.0 is reachable and responding.",
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
        title = str(raw_track.get("name") or "Untitled Track").strip()
        artist = str(raw_track.get("artist_name") or "Unknown Artist").strip()
        album = raw_track.get("album_name") or None

        musicinfo = raw_track.get("musicinfo") if isinstance(raw_track.get("musicinfo"), dict) else {}
        tags_dict = musicinfo.get("tags") if isinstance(musicinfo.get("tags"), dict) else {}

        genres = [str(g).strip().lower() for g in (tags_dict.get("genres") or []) if g]
        vartags = [str(t).strip().lower() for t in (tags_dict.get("vartags") or []) if t]
        instruments = [str(i).strip().lower() for i in (tags_dict.get("instruments") or []) if i]

        speed_label = str(musicinfo.get("speed") or "").strip().lower()
        estimated_energy, estimated_bpm = JAMENDO_SPEED_PROFILE.get(speed_label, (None, None))

        duration_raw = raw_track.get("duration")
        duration = int(duration_raw) if duration_raw is not None and str(duration_raw).isdigit() else None

        audio_url = (raw_track.get("audio") or "").strip() or None
        artwork = raw_track.get("album_image") or raw_track.get("image") or None
        license_ccurl = (raw_track.get("license_ccurl") or "").strip() or None
        prourl = (raw_track.get("prourl") or "").strip() or None
        audiodownload_allowed = bool(raw_track.get("audiodownload_allowed", False))
        language = (musicinfo.get("lang") or "").strip().lower() or None

        licensing = build_jamendo_licensing(
            title=title,
            artist=artist,
            license_ccurl=license_ccurl,
            prourl=prourl,
            audiodownload_allowed=audiodownload_allowed,
            has_audio_stream=bool(audio_url),
            commercial_agreement_verified=self.commercial_agreement_verified,
        )

        mood_tags = list(dict.fromkeys(vartags + genres))

        return UnifiedTrack(
            internal_id=make_internal_track_id(self.name, provider_track_id),
            provider=self.name,
            provider_track_id=provider_track_id,
            title=title,
            artist=artist,
            album=album,
            genre=genres[0] if genres else None,
            duration=duration,
            bpm=estimated_bpm,
            energy=estimated_energy,
            mood_tags=mood_tags,
            language=language,
            artwork=artwork,
            preview_url=audio_url,
            playback_url=audio_url,
            playback_reference=raw_track.get("shareurl") or audio_url,
            playback_expires_at=None,
            is_available=bool(audio_url),
            licensing=licensing,
            provider_metadata={
                "jamendo_artist_id": raw_track.get("artist_id"),
                "jamendo_album_id": raw_track.get("album_id"),
                "shareurl": raw_track.get("shareurl"),
                "shorturl": raw_track.get("shorturl"),
                "prourl": prourl,
                "audiodownload_allowed": audiodownload_allowed,
                "speed": speed_label or None,
                "vocalinstrumental": musicinfo.get("vocalinstrumental"),
                "acousticelectric": musicinfo.get("acousticelectric"),
                "instruments": instruments,
                "stats": raw_track.get("stats"),
                "licenses": raw_track.get("licenses"),
            },
        )

    @staticmethod
    def _speed_filter_for_targets(
        *,
        bpm_range: Optional[tuple[float, float]] = None,
        target_energy: Optional[float] = None,
    ) -> Optional[str]:
        if target_energy is not None:
            if target_energy < 0.35:
                return "verylow+low"
            if target_energy < 0.65:
                return "low+medium"
            return "medium+high+veryhigh"
        if bpm_range is not None:
            mid = (bpm_range[0] + bpm_range[1]) / 2.0
            if mid < 85:
                return "verylow+low"
            if mid < 115:
                return "low+medium"
            return "medium+high+veryhigh"
        return None
