"""单进程演示用：按真实用户限制最近 60 秒内进入模型阶段的次数。"""
from collections import deque
from math import ceil
from threading import Lock
from time import monotonic


USER_CALL_LIMIT = 5
USER_WINDOW_SECONDS = 60


class UserModelRateLimiter:
    def __init__(self, *, clock=monotonic):
        self._clock = clock
        self._lock = Lock()
        self._attempts: dict[int, deque[float]] = {}

    def reserve(self, user_id: int) -> int:
        """成功预留返回 0；超限返回至少需要等待的秒数，不延长窗口。"""
        with self._lock:
            now = self._clock()
            # 清掉不活跃用户，避免仅追加记录；当前没有开放注册。
            for actor, attempts in list(self._attempts.items()):
                while attempts and attempts[0] <= now - USER_WINDOW_SECONDS:
                    attempts.popleft()
                if not attempts:
                    del self._attempts[actor]
            attempts = self._attempts.setdefault(user_id, deque())
            if len(attempts) >= USER_CALL_LIMIT:
                return max(1, ceil(attempts[0] + USER_WINDOW_SECONDS - now))
            attempts.append(now)
            return 0
