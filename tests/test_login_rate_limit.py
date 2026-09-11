from concurrent.futures import ThreadPoolExecutor

from app.auth.rate_limit import LoginRateLimiter


def test_account_limit_and_expiration_are_sliding_and_do_not_extend():
    now = [0.0]
    limiter = LoginRateLimiter(clock=lambda: now[0])
    for timestamp in (0, 10, 20, 30, 40):
        now[0] = timestamp
        assert limiter.reserve("alice") == 0
    now[0] = 59.2
    assert limiter.reserve("alice") == 1
    assert limiter.reserve("alice") == 1
    assert limiter.reserve("bob") == 0
    now[0] = 60
    assert limiter.reserve("alice") == 0
    assert limiter.reserve("alice") == 10
    now[0] = 120
    assert limiter.reserve("new") == 0
    assert len(limiter._accounts) == 1


def test_random_names_cannot_bypass_global_limit_or_expand_memory():
    limiter = LoginRateLimiter(clock=lambda: 0)
    assert all(limiter.reserve(f"user-{i}") == 0 for i in range(20))
    assert all(limiter.reserve(f"unknown-{i}") == 60 for i in range(100))
    assert len(limiter._accounts) == 20


def test_parallel_login_reservations_are_bounded():
    limiter = LoginRateLimiter(clock=lambda: 0)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(limiter.reserve, ["alice"] * 20))
    assert results.count(0) == 5
    assert results.count(60) == 15
