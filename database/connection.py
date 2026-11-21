"""Supabase connection management with credentials isolation and health reporting."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    import importlib.util
    SUPABASE_SDK_AVAILABLE = importlib.util.find_spec("supabase") is not None
except Exception:
    SUPABASE_SDK_AVAILABLE = False
Client = Any  # type: ignore[misc,assignment]


class SupabaseConnectionManager:
    """Manages Supabase client instances.

    - Anon client: for client-level queries and GoTrue user authentication operations.
    - Admin client: uses SUPABASE_SERVICE_ROLE_KEY for server-side trusted operations
      (e.g., cascade account deletion, system audit logging, bypass RLS when required).
    - NEVER exposes SUPABASE_SERVICE_ROLE_KEY to frontend JavaScript or public endpoints.
    """

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        supabase_anon_key: Optional[str] = None,
        supabase_service_role_key: Optional[str] = None,
    ) -> None:
        self.url = (supabase_url or os.getenv("SUPABASE_URL", "")).strip().rstrip("/")
        self.anon_key = (supabase_anon_key or os.getenv("SUPABASE_ANON_KEY", "")).strip()
        self.service_role_key = (
            supabase_service_role_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        ).strip()

        self._anon_client: Optional[Client] = None
        self._admin_client: Optional[Client] = None

    @property
    def is_configured(self) -> bool:
        """Return True when minimum Supabase credentials are provided."""
        if not (self.url and self.anon_key and SUPABASE_SDK_AVAILABLE):
            return False
        if "your-project" in self.url or "your-supabase" in self.anon_key:
            return False
        return True

    @property
    def has_admin_privileges(self) -> bool:
        if not (self.url and self.service_role_key and SUPABASE_SDK_AVAILABLE):
            return False
        if "your-project" in self.url or "your-supabase" in self.service_role_key:
            return False
        return True

    def get_client(self, user_jwt: Optional[str] = None) -> Optional[Client]:
        """Return a Supabase client configured for public/authenticated user requests."""
        if not self.is_configured:
            return None

        if user_jwt:
            # Create a user-scoped client that sends the user's JWT so RLS enforces auth.uid()
            try:
                from supabase import create_client
                client = create_client(self.url, self.anon_key)
                client.postgrest.auth(user_jwt)
                return client
            except Exception as exc:
                logger.error("Failed to create user-scoped Supabase client: %s", exc)
                return None

        if self._anon_client is None:
            try:
                from supabase import create_client
                self._anon_client = create_client(self.url, self.anon_key)
            except Exception as exc:
                logger.error("Failed to initialize Supabase anon client: %s", exc)
                return None
        return self._anon_client

    def get_admin_client(self) -> Optional[Client]:
        """Return privileged Supabase client using service role key (strictly server-side)."""
        if not self.has_admin_privileges:
            return None

        if self._admin_client is None:
            try:
                from supabase import create_client
                self._admin_client = create_client(self.url, self.service_role_key)
            except Exception as exc:
                logger.error("Failed to initialize Supabase admin client: %s", exc)
                return None
        return self._admin_client

    def check_health(self) -> Dict[str, Any]:
        """Check connection health and return status dict (exposes no secret keys)."""
        if not SUPABASE_SDK_AVAILABLE:
            return {
                "status": "unavailable",
                "configured": False,
                "message": "supabase-py package is not installed.",
            }

        if not (self.url and self.anon_key):
            return {
                "status": "unconfigured",
                "configured": False,
                "message": "SUPABASE_URL and SUPABASE_ANON_KEY are not configured.",
            }

        client = self.get_client()
        if client is None:
            return {
                "status": "error",
                "configured": True,
                "message": "Could not instantiate Supabase client.",
            }

        try:
            # Query public policy_versions table as a lightweight health check
            res = client.table("policy_versions").select("version").limit(1).execute()
            return {
                "status": "healthy",
                "configured": True,
                "url": self.url,
                "service_role_configured": bool(self.service_role_key),
                "message": "Supabase PostgreSQL is connected and responsive.",
            }
        except Exception as exc:
            return {
                "status": "degraded",
                "configured": True,
                "url": self.url,
                "service_role_configured": bool(self.service_role_key),
                "message": f"Supabase health check probe failed: {exc}",
            }


# Singleton instance initialized from environment variables
db_manager = SupabaseConnectionManager()
