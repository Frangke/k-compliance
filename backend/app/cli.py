"""CLI utilities for K-Compliance admin operations."""

import asyncio
import secrets
import sys

from sqlalchemy import func, select

from app.database import async_session
from app.models.user import User
from app.services.auth_service import hash_password


async def create_admin(username: str, email: str):
    async with async_session() as db:
        # Check if CPO already exists
        result = await db.execute(select(func.count()).where(User.role == "cpo", User.is_active == True))
        cpo_count = result.scalar()
        if cpo_count > 0:
            print("ERROR: CPO 계정이 이미 존재합니다. 추가 사용자는 웹 UI에서 생성하세요.")
            return

        # Generate temporary password
        temp_password = secrets.token_urlsafe(12)

        user = User(
            username=username,
            password_hash=hash_password(temp_password),
            name="관리자",
            email=email,
            role="cpo",
        )
        db.add(user)
        await db.commit()
        print("CPO 계정 생성 완료:")
        print(f"  Username: {username}")
        print(f"  Password: {temp_password}")
        print("  (첫 로그인 후 비밀번호를 변경하세요)")


async def unlock_user(username: str):
    async with async_session() as db:
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        if not user:
            print(f"ERROR: 사용자 '{username}'을 찾을 수 없습니다")
            return
        user.locked_until = None
        user.failed_login_count = 0
        await db.commit()
        print(f"계정 잠금 해제 완료: {username}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m app.cli <command> [args]")
        print("Commands:")
        print("  create-admin <username> <email>")
        print("  unlock-user <username>")
        return

    command = sys.argv[1]
    if command == "create-admin":
        if len(sys.argv) != 4:
            print("Usage: python -m app.cli create-admin <username> <email>")
            return
        asyncio.run(create_admin(sys.argv[2], sys.argv[3]))
    elif command == "unlock-user":
        if len(sys.argv) != 3:
            print("Usage: python -m app.cli unlock-user <username>")
            return
        asyncio.run(unlock_user(sys.argv[2]))
    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
