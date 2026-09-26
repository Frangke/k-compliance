from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.user import User
from app.schemas.user import AdminPasswordReset, UserCreate, UserListResponse, UserResponse, UserUpdate
from app.services.audit import log_audit
from app.services.auth_service import hash_password, validate_password_policy

router = APIRouter(prefix="/api/users", tags=["users"])

_cpo_only = require_role(["cpo"])


@router.get("", response_model=UserListResponse)
async def list_users(
    role: str | None = None,
    department: str | None = None,
    is_active: bool | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(_cpo_only),
    db: AsyncSession = Depends(get_db),
):
    q = select(User)
    count_q = select(func.count()).select_from(User)

    if role:
        q = q.where(User.role == role)
        count_q = count_q.where(User.role == role)
    if department:
        q = q.where(User.department == department)
        count_q = count_q.where(User.department == department)
    if is_active is not None:
        q = q.where(User.is_active == is_active)
        count_q = count_q.where(User.is_active == is_active)

    total = (await db.execute(count_q)).scalar()
    result = await db.execute(q.order_by(User.id).offset((page - 1) * size).limit(size))
    return UserListResponse(items=result.scalars().all(), total=total)


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(
    body: UserCreate,
    request: Request,
    current_user: User = Depends(_cpo_only),
    db: AsyncSession = Depends(get_db),
):
    # Validate password policy
    error = validate_password_policy(body.password)
    if error:
        raise HTTPException(status_code=400, detail=error)

    # Check duplicate
    existing = await db.execute(select(User).where((User.username == body.username) | (User.email == body.email)))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="이미 존재하는 아이디 또는 이메일입니다")

    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        name=body.name,
        email=body.email,
        role=body.role,
        department=body.department,
    )
    db.add(user)
    await db.flush()
    await log_audit(
        db,
        current_user.id,
        "create",
        "user",
        user.id,
        new_values={"username": user.username, "email": user.email, "role": user.role, "department": user.department},
        request=request,
    )
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    current_user: User = Depends(_cpo_only),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    return user


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    body: UserUpdate,
    request: Request,
    current_user: User = Depends(_cpo_only),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

    changes = body.model_dump(exclude_unset=True)
    old_values = {k: getattr(user, k) for k in changes.keys()}
    for field, value in changes.items():
        setattr(user, field, value)
    await log_audit(
        db, current_user.id, "update", "user", user.id, old_values=old_values, new_values=changes, request=request
    )
    await db.commit()
    await db.refresh(user)
    return user


@router.put("/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    body: AdminPasswordReset,
    request: Request,
    current_user: User = Depends(_cpo_only),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

    error = validate_password_policy(body.new_password)
    if error:
        raise HTTPException(status_code=400, detail=error)

    user.password_hash = hash_password(body.new_password)
    user.password_changed_at = datetime.now(UTC)
    await log_audit(
        db,
        current_user.id,
        "password.reset",
        "user",
        user.id,
        new_values={"target_username": user.username},
        request=request,
    )
    await db.commit()
    return {"message": f"{user.username}의 비밀번호가 초기화되었습니다"}


@router.delete("/{user_id}")
async def deactivate_user(
    user_id: int,
    request: Request,
    current_user: User = Depends(_cpo_only),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

    # Prevent deactivating the last CPO
    if user.role == "cpo":
        count = (
            await db.execute(select(func.count()).select_from(User).where(User.role == "cpo", User.is_active == True))
        ).scalar()
        if count <= 1:
            raise HTTPException(status_code=400, detail="마지막 CPO 계정은 비활성화할 수 없습니다")

    user.is_active = False
    await log_audit(
        db,
        current_user.id,
        "delete",
        "user",
        user.id,
        new_values={"username": user.username, "action_type": "deactivate"},
        request=request,
    )
    await db.commit()
    return {"message": f"{user.username} 계정이 비활성화되었습니다"}
