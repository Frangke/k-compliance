import hashlib
import re
from datetime import UTC, datetime, timedelta

from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.auth import PasswordHistory, RefreshToken
from app.models.user import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# --- Password hashing ---


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# --- Password policy (ISMS-P 2.5.4) ---


def validate_password_policy(password: str) -> str | None:
    """Returns error message if policy violated, None if OK."""
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        return f"비밀번호는 최소 {settings.PASSWORD_MIN_LENGTH}자 이상이어야 합니다"

    if settings.PASSWORD_REQUIRE_COMPLEXITY:
        categories = 0
        if re.search(r"[a-z]", password):
            categories += 1
        if re.search(r"[A-Z]", password):
            categories += 1
        if re.search(r"\d", password):
            categories += 1
        if re.search(r"[^a-zA-Z0-9]", password):
            categories += 1
        if categories < 3:
            return "영문 대/소문자, 숫자, 특수문자 중 3종 이상 조합이 필요합니다"

    return None


async def check_password_history(db: AsyncSession, user_id: int, new_password: str) -> bool:
    """Returns True if password was recently used (violation)."""
    result = await db.execute(
        select(PasswordHistory)
        .where(PasswordHistory.user_id == user_id)
        .order_by(PasswordHistory.created_at.desc())
        .limit(settings.PASSWORD_HISTORY_COUNT)
    )
    for history in result.scalars():
        if verify_password(new_password, history.password_hash):
            return True
    return False


async def save_password_history(db: AsyncSession, user_id: int, password_hash: str):
    db.add(PasswordHistory(user_id=user_id, password_hash=password_hash))


# --- Account lockout (ISMS-P 2.5.3) ---


def is_account_locked(user: User) -> tuple[bool, int]:
    """Returns (is_locked, remaining_seconds)."""
    if user.locked_until and user.locked_until > datetime.now(UTC):
        remaining = int((user.locked_until - datetime.now(UTC)).total_seconds())
        return True, remaining
    return False, 0


async def handle_login_failure(db: AsyncSession, user: User):
    user.failed_login_count += 1
    if user.failed_login_count >= settings.MAX_LOGIN_ATTEMPTS:
        user.locked_until = datetime.now(UTC) + timedelta(minutes=settings.LOCKOUT_DURATION_MINUTES)
    await db.commit()


async def reset_login_failure(db: AsyncSession, user: User):
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = datetime.now(UTC)
    await db.commit()


# --- JWT tokens ---


def create_access_token(user_id: int, role: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "role": role, "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: int) -> str:
    expire = datetime.now(UTC) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {"sub": str(user_id), "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except Exception:
        return None


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# --- Refresh token DB management ---


async def store_refresh_token(db: AsyncSession, user_id: int, token: str):
    expires_at = datetime.now(UTC) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    db.add(
        RefreshToken(
            user_id=user_id,
            token_hash=hash_token(token),
            expires_at=expires_at,
        )
    )
    await db.commit()


async def validate_refresh_token(db: AsyncSession, token: str) -> RefreshToken | None:
    token_hash = hash_token(token)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > func.now(),
        )
    )
    return result.scalar_one_or_none()


async def revoke_refresh_token(db: AsyncSession, token_record: RefreshToken):
    token_record.revoked_at = datetime.now(UTC)
    await db.commit()
