from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.dependencies import get_current_user
from app.models.user import User
from app.services.ai_service import categorize_media, recommend_media, enrich_metadata

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai", tags=["ai"])


class CategorizeRequest(BaseModel):
    title: str
    filename: str
    genre_hints: list[str] | None = None


class RecommendRequest(BaseModel):
    recently_watched: list[str]
    available_titles: list[str]


class EnrichRequest(BaseModel):
    title: str
    filename: str
    existing_metadata: dict | None = None


@router.post("/categorize")
async def ai_categorize(req: CategorizeRequest, user: User = Depends(get_current_user)):
    logger.debug("AI categorize: title=%s filename=%s genre_hints=%s user=%s", req.title, req.filename, req.genre_hints, user.username)
    result = await categorize_media(req.title, req.filename, req.genre_hints)
    logger.info("AI categorize result for '%s': %s", req.title, result)
    return {"success": True, "result": result}


@router.post("/recommend")
async def ai_recommend(req: RecommendRequest, user: User = Depends(get_current_user)):
    logger.debug("AI recommend: watched=%d available=%d user=%s", len(req.recently_watched), len(req.available_titles), user.username)
    result = await recommend_media(req.recently_watched, req.available_titles)
    logger.info("AI recommend result count: %d for user=%s", len(result) if isinstance(result, list) else 0, user.username)
    return {"success": True, "result": result}


@router.post("/enrich")
async def ai_enrich(req: EnrichRequest, user: User = Depends(get_current_user)):
    logger.debug("AI enrich: title=%s filename=%s user=%s", req.title, req.filename, user.username)
    result = await enrich_metadata(req.title, req.filename, req.existing_metadata)
    logger.info("AI enrich result for '%s': %s", req.title, result)
    return {"success": True, "result": result}
