"""Licensing metadata evaluation and playback compliance enforcement.

Never assumes API access grants commercial streaming rights.
Blocks commercial playback for any track that has not passed verified commercial checks.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from music.exceptions import LicensingViolationError
from music.models import (
    DeploymentMode,
    LicensingMetadata,
    LicensingVerificationStatus,
    UnifiedTrack,
)


def _extract_cc_code(cc_url: Optional[str]) -> Optional[str]:
    if not cc_url:
        return None
    lower = cc_url.lower()
    if "publicdomain/zero" in lower or "cc0" in lower:
        return "CC0"
    match = re.search(r"licenses/([a-z\-]+)/", lower)
    if match:
        return f"CC {match.group(1).upper()}"
    return None


def build_jamendo_licensing(
    *,
    title: str,
    artist: str,
    license_ccurl: Optional[str],
    prourl: Optional[str],
    audiodownload_allowed: bool,
    has_audio_stream: bool,
    commercial_agreement_verified: bool = False,
) -> LicensingMetadata:
    """Build verified LicensingMetadata for a Jamendo v3.0 track.

    Jamendo free API tier (35k req/mo) is strictly non-commercial.
    Tracks carry Creative Commons licenses (often CC BY-NC / BY-NC-ND).
    Commercial streaming requires Jamendo Licensing / Pro commercial clearance.
    """
    cc_code = _extract_cc_code(license_ccurl)
    is_non_commercial_cc = bool(cc_code and "NC" in cc_code)
    is_cc_commercial_permitting = bool(cc_code and cc_code in {"CC0", "CC BY", "CC BY-SA", "CC BY-ND"})

    license_type = cc_code or ("Jamendo Pro" if prourl else "Jamendo Standard (Unverified)")
    attribution_required = cc_code != "CC0"
    attribution_text = (
        f"'{title}' by {artist} via Jamendo ({license_type})"
        + (f" — {license_ccurl}" if license_ccurl else "")
    )

    if not has_audio_stream:
        return LicensingMetadata(
            license_type=license_type,
            license_source="Jamendo API v3.0",
            license_url=license_ccurl or prourl,
            permitted_playback_type="none",
            commercial_use_allowed=False,
            redistribution_allowed=False,
            attribution_required=attribution_required,
            attribution_text=attribution_text,
            verification_status=LicensingVerificationStatus.BLOCKED.value,
            restriction_reason="No authorized audio stream URL returned by Jamendo.",
            commercial_approval_required=True,
        )

    # Commercial permission: either an explicit verified Jamendo Pro/Licensing agreement
    # covering this track OR a verified CC0/CC-BY license with explicit commercial approval.
    # Remember: Jamendo API Terms restrict free API tier to non-commercial apps!
    if commercial_agreement_verified and (bool(prourl) or is_cc_commercial_permitting):
        commercial_allowed = True
        verification_status = LicensingVerificationStatus.VERIFIED.value
        commercial_approval_required = False
        restriction_reason = None
    elif cc_code:
        commercial_allowed = False
        verification_status = (
            LicensingVerificationStatus.RESTRICTED.value
            if is_non_commercial_cc
            else LicensingVerificationStatus.VERIFIED.value
        )
        commercial_approval_required = True
        restriction_reason = (
            "Track carries a Non-Commercial Creative Commons license (CC-NC); commercial use requires Jamendo Licensing."
            if is_non_commercial_cc
            else "Standard Jamendo API tier is restricted to non-commercial apps; commercial streaming requires Jamendo Licensing / Pro approval."
        )
    else:
        commercial_allowed = False
        verification_status = LicensingVerificationStatus.UNVERIFIED.value
        commercial_approval_required = True
        restriction_reason = "No verified Creative Commons or Jamendo Pro license metadata returned."

    return LicensingMetadata(
        license_type=license_type,
        license_source="Jamendo API v3.0",
        license_url=license_ccurl or prourl,
        permitted_playback_type="direct_stream",
        commercial_use_allowed=commercial_allowed,
        redistribution_allowed=False,  # Jamendo API prohibits audio caching/redistribution
        attribution_required=attribution_required,
        attribution_text=attribution_text,
        verification_status=verification_status,
        restriction_reason=restriction_reason,
        commercial_approval_required=commercial_approval_required,
    )


def build_audius_licensing(
    *,
    title: str,
    artist: str,
    license_str: Optional[str],
    is_streamable: bool,
    stream_conditions: Optional[Dict[str, Any]],
    is_unlisted: bool = False,
    oml_commercial_verified: bool = False,
) -> LicensingMetadata:
    """Build LicensingMetadata for an Audius v1 track.

    Respects artist-controlled `is_streamable`, `stream_conditions` (gating),
    and `license` ("All Rights Reserved", Creative Commons, or Open Music License).
    """
    raw_license = (license_str or "").strip()
    lower = raw_license.lower()
    attribution_text = f"'{title}' by {artist} via Audius" + (f" ({raw_license})" if raw_license else "")

    if not is_streamable:
        return LicensingMetadata(
            license_type=raw_license or "All Rights Reserved",
            license_source="Audius API v1",
            permitted_playback_type="none",
            commercial_use_allowed=False,
            redistribution_allowed=False,
            attribution_required=True,
            attribution_text=attribution_text,
            verification_status=LicensingVerificationStatus.BLOCKED.value,
            restriction_reason="Artist disabled API streaming (is_streamable=false).",
            commercial_approval_required=True,
        )

    if stream_conditions:
        return LicensingMetadata(
            license_type=raw_license or "Gated Track",
            license_source="Audius API v1",
            permitted_playback_type="none",
            commercial_use_allowed=False,
            redistribution_allowed=False,
            attribution_required=True,
            attribution_text=attribution_text,
            verification_status=LicensingVerificationStatus.BLOCKED.value,
            restriction_reason="Track has stream_conditions (gated access); bypassing restrictions is prohibited.",
            commercial_approval_required=True,
        )

    if is_unlisted:
        return LicensingMetadata(
            license_type=raw_license or "Unlisted",
            license_source="Audius API v1",
            permitted_playback_type="none",
            commercial_use_allowed=False,
            redistribution_allowed=False,
            attribution_required=True,
            attribution_text=attribution_text,
            verification_status=LicensingVerificationStatus.BLOCKED.value,
            restriction_reason="Track is unlisted and excluded from public recommendation playback.",
            commercial_approval_required=True,
        )

    is_cc0 = "cc0" in lower or "public domain" in lower
    is_cc_nc = "noncommercial" in lower or "by-nc" in lower or "nc-" in lower
    is_cc_by_commercial = (
        ("attribution" in lower or "cc by" in lower or "cc-by" in lower) and not is_cc_nc
    )
    is_oml = "open music license" in lower or "oml" in lower
    is_all_rights_reserved = not raw_license or "all rights reserved" in lower

    if is_cc0:
        return LicensingMetadata(
            license_type=raw_license or "CC0",
            license_source="Audius API v1",
            permitted_playback_type="direct_stream",
            commercial_use_allowed=True,
            redistribution_allowed=False,
            attribution_required=False,
            attribution_text=attribution_text,
            verification_status=LicensingVerificationStatus.VERIFIED.value,
            commercial_approval_required=False,
        )

    if is_cc_by_commercial:
        return LicensingMetadata(
            license_type=raw_license,
            license_source="Audius API v1",
            permitted_playback_type="direct_stream",
            commercial_use_allowed=True,
            redistribution_allowed=False,
            attribution_required=True,
            attribution_text=attribution_text,
            verification_status=LicensingVerificationStatus.VERIFIED.value,
            commercial_approval_required=False,
        )

    if is_oml:
        return LicensingMetadata(
            license_type=raw_license,
            license_source="Audius API v1 (Open Music License)",
            permitted_playback_type="direct_stream",
            commercial_use_allowed=oml_commercial_verified,
            redistribution_allowed=False,
            attribution_required=True,
            attribution_text=attribution_text,
            verification_status=(
                LicensingVerificationStatus.VERIFIED.value
                if oml_commercial_verified
                else LicensingVerificationStatus.RESTRICTED.value
            ),
            restriction_reason=(
                None
                if oml_commercial_verified
                else "Audius Open Music License commercial compliance must be verified before commercial playback."
            ),
            commercial_approval_required=not oml_commercial_verified,
        )

    if is_cc_nc:
        return LicensingMetadata(
            license_type=raw_license,
            license_source="Audius API v1",
            permitted_playback_type="direct_stream",
            commercial_use_allowed=False,
            redistribution_allowed=False,
            attribution_required=True,
            attribution_text=attribution_text,
            verification_status=LicensingVerificationStatus.RESTRICTED.value,
            restriction_reason="Track carries a Non-Commercial Creative Commons license.",
            commercial_approval_required=True,
        )

    # Default: "All Rights Reserved" or unrecognized license string
    return LicensingMetadata(
        license_type=raw_license or "All Rights Reserved",
        license_source="Audius API v1",
        permitted_playback_type="direct_stream",
        commercial_use_allowed=False,
        redistribution_allowed=False,
        attribution_required=True,
        attribution_text=attribution_text,
        verification_status=(
            LicensingVerificationStatus.RESTRICTED.value
            if is_all_rights_reserved
            else LicensingVerificationStatus.UNVERIFIED.value
        ),
        restriction_reason="Track is 'All Rights Reserved' or has unverified commercial rights; commercial playback is blocked.",
        commercial_approval_required=True,
    )


def build_mubert_licensing(
    *,
    title: str,
    b2b_license_verified: bool,
    plan_name: Optional[str] = None,
) -> LicensingMetadata:
    """Build LicensingMetadata for Mubert API v3 AI-generated streams.

    Commercial app usage requires an active paid Mubert B2B/API license.
    DSP distribution, Content ID registration, and stock resale are prohibited on all plans.
    """
    license_label = f"Mubert B2B ({plan_name})" if plan_name else "Mubert API v3 License"
    attribution_text = f"'{title}' — AI generative audio powered by Mubert"

    if not b2b_license_verified:
        return LicensingMetadata(
            license_type=license_label,
            license_source="Mubert API v3",
            permitted_playback_type="none",
            commercial_use_allowed=False,
            redistribution_allowed=False,
            attribution_required=True,
            attribution_text=attribution_text,
            verification_status=LicensingVerificationStatus.UNVERIFIED.value,
            restriction_reason="Mubert commercial license not verified via /api/v3/service/licenses.",
            commercial_approval_required=True,
        )

    return LicensingMetadata(
        license_type=license_label,
        license_source="Mubert API v3",
        permitted_playback_type="time_limited_stream",
        commercial_use_allowed=True,
        redistribution_allowed=False,  # DSP upload, Content ID & stock resale strictly prohibited
        attribution_required=True,
        attribution_text=attribution_text,
        verification_status=LicensingVerificationStatus.VERIFIED.value,
        restriction_reason=None,
        commercial_approval_required=False,
    )


class LicensingValidator:
    """Enforces deployment-level playback licensing policy across all providers."""

    def __init__(self, deployment_mode: str = DeploymentMode.NON_COMMERCIAL.value) -> None:
        try:
            self.deployment_mode = DeploymentMode(deployment_mode)
        except ValueError:
            self.deployment_mode = DeploymentMode.NON_COMMERCIAL

    def is_playable(self, track: UnifiedTrack) -> tuple[bool, Optional[str]]:
        """Check whether a track is permitted for playback under the active deployment mode."""
        if not track.is_available:
            return False, "Track is currently unavailable on provider."

        lic = track.licensing
        if lic.verification_status == LicensingVerificationStatus.BLOCKED.value:
            return False, lic.restriction_reason or "Track playback is blocked by provider licensing rules."

        if lic.permitted_playback_type == "none":
            return False, lic.restriction_reason or "Provider does not permit playback for this track."

        if self.deployment_mode == DeploymentMode.COMMERCIAL:
            if lic.verification_status != LicensingVerificationStatus.VERIFIED.value:
                return (
                    False,
                    lic.restriction_reason
                    or f"Commercial playback blocked: licensing status is '{lic.verification_status}'.",
                )
            if not lic.commercial_use_allowed:
                return (
                    False,
                    lic.restriction_reason
                    or "Commercial playback blocked: track is not cleared for commercial streaming.",
                )
        else:
            # Even in non-commercial mode, block completely unverified Mubert/unknown licenses with no playback type
            if lic.verification_status == LicensingVerificationStatus.UNVERIFIED.value and not (
                track.playback_url or track.playback_reference
            ):
                return False, lic.restriction_reason or "Track has unverified licensing and no authorized playback URL."

        if not (track.playback_url or track.playback_reference):
            return False, "No authorized playback URL or reference available."

        return True, None

    def enforce_playback(self, track: UnifiedTrack) -> None:
        """Raise LicensingViolationError if track fails playback licensing checks."""
        allowed, reason = self.is_playable(track)
        if not allowed:
            raise LicensingViolationError(
                reason or "Track failed licensing validation.",
                provider=track.provider,
                reason=reason,
            )
