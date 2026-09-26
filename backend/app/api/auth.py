from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.user import ChangePasswordRequest, LoginRequest, UserResponse
from app.services import auth_service
from app.services.audit import log_audit

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == body.username, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        # Unknown user — log the failed attempt with the attempted username for audit trail
        await log_audit(
            db,
            None,
            "login.failure",
            "user",
            None,
            new_values={"username": body.username, "reason": "unknown_user"},
            request=request,
        )
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="아이디 또는 비밀번호가 올바르지 않습니다")

    # Account lockout check
    locked, remaining = auth_service.is_account_locked(user)
    if locked:
        await log_audit(
            db,
            user.id,
            "login.failure",
            "user",
            user.id,
            new_values={"reason": "locked", "remaining_seconds": remaining},
            request=request,
        )
        await db.commit()
        raise HTTPException(
            status_code=423,
            detail=f"계정이 잠겼습니다. {remaining}초 후 다시 시도해주세요",
        )

    # Password verification
    if not auth_service.verify_password(body.password, user.password_hash):
        await auth_service.handle_login_failure(db, user)  # commits internally
        # Separate transaction for the audit trail; acceptable since both are monotonic
        await log_audit(
            db,
            user.id,
            "login.failure",
            "user",
            user.id,
            new_values={"reason": "wrong_password", "failed_count": user.failed_login_count},
            request=request,
        )
        await db.commit()
        remaining_attempts = max(0, settings.MAX_LOGIN_ATTEMPTS - user.failed_login_count)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"아이디 또는 비밀번호가 올바르지 않습니다 (남은 시도: {remaining_attempts}회)",
        )

    # Success — reset failure count (commits internally)
    await auth_service.reset_login_failure(db, user)

    # Issue tokens
    access_token = auth_service.create_access_token(user.id, user.role)
    refresh_token = auth_service.create_refresh_token(user.id)
    await auth_service.store_refresh_token(db, user.id, refresh_token)

    await log_audit(db, user.id, "login.success", "user", user.id, request=request)
    await db.commit()

    # Set httpOnly cookies
    response.set_cookie(
        "access_token",
        access_token,
        httponly=True,
        samesite="strict",
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        "refresh_token",
        refresh_token,
        httponly=True,
        samesite="strict",
        path="/api/auth",
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )

    return {"message": "로그인 성공", "user": UserResponse.model_validate(user)}


@router.post("/refresh")
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="리프레시 토큰이 없습니다")

    # Validate refresh token
    payload = auth_service.decode_token(token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 리프레시 토큰입니다")

    token_record = await auth_service.validate_refresh_token(db, token)
    if not token_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="리프레시 토큰이 만료되었거나 무효화되었습니다"
        )

    # Rotation: revoke old, issue new
    await auth_service.revoke_refresh_token(db, token_record)

    user_id = int(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="사용자를 찾을 수 없습니다")

    new_access = auth_service.create_access_token(user.id, user.role)
    new_refresh = auth_service.create_refresh_token(user.id)
    await auth_service.store_refresh_token(db, user.id, new_refresh)

    await log_audit(db, user.id, "auth.refresh", "user", user.id, request=request)
    await db.commit()

    response.set_cookie(
        "access_token",
        new_access,
        httponly=True,
        samesite="strict",
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        "refresh_token",
        new_refresh,
        httponly=True,
        samesite="strict",
        path="/api/auth",
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )

    return {"message": "토큰 갱신 성공"}


@router.post("/logout")
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    token = request.cookies.get("refresh_token")
    logged_out_user_id: int | None = None
    if token:
        token_record = await auth_service.validate_refresh_token(db, token)
        if token_record:
            logged_out_user_id = token_record.user_id
            await auth_service.revoke_refresh_token(db, token_record)

    await log_audit(db, logged_out_user_id, "logout", "user", logged_out_user_id, request=request)
    await db.commit()

    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token", path="/api/auth")
    return {"message": "로그아웃 성공"}


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify current password
    if not auth_service.verify_password(body.current_password, current_user.password_hash):
        await log_audit(
            db,
            current_user.id,
            "password.change.failure",
            "user",
            current_user.id,
            new_values={"reason": "wrong_current"},
            request=request,
        )
        await db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="현재 비밀번호가 올바르지 않습니다")

    # Validate new password policy
    error = auth_service.validate_password_policy(body.new_password)
    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    # Check password history
    if await auth_service.check_password_history(db, current_user.id, body.new_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"최근 {settings.PASSWORD_HISTORY_COUNT}개 비밀번호와 동일한 비밀번호는 사용할 수 없습니다",
        )

    # Save old password to history, update password
    await auth_service.save_password_history(db, current_user.id, current_user.password_hash)
    current_user.password_hash = auth_service.hash_password(body.new_password)
    current_user.password_changed_at = datetime.now(UTC)
    await log_audit(db, current_user.id, "password.change", "user", current_user.id, request=request)
    await db.commit()

    return {"message": "비밀번호가 변경되었습니다"}
