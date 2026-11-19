"""Resilient HTTP client with timeouts, retries, rate-limit handling, and secret redaction."""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, Optional, Tuple

import requests

from music.exceptions import (
    MusicProviderError,
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderUnavailableError,
    TrackNotFoundError,
)

logger = logging.getLogger(__name__)

SENSITIVE_KEYS = {
    "client_id",
    "client_secret",
    "api_key",
    "authorization",
    "license-token",
    "access-token",
    "company-id",
    "x-api-key",
}


def redact_dict(data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return a shallow copy with sensitive auth keys redacted for safe logging."""
    if not data:
        return {}
    redacted: Dict[str, Any] = {}
    for key, value in data.items():
        if key.lower() in SENSITIVE_KEYS:
            redacted[key] = "***REDACTED***"
        else:
            redacted[key] = value
    return redacted


class ResilientHTTPClient:
    """HTTP wrapper for music provider JSON APIs (never downloads/caches audio streams)."""

    def __init__(
        self,
        provider_name: str,
        connect_timeout: float = 5.0,
        read_timeout: float = 10.0,
        max_retries: int = 2,
        backoff_base_seconds: float = 0.5,
        max_retry_after_seconds: float = 5.0,
        session: Optional[requests.Session] = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.provider_name = provider_name
        self.timeout: Tuple[float, float] = (connect_timeout, read_timeout)
        self.max_retries = max(0, int(max_retries))
        self.backoff_base_seconds = max(0.0, float(backoff_base_seconds))
        self.max_retry_after_seconds = max(0.0, float(max_retry_after_seconds))
        self.session = session or requests.Session()
        self.sleep_fn = sleep_fn

    def request_json(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        allow_404_none: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Execute an HTTP request expecting JSON with retries and rate-limit handling."""
        attempt = 0
        last_error: Optional[Exception] = None

        while attempt <= self.max_retries:
            started = time.monotonic()
            try:
                response = self.session.request(
                    method=method.upper(),
                    url=url,
                    params=params,
                    headers=headers,
                    json=json_body,
                    timeout=self.timeout,
                )
                elapsed_ms = round((time.monotonic() - started) * 1000.0, 2)
                logger.debug(
                    "HTTP %s %s [%s] -> %s (%.2fms) params=%s",
                    method.upper(),
                    url,
                    self.provider_name,
                    response.status_code,
                    elapsed_ms,
                    redact_dict(params),
                )

                status = response.status_code
                if status in (401, 403):
                    raise ProviderAuthError(
                        f"{self.provider_name} authentication/authorization failed (HTTP {status})",
                        provider=self.provider_name,
                    )

                if status == 404:
                    if allow_404_none:
                        return None
                    raise TrackNotFoundError(
                        f"Resource not found on {self.provider_name} (HTTP 404)",
                        provider=self.provider_name,
                    )

                if status == 429:
                    retry_after = self._parse_retry_after(response.headers.get("Retry-After"))
                    if attempt < self.max_retries and retry_after is not None and retry_after <= self.max_retry_after_seconds:
                        logger.warning(
                            "%s rate limited (HTTP 429); retrying after %.2fs (attempt %d/%d)",
                            self.provider_name,
                            retry_after,
                            attempt + 1,
                            self.max_retries,
                        )
                        self.sleep_fn(retry_after)
                        attempt += 1
                        continue
                    raise ProviderRateLimitError(
                        f"{self.provider_name} rate limit exceeded (HTTP 429)",
                        provider=self.provider_name,
                        retry_after=retry_after,
                    )

                if status >= 500:
                    if attempt < self.max_retries:
                        delay = self.backoff_base_seconds * (2**attempt)
                        logger.warning(
                            "%s returned HTTP %s; retrying in %.2fs (attempt %d/%d)",
                            self.provider_name,
                            status,
                            delay,
                            attempt + 1,
                            self.max_retries,
                        )
                        self.sleep_fn(delay)
                        attempt += 1
                        continue
                    raise ProviderUnavailableError(
                        f"{self.provider_name} service error (HTTP {status})",
                        provider=self.provider_name,
                    )

                if status >= 400:
                    raise MusicProviderError(
                        f"{self.provider_name} request failed with HTTP {status}",
                        provider=self.provider_name,
                        status_code=status,
                    )

                try:
                    return response.json()
                except ValueError as exc:
                    raise MusicProviderError(
                        f"{self.provider_name} returned invalid JSON payload",
                        provider=self.provider_name,
                        status_code=502,
                    ) from exc

            except (ProviderAuthError, ProviderRateLimitError, TrackNotFoundError):
                raise
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    delay = self.backoff_base_seconds * (2**attempt)
                    logger.warning(
                        "%s network/timeout error (%s); retrying in %.2fs (attempt %d/%d)",
                        self.provider_name,
                        exc.__class__.__name__,
                        delay,
                        attempt + 1,
                        self.max_retries,
                    )
                    self.sleep_fn(delay)
                    attempt += 1
                    continue
                raise ProviderUnavailableError(
                    f"{self.provider_name} request timed out or failed to connect: {exc}",
                    provider=self.provider_name,
                ) from exc
            except requests.RequestException as exc:
                last_error = exc
                raise ProviderUnavailableError(
                    f"{self.provider_name} HTTP error: {exc}",
                    provider=self.provider_name,
                ) from exc

        raise ProviderUnavailableError(
            f"{self.provider_name} failed after {self.max_retries} retries: {last_error}",
            provider=self.provider_name,
        )

    def resolve_redirect_url(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, Optional[str]]:
        """Issue a lightweight HEAD request without downloading audio bytes to verify/resolve redirects."""
        try:
            response = self.session.request(
                method="HEAD",
                url=url,
                params=params,
                headers=headers,
                allow_redirects=False,
                timeout=self.timeout,
            )
            location = response.headers.get("Location")
            return response.status_code, location
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise ProviderUnavailableError(
                f"{self.provider_name} stream verification failed: {exc}",
                provider=self.provider_name,
            ) from exc
        except requests.RequestException as exc:
            raise MusicProviderError(
                f"{self.provider_name} stream check error: {exc}",
                provider=self.provider_name,
            ) from exc

    @staticmethod
    def _parse_retry_after(header_value: Optional[str]) -> Optional[float]:
        if not header_value:
            return None
        try:
            value = float(header_value.strip())
            return max(0.0, value)
        except ValueError:
            return None
