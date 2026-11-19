"""Typed exceptions for the multi-provider music integration layer."""
from __future__ import annotations

from typing import Optional


class MusicProviderError(Exception):
    """Base error for all music provider operations."""

    def __init__(
        self,
        message: str,
        provider: Optional[str] = None,
        status_code: Optional[int] = None,
        code: str = "provider_error",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.status_code = status_code
        self.code = code


class UnsupportedOperationError(MusicProviderError):
    """Raised when a provider does not support a requested operation."""

    def __init__(self, message: str, provider: Optional[str] = None) -> None:
        super().__init__(message, provider=provider, status_code=501, code="unsupported_operation")


class ProviderConfigError(MusicProviderError):
    """Raised when required provider credentials or configuration are missing."""

    def __init__(self, message: str, provider: Optional[str] = None) -> None:
        super().__init__(message, provider=provider, status_code=503, code="provider_not_configured")


class ProviderAuthError(MusicProviderError):
    """Raised when upstream provider authentication or authorization fails."""

    def __init__(self, message: str, provider: Optional[str] = None) -> None:
        super().__init__(message, provider=provider, status_code=502, code="provider_auth_failed")


class ProviderRateLimitError(MusicProviderError):
    """Raised when a provider responds with rate limiting (HTTP 429 or API quota)."""

    def __init__(
        self,
        message: str,
        provider: Optional[str] = None,
        retry_after: Optional[float] = None,
    ) -> None:
        super().__init__(message, provider=provider, status_code=429, code="provider_rate_limited")
        self.retry_after = retry_after


class ProviderUnavailableError(MusicProviderError):
    """Raised when a provider is unreachable, timed out, or returning 5xx."""

    def __init__(self, message: str, provider: Optional[str] = None) -> None:
        super().__init__(message, provider=provider, status_code=503, code="provider_unavailable")


class TrackNotFoundError(MusicProviderError):
    """Raised when a track cannot be found on the specified provider."""

    def __init__(self, message: str, provider: Optional[str] = None) -> None:
        super().__init__(message, provider=provider, status_code=404, code="track_not_found")


class LicensingViolationError(MusicProviderError):
    """Raised when playback is blocked by licensing or provider restriction checks."""

    def __init__(
        self,
        message: str,
        provider: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> None:
        super().__init__(message, provider=provider, status_code=403, code="licensing_blocked")
        self.reason = reason or message


class StreamExpiredError(MusicProviderError):
    """Raised when a time-limited playback URL has expired and must be refreshed."""

    def __init__(self, message: str, provider: Optional[str] = None) -> None:
        super().__init__(message, provider=provider, status_code=410, code="stream_expired")
