"""Tests for IP extraction and sliding-window rate limiters."""


from fastapi import Request

from retrieval_service.limiter import (
    MemoryRateLimiter,
    RedisRateLimiter,
    get_client_ip,
)


def _make_mock_request(client_ip: str, headers: dict | None = None) -> Request:
    headers_list = [
        (k.lower().encode("latin1"), v.encode("latin1"))
        for k, v in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "client": (client_ip, 54321),
        "headers": headers_list,
    }
    return Request(scope)


def test_get_client_ip_direct_connection():
    req = _make_mock_request("198.51.100.5")
    ip = get_client_ip(req, trusted_proxies=["127.0.0.1"])
    assert ip == "198.51.100.5"


def test_get_client_ip_spoofed_header_from_untrusted_peer_ignored():
    # An untrusted external client connects directly and pretends to be another IP
    req = _make_mock_request("198.51.100.5", headers={"x-forwarded-for": "8.8.8.8"})
    ip = get_client_ip(req, trusted_proxies=["127.0.0.1"])
    # Must NOT trust the spoofed header; must return the actual connection IP
    assert ip == "198.51.100.5"


def test_get_client_ip_trusted_reverse_proxy():
    req = _make_mock_request("127.0.0.1", headers={"x-forwarded-for": "203.0.113.42"})
    ip = get_client_ip(req, trusted_proxies=["127.0.0.1", "::1"])
    assert ip == "203.0.113.42"


def test_get_client_ip_multi_hop_with_trusted_intermediate_proxies():
    # Chain: Client (192.0.2.1) -> Proxy1 (10.0.0.2) -> Proxy2 (127.0.0.1)
    req = _make_mock_request("127.0.0.1", headers={"x-forwarded-for": "192.0.2.1, 10.0.0.2"})
    ip = get_client_ip(req, trusted_proxies=["127.0.0.1", "10.0.0.0/8"])
    assert ip == "192.0.2.1"


def test_memory_rate_limiter_minute_window():
    limiter = MemoryRateLimiter(rate_limit_per_minute=3, rate_limit_per_hour=10)
    client_ip = "192.0.2.10"

    # 3 allowed requests
    for i in range(3):
        res = limiter.check_rate_limit(client_ip)
        assert res.allowed is True
        assert res.limit_minute == 3
        assert res.remaining_minute == 2 - i

    # 4th request must be rejected with 429 semantics
    res4 = limiter.check_rate_limit(client_ip)
    assert res4.allowed is False
    assert res4.remaining_minute == 0
    assert res4.retry_after_seconds > 0
    assert "Retry-After" in res4.headers
    assert res4.headers["X-RateLimit-Limit-Minute"] == "3"


def test_memory_rate_limiter_distinct_ips():
    limiter = MemoryRateLimiter(rate_limit_per_minute=2, rate_limit_per_hour=10)
    ip_a = "192.0.2.1"
    ip_b = "192.0.2.2"

    assert limiter.check_rate_limit(ip_a).allowed is True
    assert limiter.check_rate_limit(ip_a).allowed is True
    assert limiter.check_rate_limit(ip_a).allowed is False

    # IP B is unaffected
    assert limiter.check_rate_limit(ip_b).allowed is True
    assert limiter.check_rate_limit(ip_b).allowed is True


def test_memory_rate_limiter_hour_window():
    limiter = MemoryRateLimiter(rate_limit_per_minute=100, rate_limit_per_hour=2)
    ip = "192.0.2.30"

    assert limiter.check_rate_limit(ip).allowed is True
    assert limiter.check_rate_limit(ip).allowed is True
    res3 = limiter.check_rate_limit(ip)
    assert res3.allowed is False
    assert res3.remaining_hour == 0
    assert res3.retry_after_seconds > 0


def test_redis_rate_limiter_fallback_on_invalid_url():
    # If redis URL is unreachable, it logs a warning and falls back cleanly to memory limiter
    limiter = RedisRateLimiter(
        redis_url="redis://localhost:9999/0",
        rate_limit_per_minute=2,
        rate_limit_per_hour=10,
    )
    ip = "192.0.2.55"
    assert limiter.check_rate_limit(ip).allowed is True
    assert limiter.check_rate_limit(ip).allowed is True
    assert limiter.check_rate_limit(ip).allowed is False
