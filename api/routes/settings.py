from datetime import datetime
from typing import Optional, Any

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.api_keys import get_key
from db.database import get_db
from db.models import PromptDefaults, PostMedia, CharacterMedia, Place, Room, Post

router = APIRouter(prefix="/api/settings", tags=["settings"])


class PromptDefaultsOut(BaseModel):
    positive: Optional[str]
    negative: Optional[str]
    style: Optional[str]
    text_provider: str = "claude"
    # Generation params
    safety_tolerance: int = 5
    output_quality: int = 90
    output_format: str = "jpg"
    prompt_upsampling: bool = False
    seed: Optional[int] = None
    aspect_ratio: str = "4:5"
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class PromptDefaultsIn(BaseModel):
    positive: Optional[str] = None
    negative: Optional[str] = None
    style: Optional[str] = None
    text_provider: Optional[str] = None
    # Generation params
    safety_tolerance: Optional[int] = None
    output_quality: Optional[int] = None
    output_format: Optional[str] = None
    prompt_upsampling: Optional[bool] = None
    seed: Optional[int] = None
    aspect_ratio: Optional[str] = None


def _get_or_create(db: Session) -> PromptDefaults:
    row = db.get(PromptDefaults, 1)
    if not row:
        row = PromptDefaults(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


@router.get("/prompt-defaults", response_model=PromptDefaultsOut)
def get_prompt_defaults(db: Session = Depends(get_db)):
    return _get_or_create(db)


@router.patch("/prompt-defaults", response_model=PromptDefaultsOut)
def update_prompt_defaults(body: PromptDefaultsIn, db: Session = Depends(get_db)):
    row = _get_or_create(db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row


# Pricing constants (approximate, update as needed)
_FLUX_COST_PER_IMAGE = 0.04          # Flux 1.1 Pro on Replicate
_EL_COST_PER_1K_CHARS = 0.30        # ElevenLabs Creator tier (~$0.30 / 1k chars)


class ImprovePromptIn(BaseModel):
    prompt: str
    provider: Optional[str] = None  # "claude" | "openai" | "grok" — None = use default


@router.post("/improve-prompt")
def improve_prompt_endpoint(body: ImprovePromptIn):
    from core.content_gen import improve_prompt
    improved = improve_prompt(body.prompt, provider=body.provider)
    return {"improved": improved}


@router.get("/usage")
def get_usage(db: Session = Depends(get_db)) -> dict[str, Any]:
    result: dict[str, Any] = {}

    # ElevenLabs — character quota from subscription endpoint
    el_key = get_key("elevenlabs")
    if el_key:
        try:
            r = httpx.get(
                "https://api.elevenlabs.io/v1/user/subscription",
                headers={"xi-api-key": el_key},
                timeout=8,
            )
            if r.status_code == 200:
                data = r.json()
                result["elevenlabs"] = {
                    "tier": data.get("tier"),
                    "character_count": data.get("character_count"),
                    "character_limit": data.get("character_limit"),
                    "next_reset_unix": data.get("next_character_count_reset_unix"),
                    "status": "ok",
                }
            else:
                result["elevenlabs"] = {"status": "error", "detail": r.text[:200]}
        except Exception as e:
            result["elevenlabs"] = {"status": "error", "detail": str(e)}
    else:
        result["elevenlabs"] = {"status": "no_key"}

    # Replicate — account info (pay-as-you-go, no credit balance API)
    rep_token = get_key("replicate")
    if rep_token:
        try:
            r = httpx.get(
                "https://api.replicate.com/v1/account",
                headers={"Authorization": f"Token {rep_token}"},
                timeout=8,
            )
            if r.status_code == 200:
                data = r.json()
                result["replicate"] = {
                    "username": data.get("username"),
                    "name": data.get("name"),
                    "type": data.get("type"),
                    "status": "ok",
                }
            else:
                result["replicate"] = {"status": "error", "detail": r.text[:200]}
        except Exception as e:
            result["replicate"] = {"status": "error", "detail": str(e)}
    else:
        result["replicate"] = {"status": "no_key"}

    # Local DB estimates
    post_images  = db.query(PostMedia).filter(PostMedia.file_type == "photo").count()
    char_images  = db.query(CharacterMedia).filter(CharacterMedia.file_type == "photo").count()
    place_renders = db.query(Place).filter(Place.render_image.isnot(None)).count()
    room_renders  = db.query(Room).filter(Room.render_image.isnot(None)).count()
    audio_files  = db.query(PostMedia).filter(PostMedia.file_type == "audio").count()
    captions     = db.query(Post).filter(Post.caption.isnot(None)).count()

    total_images = post_images + char_images + place_renders + room_renders
    replicate_est = round(total_images * _FLUX_COST_PER_IMAGE, 4)

    el_chars_est = (result.get("elevenlabs", {}).get("character_count") or 0)
    el_cost_est  = round(el_chars_est / 1000 * _EL_COST_PER_1K_CHARS, 4)

    result["estimates"] = {
        "replicate": {
            "post_images": post_images,
            "character_images": char_images,
            "place_renders": place_renders,
            "room_renders": room_renders,
            "total_images": total_images,
            "cost_usd": replicate_est,
            "price_per_image_usd": _FLUX_COST_PER_IMAGE,
        },
        "elevenlabs": {
            "audio_files_generated": audio_files,
            "captions_generated": captions,
            "characters_used": el_chars_est,
            "cost_usd": el_cost_est,
            "price_per_1k_chars_usd": _EL_COST_PER_1K_CHARS,
        },
    }

    return result
