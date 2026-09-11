"""本机单进程登录限流：先预留次数，再执行耗资源的密码校验。"""
from collections import deque
from hashlib import sha256
from math import ceil
from threading import Lock
from time import monotonic


LOGIN_WINDOW_SECONDS = 60
LOGIN_ACCOUNT_LIMIT = 5
LOGIN_GLOBAL_LIMIT = 20


class LoginRateLimiter:
    def __init__(self, *, clock=monotonic):
        self._clock = clock
        self._lock = Lock()
        self._global: deque[float] = deque()
        self._accounts: dict[str, deque[float]] = {}

    def reserve(self, username: str) -> int:
        # 不查询账户是否存在；不保存密码、原始用户名或客户端声称的 IP。
        key = sha256(username.encode("utf-8")).hexdigest()
        with self._lock:
            now = self._clock()
            cutoff = now - LOGIN_WINDOW_SECONDS
            while self._global and self._global[0] <= cutoff:
                self._global.popleft()
            for actor, attempts in list(self._accounts.items()):
                while attempts and attempts[0] <= cutoff:
                    attempts.popleft()
                if not attempts:
                    del self._accounts[actor]
            attempts = self._accounts.get(key)
            waits = []
            if len(self._global) >= LOGIN_GLOBAL_LIMIT:
                waits.append(self._global[0] + LOGIN_WINDOW_SECONDS - now)
            if attempts is not None and len(attempts) >= LOGIN_ACCOUNT_LIMIT:
                waits.append(attempts[0] + LOGIN_WINDOW_SECONDS - now)
            if waits:
                return max(1, ceil(max(waits)))
            # 总次数限制也限制活跃账户键数量，不能靠随机用户名无限增长。
            self._global.append(now)
            self._accounts.setdefault(key, deque()).append(now)
            return 0
