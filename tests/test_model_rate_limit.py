from concurrent.futures import ThreadPoolExecutor

from app.agent.rate_limit import UserModelRateLimiter


def test_sliding_window_and_retry_do_not_extend_lockout():
    now = [0.0]
    limiter = UserModelRateLimiter(clock=lambda: now[0])
    for second in (0, 10, 20, 30, 40):
        now[0] = second
        assert limiter.reserve(1) == 0
    now[0] = 59.2
    assert limiter.reserve(1) == 1
    assert limiter.reserve(1) == 1
    now[0] = 60
    assert limiter.reserve(1) == 0
    assert limiter.reserve(1) == 10
    now[0] = 120
    assert limiter.reserve(2) == 0
    assert 1 not in limiter._attempts


def test_parallel_reservations_cannot_exceed_limit():
    limiter = UserModelRateLimiter(clock=lambda: 0)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(limiter.reserve, [1] * 20))
    assert results.count(0) == 5
    assert results.count(60) == 15
    assert limiter.reserve(2) == 0
