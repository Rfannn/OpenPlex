import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.watch_history import WatchHistory
from app.models.user import User
from app.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/history", tags=["history"])


class UpdateHistoryRequest(BaseModel):
    media_path: str
    title: str = ""
    position_sec: float = 0.0
    duration_sec: float = 0.0
    completed: bool = False


@router.post("/update")
async def update_history(req: UpdateHistoryRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    logger.debug("Update history: user=%s path=%s pos=%.1f", user.username, req.media_path, req.position_sec)
    result = await db.execute(
        select(WatchHistory).where(
            WatchHistory.user_id == user.id,
            WatchHistory.media_path == req.media_path,
        )
    )
    entry = result.scalar_one_or_none()
    if entry:
        entry.position_sec = req.position_sec
        entry.duration_sec = req.duration_sec
        entry.completed = req.completed
        entry.title = req.title or entry.title
    else:
        entry = WatchHistory(
            user_id=user.id,
            media_path=req.media_path,
            title=req.title,
            position_sec=req.position_sec,
            duration_sec=req.duration_sec,
            completed=req.completed,
        )
        db.add(entry)
        await db.commit()
    logger.info("History updated: user=%s path=%s pos=%.1f", user.username, req.media_path, req.position_sec)
    return {"success": True}


@router.get("")
async def get_history(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    logger.debug("Get history: user=%s", user.username)
    result = await db.execute(
        select(WatchHistory).where(WatchHistory.user_id == user.id).order_by(WatchHistory.last_watched.desc()).limit(100)
    )
    entries = result.scalars().all()
    logger.debug("History fetched: user=%s count=%d", user.username, len(entries))
    return {
        "success": True,
        "history": [
            {
                "media_path": e.media_path,
                "title": e.title,
                "position_sec": e.position_sec,
                "duration_sec": e.duration_sec,
                "completed": e.completed,
                "last_watched": e.last_watched.isoformat() if e.last_watched else None,
            }
            for e in entries
        ],
    }


@router.get("/{media_path:path}")
async def get_resume_point(media_path: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    logger.debug("Get resume point: user=%s path=%s", user.username, media_path)
    result = await db.execute(
        select(WatchHistory).where(
            WatchHistory.user_id == user.id,
            WatchHistory.media_path == media_path,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        logger.debug("No resume point: user=%s path=%s", user.username, media_path)
        return {"success": True, "found": False}
    return {
        "success": True,
        "found": True,
        "position_sec": entry.position_sec,
        "duration_sec": entry.duration_sec,
        "completed": entry.completed,
        "title": entry.title,
    }


@router.delete("/{media_path:path}")
async def clear_history(media_path: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    logger.debug("Clear history: user=%s path=%s", user.username, media_path)
    result = await db.execute(
        select(WatchHistory).where(
            WatchHistory.user_id == user.id,
            WatchHistory.media_path == media_path,
        )
    )
    entry = result.scalar_one_or_none()
    if entry:
        await db.delete(entry)
        await db.commit()
        logger.info("History cleared: user=%s path=%s", user.username, media_path)
    return {"success": True}
