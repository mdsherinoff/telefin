import hashlib
import hmac
import time

SESSION_COOKIE = "telefin_session"
SESSION_SECONDS = 30 * 24 * 3600

MAX_FAILURES = 5
FAILURE_WINDOW_SECONDS = 15 * 60
LOCKOUT_SECONDS = 15 * 60


def session_secret(username: str, password: str) -> bytes:
    # Derived from the credentials, so sessions survive restarts (no stored
    # secret needed) and every session is invalidated the moment the
    # username or password changes.
    return hashlib.sha256(
        f"telefin-session\0{username}\0{password}".encode()
    ).digest()


def make_token(secret: bytes, now: float | None = None) -> str:
    expires = int((now if now is not None else time.time()) + SESSION_SECONDS)
    return f"{expires}.{_sign(secret, expires)}"


def verify_token(secret: bytes, token: str | None, now: float | None = None) -> bool:
    if not token:
        return False

    expires_raw, _, signature = token.partition(".")

    try:
        expires = int(expires_raw)
    except ValueError:
        return False

    if not hmac.compare_digest(signature, _sign(secret, expires)):
        return False

    return expires > (now if now is not None else time.time())


def _sign(secret: bytes, expires: int) -> str:
    return hmac.new(secret, str(expires).encode(), hashlib.sha256).hexdigest()


def credentials_match(
    username: str, password: str, expected_username: str, expected_password: str
) -> bool:
    # Encoded so non-ASCII input can't make compare_digest raise, and both
    # fields are always compared so timing doesn't reveal which was wrong.
    user_ok = hmac.compare_digest(username.encode(), expected_username.encode())
    pass_ok = hmac.compare_digest(password.encode(), expected_password.encode())
    return user_ok and pass_ok


class LoginLimiter:
    # Locks a client address out after MAX_FAILURES failed attempts within
    # FAILURE_WINDOW_SECONDS. In-memory, so a restart clears it; behind a
    # reverse proxy every client shares the proxy's address.

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._failures: dict[str, list[float]] = {}
        self._locked_until: dict[str, float] = {}

    def retry_after(self, key: str) -> int:
        # Seconds until `key` may try again; 0 when not locked out.
        remaining = self._locked_until.get(key, 0) - self._clock()

        if remaining <= 0:
            self._locked_until.pop(key, None)
            return 0

        return int(remaining) + 1

    def record_failure(self, key: str) -> None:
        now = self._clock()
        recent = [
            t for t in self._failures.get(key, [])
            if now - t < FAILURE_WINDOW_SECONDS
        ]
        recent.append(now)
        self._failures[key] = recent

        if len(recent) >= MAX_FAILURES:
            self._locked_until[key] = now + LOCKOUT_SECONDS
            self._failures.pop(key, None)

        if len(self._failures) > 1000:
            self._failures = {
                k: v for k, v in self._failures.items()
                if v and now - v[-1] < FAILURE_WINDOW_SECONDS
            }

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)
        self._locked_until.pop(key, None)
