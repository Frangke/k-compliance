"""Shared fixtures for backend smoke tests.

Tests use the live development database, not an isolated one. Rationale:
- We're validating actual HTTP+SQL paths, not abstract unit logic.
- Test scope is "does the endpoint behave correctly end-to-end" not
  "try every possible state permutation," so the data left behind is
  small and named.
- Each test cleans up its own rows. Anything it can't easily clean up
  (e.g. audit_logs written by log_audit) is tagged in metadata
  ("pytest:" prefix) so it's visible and removable manually.

If we ever need hermetic isolation (for running in CI on a shared host),
switch to a dedicated `kcompliance_test` DB or a SAVEPOINT-per-test
pattern. Not worth the complexity yet.
"""

import asyncio
import os

import pytest
import pytest_asyncio
from app.database import async_session
from app.main import app
from app.models.user import User
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture(scope="session")
async def client() -> AsyncClient:
    """Shared HTTP client for the whole test session.

    Session-scoped so login cookies can persist across tests (see
    cpo_cookies below — each test doing its own login would collide
    on refresh_tokens.token_hash when the JWT `exp` claim resolves
    to the same second).
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest_asyncio.fixture
async def anon_client() -> AsyncClient:
    """Per-test, unauthenticated client — for 401/403 path tests.

    The session-scoped `client` above carries cookies from the CPO
    login, so it's useless for testing "unauthenticated caller is
    rejected" cases.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest_asyncio.fixture(scope="session")
async def cpo_cookies(client: AsyncClient) -> dict:
    """Log in as the seeded admin (CPO) and return the cookie jar.

    The password ships from a local .env override so CI can point at a
    fresh test user without leaking real credentials. Falls back to the
    dev default.
    """
    username = os.getenv("TEST_ADMIN_USERNAME", "admin")
    password = os.getenv("TEST_ADMIN_PASSWORD", "Admin1234!")

    # Make sure the account isn't locked from prior failed test runs.
    async with async_session() as db:
        from sqlalchemy import select, update

        u = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
        if u and (u.failed_login_count or u.locked_until):
            await db.execute(update(User).where(User.id == u.id).values(failed_login_count=0, locked_until=None))
            await db.commit()

    res = await client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert res.status_code == 200, f"login failed: {res.status_code} {res.text}"
    return dict(res.cookies)


@pytest.fixture(scope="session")
def event_loop():
    # pytest-asyncio default per-function loop closes the asyncpg pool
    # between tests, which causes "Event loop is closed" noise. Use a
    # session-scoped loop so the shared engine keeps working.
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
