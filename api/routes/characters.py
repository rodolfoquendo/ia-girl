from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Character, CharacterMedia, Gender, MediaType

router = APIRouter(prefix="/api/characters", tags=["characters"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class CharacterIn(BaseModel):
    name: str
    gender: Optional[Gender] = Gender.female
    voice_id: Optional[str] = None
    full_name: Optional[str] = None
    age: Optional[int] = None
    nationality: Optional[str] = None
    location: Optional[str] = None
    personality_traits: Optional[List[str]] = None
    personality_interests: Optional[List[str]] = None
    language_style: Optional[str] = None
    visual_base_prompt: Optional[str] = None
    visual_style: Optional[str] = None
    visual_negative_prompt: Optional[str] = None
    visual_settings: Optional[List[str]] = None
    posting_frequency: int = 5
    posting_times_utc: Optional[List[str]] = None
    instagram_username: Optional[str] = None
    instagram_password: Optional[str] = None
    instagram_session_id: Optional[str] = None
    instagram_enabled: bool = True
    tiktok_session_id: Optional[str] = None
    tiktok_enabled: bool = True
    email_address: Optional[str] = None
    email_password: Optional[str] = None
    email_imap_host: Optional[str] = None
    email_imap_port: Optional[int] = None
    email_smtp_host: Optional[str] = None
    email_smtp_port: Optional[int] = None
    is_active: bool = True
    profile_bio: Optional[str] = None
    character_bible: Optional[str] = None


class CharacterOut(BaseModel):
    id: int
    name: str
    gender: Optional[Gender]
    voice_id: Optional[str]
    full_name: Optional[str]
    age: Optional[int]
    nationality: Optional[str]
    location: Optional[str]
    personality_traits: Optional[List[str]]
    personality_interests: Optional[List[str]]
    language_style: Optional[str]
    visual_base_prompt: Optional[str]
    visual_style: Optional[str]
    visual_negative_prompt: Optional[str]
    visual_settings: Optional[List[str]]
    posting_frequency: int
    posting_times_utc: Optional[List[str]]
    instagram_username: Optional[str]
    instagram_session_id: Optional[str] = None
    instagram_enabled: bool
    tiktok_session_id: Optional[str] = None
    tiktok_enabled: bool
    email_address: Optional[str] = None
    email_imap_host: Optional[str] = None
    email_imap_port: Optional[int] = None
    email_smtp_host: Optional[str] = None
    email_smtp_port: Optional[int] = None
    profile_bio: Optional[str] = None
    profile_picture: Optional[str] = None
    character_bible: Optional[str] = None
    trigger_word: Optional[str] = None
    replicate_model: Optional[str] = None
    replicate_training_id: Optional[str] = None
    training_status: Optional[str] = None
    training_ready: bool = False
    missing_media_types: List[str] = []
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── Endpoints ─────────────────────────────────────────────────────────────────

REQUIRED_MEDIA_TYPES = {'face', 'body', 'feet', 'hair', 'full_body', 'side_profile', 'hands'}
REQUIRED_MEDIA_LABELS = {
    'face': 'Face Reference', 'body': 'Body Reference', 'feet': 'Feet Reference',
    'hair': 'Hair Reference', 'full_body': 'Full Body', 'side_profile': 'Side Profile',
    'hands': 'Hands',
}


@router.get("", response_model=List[CharacterOut])
def list_characters(db: Session = Depends(get_db)):
    chars = db.query(Character).order_by(Character.created_at).all()
    if not chars:
        return []

    char_ids = [c.id for c in chars]
    covered_rows = (
        db.query(CharacterMedia.character_id, CharacterMedia.photo_type)
        .filter(
            CharacterMedia.character_id.in_(char_ids),
            CharacterMedia.file_type == MediaType.photo,
            CharacterMedia.file_path.isnot(None),
            CharacterMedia.photo_type.in_(REQUIRED_MEDIA_TYPES),
        )
        .distinct()
        .all()
    )
    covered_by = {}
    for char_id, pt in covered_rows:
        covered_by.setdefault(char_id, set()).add(pt)

    result = []
    for c in chars:
        covered = covered_by.get(c.id, set())
        missing = sorted(REQUIRED_MEDIA_LABELS[t] for t in REQUIRED_MEDIA_TYPES - covered)
        out = CharacterOut.model_validate(c).model_copy(update={
            'training_ready': len(missing) == 0,
            'missing_media_types': missing,
        })
        result.append(out)
    return result


@router.post("", response_model=CharacterOut, status_code=201)
def create_character(body: CharacterIn, db: Session = Depends(get_db)):
    char = Character(**body.model_dump())
    db.add(char)
    db.commit()
    db.refresh(char)
    return char


@router.get("/{char_id}", response_model=CharacterOut)
def get_character(char_id: int, db: Session = Depends(get_db)):
    char = db.get(Character, char_id)
    if not char:
        raise HTTPException(404, "Character not found")
    return char


@router.patch("/{char_id}", response_model=CharacterOut)
def update_character(char_id: int, body: CharacterIn, db: Session = Depends(get_db)):
    char = db.get(Character, char_id)
    if not char:
        raise HTTPException(404, "Character not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(char, field, value)
    db.commit()
    db.refresh(char)
    return char


@router.post("/{char_id}/build-bible")
def build_bible(char_id: int, db: Session = Depends(get_db)):
    """Generate and return the character bible markdown from the current character fields."""
    from core.character import load as load_char
    from core.grok_gen import build_character_bible
    char_dict = load_char(char_id)
    bible = build_character_bible(char_dict)
    return {"bible": bible}


@router.delete("/{char_id}", status_code=204)
def delete_character(char_id: int, db: Session = Depends(get_db)):
    char = db.get(Character, char_id)
    if not char:
        raise HTTPException(404, "Character not found")
    db.delete(char)
    db.commit()


import os as _os
from pathlib import Path as _Path

_PROFILE_DIR = _Path(_os.getenv("OUTPUT_DIR", "./output")) / "profiles"
_PROFILE_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/{char_id}/profile-picture")
async def upload_profile_picture(
    char_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    char = db.get(Character, char_id)
    if not char:
        raise HTTPException(404, "Character not found")
    suffix = _os.path.splitext(file.filename or "pic.jpg")[1] or ".jpg"
    dest = _PROFILE_DIR / f"char_{char_id}_profile{suffix}"
    dest.write_bytes(await file.read())
    char.profile_picture = str(dest)
    db.commit()
    return {"path": str(dest)}


class ProfilePictureFromPathIn(BaseModel):
    file_path: str


@router.post("/{char_id}/profile-picture-from-path")
def profile_picture_from_path(char_id: int, body: ProfilePictureFromPathIn, db: Session = Depends(get_db)):
    """Set profile picture from an already-generated file on disk (copy into profiles dir)."""
    import shutil
    char = db.get(Character, char_id)
    if not char:
        raise HTTPException(404, "Character not found")
    src = _Path(body.file_path)
    if not src.exists():
        raise HTTPException(400, f"File not found: {body.file_path}")
    dest = _PROFILE_DIR / f"char_{char_id}_profile{src.suffix or '.jpg'}"
    shutil.copy2(src, dest)
    char.profile_picture = str(dest)
    db.commit()
    return {"path": str(dest)}


@router.get("/{char_id}/generated-images")
def list_generated_images(char_id: int, db: Session = Depends(get_db)):
    """Return all generated photo file paths for a character (from post media)."""
    from db.models import PostMedia, Post, MediaType as MT
    rows = (
        db.query(PostMedia.file_path)
        .join(Post, PostMedia.post_id == Post.id)
        .filter(
            Post.character_id == char_id,
            PostMedia.file_type == MT.photo,
            PostMedia.file_path.isnot(None),
        )
        .order_by(PostMedia.created_at.desc())
        .all()
    )
    return [r[0] for r in rows if r[0]]


@router.post("/{char_id}/push-profile/instagram")
def push_profile_instagram(char_id: int, db: Session = Depends(get_db)):
    from platforms.instagram import client_for
    char = db.get(Character, char_id)
    if not char:
        raise HTTPException(404, "Character not found")
    if not char.instagram_username:
        raise HTTPException(400, "Instagram username not set")
    try:
        cl = client_for(char.instagram_username, char.instagram_password or "", session_id=char.instagram_session_id or None)
        if char.profile_bio is not None:
            cl.account_edit(biography=char.profile_bio)
        if char.profile_picture and _Path(char.profile_picture).exists():
            cl.account_change_picture(char.profile_picture)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/{char_id}/push-profile/twitter")
def push_profile_twitter(char_id: int, db: Session = Depends(get_db)):
    char = db.get(Character, char_id)
    if not char:
        raise HTTPException(404, "Character not found")
    try:
        from platforms.twitter import _v1_api
        api = _v1_api()
        if char.profile_bio is not None:
            api.update_profile(description=char.profile_bio)
        if char.profile_picture and _Path(char.profile_picture).exists():
            api.update_profile_image(filename=char.profile_picture)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(400, str(e))
