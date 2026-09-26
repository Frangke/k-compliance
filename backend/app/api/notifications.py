from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.notification import Notification
from app.models.user import User

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Notification).where((Notification.user_id == current_user.id) | (Notification.user_id.is_(None)))
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar()
    result = await db.execute(
        q.order_by(Notification.is_read, Notification.created_at.desc()).offset((page - 1) * size).limit(size)
    )
    notifications = result.scalars().all()
    unread = (
        await db.execute(
            select(func.count())
            .select_from(Notification)
            .where(
                ((Notification.user_id == current_user.id) | (Notification.user_id.is_(None))),
                Notification.is_read == False,
            )
        )
    ).scalar()

    return {
        "items": [
            {
                "id": n.id,
                "type": n.type,
                "title": n.title,
                "message": n.message,
                "entity_type": n.entity_type,
                "entity_id": n.entity_id,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notifications
        ],
        "total": total,
        "unread": unread,
    }


@router.put("/{notification_id}/read")
async def mark_read(
    notification_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    n = (await db.execute(select(Notification).where(Notification.id == notification_id))).scalar_one_or_none()
    if n:
        n.is_read = True
        await db.commit()
    return {"message": "읽음 처리되었습니다"}
