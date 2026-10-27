from fastapi.testclient import TestClient

from events import EventBus
from tests.factories import make_config
from utils.auth import (
    MAX_FAILURES,
    SESSION_COOKIE,
    SESSION_SECONDS,
    LoginLimiter,
    credentials_match,
    make_token,
    session_secret,
    verify_token,
)
from webapp import create_app


class TestTokens:
    def test_roundtrip(self):
        secret = session_secret("u", "p")
        assert verify_token(secret, make_token(secret))

    def test_rejects_tampered_expiry(self):
        secret = session_secret("u", "p")
        _, _, sig = make_token(secret, now=0).partition(".")

        assert not verify_token(secret, f"99999999999.{sig}")

    def test_rejects_expired(self):
        secret = session_secret("u", "p")
        token = make_token(secret, now=1000)

        assert not verify_token(secret, token, now=1000 + SESSION_SECONDS + 1)

    def test_password_change_invalidates_sessions(self):
        token = make_token(session_secret("u", "old"))

        assert not verify_token(session_secret("u", "new"), token)

    def test_rejects_garbage(self):
        secret = session_secret("u", "p")
        for bad in (None, "", "abc", "x.y", "123"):
            assert not verify_token(secret, bad)


class TestCredentialsMatch:
    def test_match_and_mismatch(self):
        assert credentials_match("u", "p", "u", "p")
        assert not credentials_match("u", "x", "u", "p")
        assert not credentials_match("x", "p", "u", "p")

    def test_non_ascii_input_does_not_raise(self):
        assert not credentials_match("ü", "påss", "u", "p")


class TestLimiter:
    def test_locks_after_max_failures_and_expires(self):
        now = [0.0]
        limiter = LoginLimiter(clock=lambda: now[0])

        for _ in range(MAX_FAILURES - 1):
            limiter.record_failure("ip")
        assert limiter.retry_after("ip") == 0

        limiter.record_failure("ip")
        assert limiter.retry_after("ip") > 0

        now[0] += 16 * 60
        assert limiter.retry_after("ip") == 0

    def test_old_failures_age_out(self):
        now = [0.0]
        limiter = LoginLimiter(clock=lambda: now[0])

        for _ in range(MAX_FAILURES - 1):
            limiter.record_failure("ip")
        now[0] += 16 * 60
        limiter.record_failure("ip")

        assert limiter.retry_after("ip") == 0

    def test_success_resets(self):
        limiter = LoginLimiter()
        for _ in range(MAX_FAILURES - 1):
            limiter.record_failure("ip")
        limiter.reset("ip")
        limiter.record_failure("ip")

        assert limiter.retry_after("ip") == 0

    def test_clients_are_independent(self):
        limiter = LoginLimiter()
        for _ in range(MAX_FAILURES):
            limiter.record_failure("a")

        assert limiter.retry_after("a") > 0
        assert limiter.retry_after("b") == 0


def auth_client() -> TestClient:
    config = make_config(web_username="user", web_password="pass")
    return TestClient(create_app(config, None, EventBus(), None))


class TestLoginFlow:
    def test_dashboard_redirects_to_login_when_signed_out(self):
        res = auth_client().get("/", follow_redirects=False)

        assert res.status_code == 302
        assert res.headers["location"] == "/login"

    def test_login_page_is_public(self):
        assert auth_client().get("/login").status_code == 200

    def test_api_401_has_no_basic_challenge(self):
        res = auth_client().get("/api/stats")

        assert res.status_code == 401
        assert "www-authenticate" not in res.headers

    def test_login_sets_cookie_that_grants_access(self):
        client = auth_client()

        res = client.post("/api/login", json={"username": "user", "password": "pass"})

        assert res.status_code == 200
        cookie = res.headers["set-cookie"].lower()
        assert SESSION_COOKIE in cookie
        assert "httponly" in cookie
        assert "samesite=lax" in cookie
        assert client.get("/", follow_redirects=False).status_code == 200
        assert client.get("/login", follow_redirects=False).status_code == 302

    def test_wrong_password_rejected(self):
        client = auth_client()

        res = client.post("/api/login", json={"username": "user", "password": "nope"})

        assert res.status_code == 401
        assert SESSION_COOKIE not in res.headers.get("set-cookie", "")

    def test_logout_clears_session(self):
        client = auth_client()
        client.post("/api/login", json={"username": "user", "password": "pass"})

        client.post("/api/logout")

        assert client.get("/", follow_redirects=False).status_code == 302

    def test_secure_flag_behind_https_proxy(self):
        res = auth_client().post(
            "/api/login", json={"username": "user", "password": "pass"},
            headers={"x-forwarded-proto": "https"},
        )

        assert "secure" in res.headers["set-cookie"].lower()

    def test_lockout_after_repeated_failures(self):
        client = auth_client()

        for _ in range(MAX_FAILURES):
            client.post("/api/login", json={"username": "user", "password": "bad"})
        res = client.post("/api/login", json={"username": "user", "password": "pass"})

        assert res.status_code == 429
        assert int(res.headers["retry-after"]) > 0

    def test_wrong_basic_credentials_count_toward_lockout(self):
        client = auth_client()

        for _ in range(MAX_FAILURES):
            client.get("/api/stats", auth=("user", "bad"))
        res = client.get("/api/stats", auth=("user", "pass"))

        assert res.status_code == 429

    def test_basic_auth_still_works_for_scripts(self):
        res = auth_client().get("/api/config", auth=("user", "pass"))

        assert res.status_code == 200

    def test_no_login_needed_when_auth_disabled(self):
        client = TestClient(create_app(make_config(), None, EventBus(), None))

        assert client.get("/", follow_redirects=False).status_code == 200
        assert client.get("/login", follow_redirects=False).status_code == 302


class TestWebSocketAuth:
    def test_rejected_without_session(self):
        import pytest
        from starlette.websockets import WebSocketDisconnect

        with pytest.raises(WebSocketDisconnect):
            with auth_client().websocket_connect("/ws"):
                pass

    def test_accepted_with_session_cookie(self):
        client = auth_client()
        client.post("/api/login", json={"username": "user", "password": "pass"})

        with client.websocket_connect("/ws"):
            pass
