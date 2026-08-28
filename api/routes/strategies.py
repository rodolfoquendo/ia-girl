from datetime import datetime, timezone
from typing import Optional, List
import random

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Strategy, Post, PostMedia, PostStatus, Network, MediaType

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class StrategyIn(BaseModel):
    character_id: Optional[int] = None
    name: str
    goal: Optional[str] = None
    tone: Optional[str] = None
    mix_photos: int = 3
    mix_carousels: int = 1
    mix_videos: int = 1
    mix_tweets: int = 1
    mix_blogs: int = 0
    topics: Optional[List[str]] = None
    scene_guidelines: Optional[str] = None
    hashtags: Optional[List[str]] = None
    best_days: Optional[List[str]] = None
    best_times_utc: Optional[List[str]] = None
    notes: Optional[str] = None
    is_active: bool = True


class StrategyOut(BaseModel):
    id: int
    character_id: Optional[int]
    name: str
    goal: Optional[str]
    tone: Optional[str]
    mix_photos: int
    mix_carousels: int
    mix_videos: int
    mix_tweets: int
    mix_blogs: int
    topics: Optional[List[str]]
    scene_guidelines: Optional[str]
    hashtags: Optional[List[str]]
    best_days: Optional[List[str]]
    best_times_utc: Optional[List[str]]
    notes: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class GeneratePostIn(BaseModel):
    post_type: str = "auto"   # photo | carousel | video | tweet | blog | auto
    topic: Optional[str] = None  # None = AI picks from strategy topics
    slides: int = 3              # for carousel only


# ── Helpers ───────────────────────────────────────────────────────────────────

_TYPE_TO_NETWORK = {
    "photo":    Network.instagram,
    "carousel": Network.instagram,
    "video":    Network.instagram,
    "tweet":    Network.twitter,
    "blog":     Network.wordpress,
}
_TYPE_TO_MEDIA = {
    "photo":    MediaType.photo,
    "carousel": MediaType.photo,
    "video":    MediaType.video,
    "tweet":    MediaType.photo,
    "blog":     MediaType.photo,
}


def _pick_post_type(strategy: Strategy) -> str:
    pool = (
        ["photo"] * strategy.mix_photos +
        ["carousel"] * strategy.mix_carousels +
        ["video"] * strategy.mix_videos +
        ["tweet"] * strategy.mix_tweets +
        ["blog"] * strategy.mix_blogs
    )
    return random.choice(pool) if pool else "photo"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=List[StrategyOut])
def list_strategies(character_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(Strategy)
    if character_id is not None:
        q = q.filter(Strategy.character_id == character_id)
    return q.order_by(Strategy.created_at.desc()).all()


@router.post("", response_model=StrategyOut, status_code=201)
def create_strategy(body: StrategyIn, db: Session = Depends(get_db)):
    s = Strategy(**body.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@router.get("/{strategy_id}", response_model=StrategyOut)
def get_strategy(strategy_id: int, db: Session = Depends(get_db)):
    s = db.get(Strategy, strategy_id)
    if not s:
        raise HTTPException(404, "Strategy not found")
    return s


@router.patch("/{strategy_id}", response_model=StrategyOut)
def update_strategy(strategy_id: int, body: StrategyIn, db: Session = Depends(get_db)):
    s = db.get(Strategy, strategy_id)
    if not s:
        raise HTTPException(404, "Strategy not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(s, field, value)
    db.commit()
    db.refresh(s)
    return s


@router.delete("/{strategy_id}", status_code=204)
def delete_strategy(strategy_id: int, db: Session = Depends(get_db)):
    s = db.get(Strategy, strategy_id)
    if not s:
        raise HTTPException(404, "Strategy not found")
    db.delete(s)
    db.commit()


@router.post("/{strategy_id}/generate-post")
def generate_post_from_strategy(
    strategy_id: int,
    body: GeneratePostIn,
    db: Session = Depends(get_db),
):
    """Generate a new post (scene + PostMedia slots) based on the strategy."""
    from core.character import load as load_char
    from core.content_gen import generate_scene_from_strategy

    s = db.get(Strategy, strategy_id)
    if not s:
        raise HTTPException(404, "Strategy not found")

    post_type = body.post_type if body.post_type != "auto" else _pick_post_type(s)

    # Pick topic
    topics = s.topics or []
    topic = body.topic or (random.choice(topics) if topics else "lifestyle moment")

    # Load character for scene generation
    char = None
    if s.character_id:
        try:
            char = load_char(s.character_id)
        except Exception:
            pass

    scene = generate_scene_from_strategy(s.__dict__, topic, post_type, char)

    network = _TYPE_TO_NETWORK.get(post_type, Network.instagram)
    media_type = _TYPE_TO_MEDIA.get(post_type, MediaType.photo)

    post = Post(
        character_id=s.character_id,
        scene=scene,
        mood=s.tone or "casual",
        network=network,
        media_type=media_type,
        status=PostStatus.pending,
    )
    db.add(post)
    db.flush()

    # Add PostMedia slots
    slides = body.slides if post_type == "carousel" else 1
    for i in range(slides):
        db.add(PostMedia(post_id=post.id, position=i, file_type=media_type, prompt=scene))

    db.commit()
    db.refresh(post)

    return {
        "post_id": post.id,
        "post_type": post_type,
        "topic": topic,
        "scene": scene,
        "network": network,
        "slides": slides,
    }
