"""cache_manager.py — Redis-backed caching for Vercel KV with in-memory fallback.

Provides async cache operations for:
1. Prompt validation results (10-minute TTL, ~1MB per entry)
2. Teams bot conversation state (60-minute TTL, ~10KB per entry)

Falls back gracefully to in-memory dicts if Redis is unavailable.
"""

import json
import logging
import time
from typing import Any, Optional

import redis.asyncio as redis

_log = logging.getLogger(__name__)

# Fallback in-memory caches (when Redis unavailable)
_fallback_validation_cache: dict[str, tuple[float, Any]] = {}
_fallback_teams_cache: dict[str, Any] = {}


class CacheManager:
    """Thread-safe async cache manager backed by Redis (Vercel KV) or in-memory fallback."""

    def __init__(self, redis_url: Optional[str] = None):
        """Initialize cache manager.

        Args:
            redis_url: Connection string for Redis/Vercel KV.
                       Format: redis://[:password]@host:port[/db]
                       If None, uses in-memory fallback only.
        """
        self.redis_url = redis_url
        self._redis_client: Optional[redis.Redis] = None
        self._redis_available = False
        self._init_task = None

    async def initialize(self) -> None:
        """Connect to Redis and verify connectivity. Safe to call multiple times."""
        if self._redis_client is not None:
            return  # Already initialized

        if not self.redis_url:
            _log.warning("VERCEL_KV_URL not configured. Using in-memory fallback cache.")
            self._redis_available = False
            return

        try:
            self._redis_client = await redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
                socket_keepalive_options={},
            )
            # Test connectivity
            await self._redis_client.ping()
            self._redis_available = True
            _log.info("✅ Redis (Vercel KV) connected and healthy.")
        except Exception as exc:
            _log.warning(
                f"⚠️  Failed to connect to Redis: {exc}. Falling back to in-memory cache. "
                "Validation results will NOT persist across restarts."
            )
            self._redis_available = False
            self._redis_client = None

    async def close(self) -> None:
        """Close Redis connection gracefully."""
        if self._redis_client:
            await self._redis_client.close()
            self._redis_client = None
            self._redis_available = False

    async def get_validation(self, key: str) -> Optional[dict[str, Any]]:
        """Retrieve cached validation result.

        Args:
            key: Cache key (SHA-256 hash of persona_id:auto_improve:prompt_text)

        Returns:
            Cached result dict, or None if expired/missing.
        """
        if self._redis_available and self._redis_client:
            try:
                cached_json = await self._redis_client.get(f"val:{key}")
                if cached_json:
                    return json.loads(cached_json)
            except Exception as exc:
                _log.warning(f"Redis GET failed: {exc}. Using fallback.")

        # Fallback to in-memory
        if key in _fallback_validation_cache:
            expire_ts, result = _fallback_validation_cache[key]
            if time.monotonic() < expire_ts:
                return result
            else:
                del _fallback_validation_cache[key]  # Evict expired
        return None

    async def set_validation(self, key: str, result: dict[str, Any], ttl_seconds: int) -> None:
        """Store validation result with TTL.

        Args:
            key: Cache key
            result: Validation result dict
            ttl_seconds: Time-to-live in seconds
        """
        try:
            result_json = json.dumps(result)
        except Exception as exc:
            _log.error(f"Failed to serialize validation result: {exc}")
            return

        if self._redis_available and self._redis_client:
            try:
                await self._redis_client.setex(f"val:{key}", ttl_seconds, result_json)
                return
            except Exception as exc:
                _log.warning(f"Redis SETEX failed: {exc}. Using fallback.")

        # Fallback to in-memory
        expire_ts = time.monotonic() + ttl_seconds
        _fallback_validation_cache[key] = (expire_ts, result)

    async def get_teams_persona(self, conversation_id: str) -> Optional[str]:
        """Retrieve Teams user's selected persona.

        Args:
            conversation_id: Teams conversation ID (e.g., user email or team:channel:user)

        Returns:
            Persona ID (e.g., "persona_4"), or None if not set.
        """
        if self._redis_available and self._redis_client:
            try:
                persona = await self._redis_client.get(f"teams:persona:{conversation_id}")
                return persona
            except Exception as exc:
                _log.warning(f"Redis GET failed: {exc}. Using fallback.")

        # Fallback to in-memory
        return _fallback_teams_cache.get(f"persona:{conversation_id}")

    async def set_teams_persona(self, conversation_id: str, persona_id: str, ttl_seconds: int = 3600) -> None:
        """Store Teams user's selected persona.

        Args:
            conversation_id: Teams conversation ID
            persona_id: Selected persona (e.g., "persona_4")
            ttl_seconds: Time-to-live (default 1 hour)
        """
        if self._redis_available and self._redis_client:
            try:
                await self._redis_client.setex(f"teams:persona:{conversation_id}", ttl_seconds, persona_id)
                return
            except Exception as exc:
                _log.warning(f"Redis SETEX failed: {exc}. Using fallback.")

        # Fallback to in-memory (no TTL, but that's ok for fallback)
        _fallback_teams_cache[f"persona:{conversation_id}"] = persona_id

    async def get_teams_result(self, conversation_id: str) -> Optional[dict[str, Any]]:
        """Retrieve last validation result for Teams user.

        Args:
            conversation_id: Teams conversation ID

        Returns:
            Last validation result dict, or None if not found.
        """
        if self._redis_available and self._redis_client:
            try:
                result_json = await self._redis_client.get(f"teams:result:{conversation_id}")
                if result_json:
                    return json.loads(result_json)
            except Exception as exc:
                _log.warning(f"Redis GET failed: {exc}. Using fallback.")

        # Fallback to in-memory
        return _fallback_teams_cache.get(f"result:{conversation_id}")

    async def set_teams_result(self, conversation_id: str, result: dict[str, Any], ttl_seconds: int = 3600) -> None:
        """Store last validation result for Teams user.

        Args:
            conversation_id: Teams conversation ID
            result: Validation result dict
            ttl_seconds: Time-to-live (default 1 hour)
        """
        try:
            result_json = json.dumps(result)
        except Exception as exc:
            _log.error(f"Failed to serialize Teams result: {exc}")
            return

        if self._redis_available and self._redis_client:
            try:
                await self._redis_client.setex(f"teams:result:{conversation_id}", ttl_seconds, result_json)
                return
            except Exception as exc:
                _log.warning(f"Redis SETEX failed: {exc}. Using fallback.")

        # Fallback to in-memory
        _fallback_teams_cache[f"result:{conversation_id}"] = result

    async def health_check(self) -> dict[str, Any]:
        """Check cache health status.

        Returns:
            Dict with status, availability, and diagnostics.
        """
        if self._redis_available and self._redis_client:
            try:
                pong = await self._redis_client.ping()
                return {
                    "status": "healthy",
                    "backend": "redis",
                    "ping": pong,
                    "fallback_validation_entries": len(_fallback_validation_cache),
                    "fallback_teams_entries": len(_fallback_teams_cache),
                }
            except Exception as exc:
                return {
                    "status": "unhealthy",
                    "backend": "redis",
                    "error": str(exc),
                    "fallback_validation_entries": len(_fallback_validation_cache),
                    "fallback_teams_entries": len(_fallback_teams_cache),
                }
        else:
            return {
                "status": "using_fallback",
                "backend": "in-memory",
                "warning": "Redis not available. Data will be lost on restart.",
                "fallback_validation_entries": len(_fallback_validation_cache),
                "fallback_teams_entries": len(_fallback_teams_cache),
            }

    # ────────────────────────────────────────────────────────────────────────
    # Synchronous fallback methods — for sync code paths that can't await
    # These bypass Redis entirely and use in-memory fallback dicts directly.
    # ────────────────────────────────────────────────────────────────────────

    def get_validation_sync(self, key: str) -> dict[str, Any] | None:
        """[SYNC] Retrieve cached validation result from in-memory fallback only."""
        if key in _fallback_validation_cache:
            expire_ts, result = _fallback_validation_cache[key]
            if time.monotonic() < expire_ts:
                return result
            else:
                del _fallback_validation_cache[key]  # Evict expired
        return None

    def set_validation_sync(self, key: str, result: dict[str, Any], ttl_seconds: int) -> None:
        """[SYNC] Store validation result in in-memory fallback only."""
        try:
            # Validate JSON serializable to ensure it's cacheable
            json.dumps(result)
        except Exception as exc:
            _log.error(f"Failed to serialize validation result: {exc}")
            return

        expire_ts = time.monotonic() + ttl_seconds
        _fallback_validation_cache[key] = (expire_ts, result)


# Global singleton instance
_cache_manager: Optional[CacheManager] = None


async def get_cache_manager() -> CacheManager:
    """Get or create the global cache manager instance (async)."""
    global _cache_manager
    if _cache_manager is None:
        from app.core.settings import VERCEL_KV_URL

        _cache_manager = CacheManager(redis_url=VERCEL_KV_URL)
        await _cache_manager.initialize()
    return _cache_manager


def get_cache_manager_sync() -> CacheManager:
    """Get the global cache manager instance for sync operations (no initialization).

    WARNING: This does NOT initialize Redis connection. Use only for accessing
    the in-memory fallback cache. For async operations, use get_cache_manager().
    """
    global _cache_manager
    if _cache_manager is None:
        from app.core.settings import VERCEL_KV_URL
        _cache_manager = CacheManager(redis_url=VERCEL_KV_URL)
        # Do NOT call initialize() here — sync path doesn't need it
        # Redis will be initialized lazily on first async access
    return _cache_manager
