import logging
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db, async_session
from app.models.user import User
from app.dependencies import hash_password, verify_password, create_token, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: str = ""


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    token: str
    user: dict


# Pre-defined avatars — SVG initials or icon references
AVATARS = [
    "avatar-1", "avatar-2", "avatar-3", "avatar-4", "avatar-5",
    "avatar-6", "avatar-7", "avatar-8", "avatar-9", "avatar-10",
    "avatar-11", "avatar-12", "avatar-13", "avatar-14", "avatar-15",
]


@router.post("/register")
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    logger.debug("Register user: %s", req.username)
    if len(req.username) < 3 or len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Username (min 3) and password (min 8) too short")
    result = await db.execute(select(User).where(User.username == req.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username taken")
    is_admin = (await db.execute(select(User).limit(1))).first() is None
    logger.info("User registered: %s (admin=%s)", req.username, is_admin)
    user = User(
        username=req.username,
        password_hash=hash_password(req.password),
        display_name=req.display_name or req.username,
        is_admin=is_admin,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {
        "token": create_token(user.id, user.username, user.is_admin),
        "user": {"id": user.id, "username": user.username, "display_name": user.display_name, "avatar": user.avatar, "is_admin": user.is_admin},
    }


@router.post("/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    logger.debug("Login attempt: %s", req.username)
    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.password_hash):
        logger.warning("Failed login attempt: %s", req.username)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    logger.info("User logged in: %s (id=%d)", user.username, user.id)
    return {
        "token": create_token(user.id, user.username, user.is_admin),
        "user": {"id": user.id, "username": user.username, "display_name": user.display_name, "avatar": user.avatar, "is_admin": user.is_admin},
    }


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    logger.debug("Profile fetch: %s (id=%d)", user.username, user.id)
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "avatar": user.avatar,
        "is_admin": user.is_admin,
    }


class ProfileUpdate(BaseModel):
    display_name: str = ""
    avatar: str = ""


@router.post("/profile")
async def update_profile(
    req: ProfileUpdate,
    user: User = Depends(get_current_user),
):
    """Update display name and/or avatar."""
    logger.debug("Profile update: %s avatar=%s display=%s", user.username, req.avatar, req.display_name)
    if req.avatar and req.avatar not in AVATARS:
        raise HTTPException(400, "Invalid avatar selection")
    async with async_session() as db:
        u = await db.get(User, user.id)
        if not u:
            raise HTTPException(404, "User not found")
        if req.display_name:
            u.display_name = req.display_name
        if req.avatar:
            u.avatar = req.avatar
        await db.commit()
    return {"success": True, "avatar": req.avatar or user.avatar, "display_name": req.display_name or user.display_name}


@router.get("/avatars")
async def list_avatars():
    """Return the list of available pre-defined avatars."""
    return {"avatars": AVATARS}
