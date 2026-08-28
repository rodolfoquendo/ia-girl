import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import CharacterMedia, Character, MediaType

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(prefix="/api/characters", tags=["character-media"])


class CharacterMediaIn(BaseModel):
    prompt: Optional[str] = None
    label: Optional[str] = None
    photo_type: Optional[str] = None
    file_path: Optional[str] = None
    file_type: MediaType = MediaType.photo
    position: int = 0


class CharacterMediaOut(BaseModel):
    id: int
    character_id: int
    file_path: Optional[str]
    file_type: MediaType
    photo_type: Optional[str]
    prompt: Optional[str]
    label: Optional[str]
    position: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


def _get_char_or_404(db: Session, char_id: int) -> Character:
    char = db.get(Character, char_id)
    if not char:
        raise HTTPException(404, "Character not found")
    return char


def _get_media_or_404(db: Session, media_id: int, char_id: int) -> CharacterMedia:
    m = db.get(CharacterMedia, media_id)
    if not m or m.character_id != char_id:
        raise HTTPException(404, "Media not found")
    return m


@router.get("/{char_id}/prompt-preview")
def get_prompt_preview(char_id: int, db: Session = Depends(get_db)):
    """Return the fully assembled character prompt so the UI can pre-fill the textarea."""
    _get_char_or_404(db, char_id)
    from core import character as char_module
    from core.image_gen import _load_defaults
    from core.character import base_image_prompt, reference_image_prompt, negative_prompt
    char_dict = char_module.load(char_id)
    global_positive, global_negative, global_style = _load_defaults()
    base = base_image_prompt(char_dict)
    references = reference_image_prompt(char_dict)
    char_style = char_dict["visual"].get("style", "")
    char_neg = negative_prompt(char_dict)
    merged_neg = ", ".join(p for p in [global_negative, char_neg] if p)
    parts = [p for p in [global_positive, base, references, char_style, global_style] if p]
    return {"prompt": ", ".join(parts), "negative": merged_neg}


@router.get("/{char_id}/media", response_model=List[CharacterMediaOut])
def list_character_media(char_id: int, db: Session = Depends(get_db)):
    _get_char_or_404(db, char_id)
    return (
        db.query(CharacterMedia)
        .filter(CharacterMedia.character_id == char_id)
        .order_by(CharacterMedia.position, CharacterMedia.created_at)
        .all()
    )


@router.post("/{char_id}/media", response_model=CharacterMediaOut, status_code=201)
def create_character_media(char_id: int, body: CharacterMediaIn, db: Session = Depends(get_db)):
    _get_char_or_404(db, char_id)
    m = CharacterMedia(character_id=char_id, **body.model_dump())
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


@router.post("/{char_id}/media/upload", response_model=CharacterMediaOut, status_code=201)
async def upload_character_media(
    char_id: int,
    photo_type: Optional[str] = None,
    label: Optional[str] = None,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    _get_char_or_404(db, char_id)
    suffix = Path(file.filename or "photo.jpg").suffix or ".jpg"
    filename = f"{uuid.uuid4().hex}{suffix}"
    dest = OUTPUT_DIR / filename
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    m = CharacterMedia(character_id=char_id, file_path=filename, photo_type=photo_type, label=label, file_type=MediaType.photo)
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


@router.post("/{char_id}/media/{media_id}/generate", response_model=CharacterMediaOut)
def generate_character_media(char_id: int, media_id: int, db: Session = Depends(get_db)):
    _get_char_or_404(db, char_id)
    m = _get_media_or_404(db, media_id, char_id)
    if m.file_type != MediaType.photo:
        raise HTTPException(400, "Generate only supports photo type; audio is created via /api/podcast/preview-tts")
    from core import character as char_module
    from core.image_gen import generate, _load_defaults
    from core.character import base_image_prompt, reference_image_prompt
    char_dict = char_module.load(char_id)

    # Build a final prompt, falling back through layers if needed.
    full_prompt = (m.prompt or "").strip() or None
    if full_prompt is None:
        global_positive, _, global_style = _load_defaults()
        base = base_image_prompt(char_dict)
        refs = reference_image_prompt(char_dict)
        style = char_dict["visual"].get("style", "")
        parts = [p for p in [global_positive, base, refs, style, global_style] if p]
        full_prompt = ", ".join(parts) or None
    if not full_prompt:
        raise HTTPException(400, "No prompt available — add a prompt to this media slot or fill in the character's visual fields first.")

    # Always use the base Flux model for reference photos (not the trained LoRA).
    path = generate("", char=char_dict, aspect_ratio="1:1", full_prompt=full_prompt, force_base_model=True)
    m.file_path = str(path)
    db.commit()
    db.refresh(m)
    return m


@router.patch("/{char_id}/media/{media_id}", response_model=CharacterMediaOut)
def update_character_media(char_id: int, media_id: int, body: CharacterMediaIn, db: Session = Depends(get_db)):
    _get_char_or_404(db, char_id)
    m = _get_media_or_404(db, media_id, char_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(m, field, value)
    db.commit()
    db.refresh(m)
    return m


@router.delete("/{char_id}/media/{media_id}", status_code=204)
def delete_character_media(char_id: int, media_id: int, db: Session = Depends(get_db)):
    _get_char_or_404(db, char_id)
    m = _get_media_or_404(db, media_id, char_id)
    db.delete(m)
    db.commit()
