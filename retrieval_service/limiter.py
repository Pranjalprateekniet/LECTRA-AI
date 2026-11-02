"""IP-based rate limiting and abuse protection for the hosted retrieval API."""

import ipaddress
import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from fastapi import Request

logger = logging.getLogger("retrieval_service.limiter")


def _is_ip_in_trusted(ip_str: str, trusted_list: List[str]) -> bool:
    """Check whether an IP address matches the trusted list (exact IP, CIDR, or '*')."""
    if "*" in trusted_list:
        return True
    clean_ip = ip_str.strip()
    try:
        parsed_ip = ipaddress.ip_address(clean_ip)
    except ValueError:
        return False

    for trusted in trusted_list:
        trusted_clean = trusted.strip()
        if not trusted_clean:
            continue
        try:
            if "/" in trusted_clean:
                if parsed_ip in ipaddress.ip_network(trusted_clean, strict=False):
                    return True
            elif parsed_ip == ipaddress.ip_address(trusted_clean):
                return True
        except ValueError:
            continue
    return False


def get_client_ip(request: Request, trusted_proxies: List[str]) -> str:
    """Extract and verify client IP address behind trusted reverse proxies.

    Never blindly trusts arbitrary X-Forwarded-For headers. Only trusts X-Forwarded-For
    if the immediate direct peer IP is in trusted_proxies.
    Traverses the proxy chain from right to left, stopping at the first untrusted IP.
    """
    direct_peer = request.client.host if request.client else "127.0.0.1"

    # If the direct peer is not a trusted proxy, use direct peer IP
    if not _is_ip_in_trusted(direct_peer, trusted_proxies):
        return direct_peer

    # Peer is trusted: inspect X-Forwarded-For header
    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded:
        return direct_peer

    # Split and parse IPs in header
    ip_chain = [ip.strip() for ip in forwarded.split(",") if ip.strip()]
    if not ip_chain:
        return direct_peer

    # Walk backwards from right to left
    # Skip any proxy IPs that are trusted; the first untrusted IP from the right is the client
    for ip in reversed(ip_chain):
        if not _is_ip_in_trusted(ip, trusted_proxies):
            return ip

    # If all entries in X-Forwarded-For are trusted, fall back to leftmost
    return ip_chain[0]


@dataclass
class RateLimitResult:
    """Result of rate limit validation."""

    allowed: bool
    retry_after_seconds: int
    limit_minute: int
    remaining_minute: int
    limit_hour: int
    remaining_hour: int

    @property
    def headers(self) -> Dict[str, str]:
        """Generate standard HTTP rate limit headers."""
        hdr = {
            "X-RateLimit-Limit-Minute": str(self.limit_minute),
            "X-RateLimit-Remaining-Minute": str(max(0, self.remaining_minute)),
            "X-RateLimit-Limit-Hour": str(self.limit_hour),
            "X-RateLimit-Remaining-Hour": str(max(0, self.remaining_hour)),
        }
        if not self.allowed:
            hdr["Retry-After"] = str(max(1, self.retry_after_seconds))
        return hdr


class BaseRateLimiter(ABC):
    """Abstract interface for rate limiters."""

    @abstractmethod
    def check_rate_limit(self, ip: str) -> RateLimitResult:
        """Check and record a request for the given client IP."""
        raise NotImplementedError

    @abstractmethod
    def reset(self) -> None:
        """Clear all stored rate limit records (primarily for testing)."""
        raise NotImplementedError


class MemoryRateLimiter(BaseRateLimiter):
    """Thread-safe in-memory sliding-window rate limiter.

    Maintains request timestamps per IP across 60-second and 3600-second windows.
    Automatically purges expired records periodically to prevent unbounded memory growth.
    """

    def __init__(
        self,
        rate_limit_per_minute: int = 10,
        rate_limit_per_hour: int = 100,
    ) -> None:
        self.limit_minute = rate_limit_per_minute
        self.limit_hour = rate_limit_per_hour
        self._records: Dict[str, List[float]] = {}
        self._lock = threading.Lock()
        self._last_cleanup = time.time()

    def _cleanup_stale_ips(self, now: float) -> None:
        """Purge records for IPs that have had no activity for over an hour."""
        if now - self._last_cleanup < 300:  # Clean every 5 minutes
            return
        self._last_cleanup = now
        cutoff = now - 3600
        stale = [
            ip
            for ip, timestamps in self._records.items()
            if not timestamps or timestamps[-1] < cutoff
        ]
        for ip in stale:
            self._records.pop(ip, None)

    def check_rate_limit(self, ip: str) -> RateLimitResult:
        now = time.time()
        with self._lock:
            self._cleanup_stale_ips(now)
            timestamps = self._records.setdefault(ip, [])

            # Prune timestamps older than 1 hour (3600 seconds)
            one_hour_ago = now - 3600
            one_minute_ago = now - 60

            # Binary search or list comprehension
            timestamps = [t for t in timestamps if t > one_hour_ago]
            self._records[ip] = timestamps

            # Count in 1 minute and 1 hour windows
            count_minute = sum(1 for t in timestamps if t > one_minute_ago)
            count_hour = len(timestamps)

            # Check minute limit
            if count_minute >= self.limit_minute:
                # Find oldest timestamp in the 1-minute window
                minute_timestamps = [t for t in timestamps if t > one_minute_ago]
                oldest_in_minute = minute_timestamps[0] if minute_timestamps else now
                retry_after = int(60 - (now - oldest_in_minute)) + 1
                return RateLimitResult(
                    allowed=False,
                    retry_after_seconds=max(1, retry_after),
                    limit_minute=self.limit_minute,
                    remaining_minute=0,
                    limit_hour=self.limit_hour,
                    remaining_hour=max(0, self.limit_hour - count_hour),
                )

            # Check hour limit
            if count_hour >= self.limit_hour:
                oldest_in_hour = timestamps[0] if timestamps else now
                retry_after = int(3600 - (now - oldest_in_hour)) + 1
                return RateLimitResult(
                    allowed=False,
                    retry_after_seconds=max(1, retry_after),
                    limit_minute=self.limit_minute,
                    remaining_minute=max(0, self.limit_minute - count_minute),
                    limit_hour=self.limit_hour,
                    remaining_hour=0,
                )

            # Allowed: record request timestamp
            timestamps.append(now)

            return RateLimitResult(
                allowed=True,
                retry_after_seconds=0,
                limit_minute=self.limit_minute,
                remaining_minute=max(0, self.limit_minute - count_minute - 1),
                limit_hour=self.limit_hour,
                remaining_hour=max(0, self.limit_hour - count_hour - 1),
            )

    def reset(self) -> None:
        with self._lock:
            self._records.clear()


class RedisRateLimiter(BaseRateLimiter):
    """Production Redis-backed sliding-window rate limiter.

    Uses Redis Sorted Sets (ZSET) with millisecond timestamps to enforce
    distributed rate limits across multiple horizontally scaled service instances.
    """

    def __init__(
        self,
        redis_url: str,
        rate_limit_per_minute: int = 10,
        rate_limit_per_hour: int = 100,
    ) -> None:
        self.redis_url = redis_url
        self.limit_minute = rate_limit_per_minute
        self.limit_hour = rate_limit_per_hour
        self._client: Any = None
        self._fallback_memory = MemoryRateLimiter(
            rate_limit_per_minute=rate_limit_per_minute,
            rate_limit_per_hour=rate_limit_per_hour,
        )
        self._init_client()

    def _init_client(self) -> None:
        try:
            import redis

            self._client = redis.Redis.from_url(self.redis_url, decode_responses=True)
            self._client.ping()
            logger.info(
                "Successfully connected to Redis for rate limiting",
                extra={"url": self.redis_url},
            )
        except Exception as exc:
            logger.warning(
                "Failed to connect to Redis; falling back to in-memory rate limiter",
                extra={"error": str(exc)},
            )
            self._client = None

    def check_rate_limit(self, ip: str) -> RateLimitResult:
        if self._client is None:
            return self._fallback_memory.check_rate_limit(ip)

        now = time.time()
        key_min = f"rl:{ip}:min"
        key_hr = f"rl:{ip}:hr"

        try:
            pipe = self._client.pipeline()
            # 1. Prune expired entries
            pipe.zremrangebyscore(key_min, 0, now - 60)
            pipe.zremrangebyscore(key_hr, 0, now - 3600)
            # 2. Count current elements
            pipe.zcard(key_min)
            pipe.zcard(key_hr)
            # 3. Get oldest entry for retry-after calculation if needed
            pipe.zrange(key_min, 0, 0, withscores=True)
            pipe.zrange(key_hr, 0, 0, withscores=True)
            results = pipe.execute()

            count_min = results[2]
            count_hr = results[3]
            oldest_min = results[4]
            oldest_hr = results[5]

            # Check minute limit
            if count_min >= self.limit_minute:
                retry_after = 60
                if oldest_min and len(oldest_min[0]) > 1:
                    retry_after = max(1, int(60 - (now - float(oldest_min[0][1]))))
                return RateLimitResult(
                    allowed=False,
                    retry_after_seconds=retry_after,
                    limit_minute=self.limit_minute,
                    remaining_minute=0,
                    limit_hour=self.limit_hour,
                    remaining_hour=max(0, self.limit_hour - count_hr),
                )

            # Check hour limit
            if count_hr >= self.limit_hour:
                retry_after = 3600
                if oldest_hr and len(oldest_hr[0]) > 1:
                    retry_after = max(1, int(3600 - (now - float(oldest_hr[0][1]))))
                return RateLimitResult(
                    allowed=False,
                    retry_after_seconds=retry_after,
                    limit_minute=self.limit_minute,
                    remaining_minute=max(0, self.limit_minute - count_min),
                    limit_hour=self.limit_hour,
                    remaining_hour=0,
                )

            # Add timestamp to both sets
            pipe = self._client.pipeline()
            now_str = str(now)
            pipe.zadd(key_min, {now_str: now})
            pipe.expire(key_min, 120)
            pipe.zadd(key_hr, {now_str: now})
            pipe.expire(key_hr, 7200)
            pipe.execute()

            return RateLimitResult(
                allowed=True,
                retry_after_seconds=0,
                limit_minute=self.limit_minute,
                remaining_minute=max(0, self.limit_minute - count_min - 1),
                limit_hour=self.limit_hour,
                remaining_hour=max(0, self.limit_hour - count_hr - 1),
            )
        except Exception as exc:
            logger.warning(
                "Redis operation failed during rate limit check; using memory fallback",
                extra={"error": str(exc)},
            )
            return self._fallback_memory.check_rate_limit(ip)

    def reset(self) -> None:
        if self._client:
            try:
                keys = self._client.keys("rl:*")
                if keys:
                    self._client.delete(*keys)
            except Exception:
                pass
        self._fallback_memory.reset()


def create_rate_limiter(
    redis_url: Optional[str] = None,
    rate_limit_per_minute: int = 10,
    rate_limit_per_hour: int = 100,
) -> BaseRateLimiter:
    """Factory creating appropriate rate limiter based on configuration."""
    if redis_url:
        return RedisRateLimiter(
            redis_url=redis_url,
            rate_limit_per_minute=rate_limit_per_minute,
            rate_limit_per_hour=rate_limit_per_hour,
        )
    return MemoryRateLimiter(
        rate_limit_per_minute=rate_limit_per_minute,
        rate_limit_per_hour=rate_limit_per_hour,
    )
