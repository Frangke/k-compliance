"""Auth endpoints — login success/failure + audit log side-effects."""

from app.database import async_session
from app.models.audit import AuditLog
from sqlalchemy import desc, select


async def test_login_success_writes_audit_log(client, cpo_cookies):
    # cpo_cookies fixture already performed a successful login.
    async with async_session() as db:
        row = (
            await db.execute(
                select(AuditLog).where(AuditLog.action == "login.success").order_by(desc(AuditLog.id)).limit(1)
            )
        ).scalar_one_or_none()
    assert row is not None
    assert row.entity_type == "user"


async def test_login_failure_unknown_user(client):
    before = await _count_logins("login.failure")
    res = await client.post(
        "/api/auth/login",
        json={"username": "definitely-not-a-real-user", "password": "x"},
    )
    assert res.status_code == 401
    after = await _count_logins("login.failure")
    assert after == before + 1


async def test_login_failure_wrong_password_increments_count(client):
    # Use a throwaway username that doesn't exist so we don't actually
    # lock the admin test account. The audit row is still produced.
    before = await _count_logins("login.failure")
    res = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "totally-wrong-password"},
    )
    assert res.status_code == 401
    # Reason is embedded in new_values but we only assert the count here.
    after = await _count_logins("login.failure")
    assert after == before + 1

    # Reset admin lockout state to keep downstream tests happy.
    async with async_session() as db:
        from app.models.user import User
        from sqlalchemy import update

        await db.execute(update(User).where(User.username == "admin").values(failed_login_count=0, locked_until=None))
        await db.commit()


async def test_me_requires_auth(anon_client):
    res = await anon_client.get("/api/auth/me")
    assert res.status_code == 401


async def test_me_returns_user(client, cpo_cookies):
    res = await client.get("/api/auth/me", cookies=cpo_cookies)
    assert res.status_code == 200
    body = res.json()
    assert body["username"] == "admin"
    assert body["role"] == "cpo"


async def _count_logins(action: str) -> int:
    async with async_session() as db:
        from sqlalchemy import func

        return (
            await db.execute(select(func.count()).select_from(AuditLog).where(AuditLog.action == action))
        ).scalar() or 0
