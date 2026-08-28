from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import CharacterLanguage, Character

router = APIRouter(prefix="/api/characters", tags=["languages"])

COMMON_LANGUAGES = [
    ("es", "Spanish"), ("en", "English"), ("pt", "Portuguese"), ("fr", "French"),
    ("it", "Italian"), ("de", "German"), ("zh", "Chinese"), ("ja", "Japanese"),
    ("ko", "Korean"), ("ar", "Arabic"), ("hi", "Hindi"), ("ru", "Russian"),
    ("nl", "Dutch"), ("pl", "Polish"), ("tr", "Turkish"), ("sv", "Swedish"),
]


class LanguageIn(BaseModel):
    language_code: str
    language_name: str
    is_primary: bool = False
    proficiency: Optional[str] = None  # native, fluent, conversational, basic


class LanguageOut(BaseModel):
    id: int
    character_id: int
    language_code: str
    language_name: str
    is_primary: bool
    proficiency: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


def _get_char_or_404(db: Session, char_id: int) -> Character:
    char = db.get(Character, char_id)
    if not char:
        raise HTTPException(404, "Character not found")
    return char


@router.get("/languages/common")
def common_languages():
    """Return a list of common language codes and names for the UI picker."""
    return [{"code": c, "name": n} for c, n in COMMON_LANGUAGES]


@router.get("/{char_id}/languages", response_model=List[LanguageOut])
def list_languages(char_id: int, db: Session = Depends(get_db)):
    _get_char_or_404(db, char_id)
    return (
        db.query(CharacterLanguage)
        .filter(CharacterLanguage.character_id == char_id)
        .order_by(CharacterLanguage.is_primary.desc(), CharacterLanguage.language_name)
        .all()
    )


@router.post("/{char_id}/languages", response_model=LanguageOut, status_code=201)
def add_language(char_id: int, body: LanguageIn, db: Session = Depends(get_db)):
    _get_char_or_404(db, char_id)
    existing = (
        db.query(CharacterLanguage)
        .filter(CharacterLanguage.character_id == char_id, CharacterLanguage.language_code == body.language_code)
        .first()
    )
    if existing:
        raise HTTPException(409, f"Character already has {body.language_name} ({body.language_code})")
    if body.is_primary:
        db.query(CharacterLanguage).filter(
            CharacterLanguage.character_id == char_id, CharacterLanguage.is_primary == True
        ).update({"is_primary": False})
    lang = CharacterLanguage(character_id=char_id, **body.model_dump())
    db.add(lang)
    db.commit()
    db.refresh(lang)
    return lang


@router.patch("/{char_id}/languages/{lang_id}", response_model=LanguageOut)
def update_language(char_id: int, lang_id: int, body: LanguageIn, db: Session = Depends(get_db)):
    _get_char_or_404(db, char_id)
    lang = db.get(CharacterLanguage, lang_id)
    if not lang or lang.character_id != char_id:
        raise HTTPException(404, "Language entry not found")
    if body.is_primary and not lang.is_primary:
        db.query(CharacterLanguage).filter(
            CharacterLanguage.character_id == char_id, CharacterLanguage.is_primary == True
        ).update({"is_primary": False})
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(lang, field, value)
    db.commit()
    db.refresh(lang)
    return lang


@router.delete("/{char_id}/languages/{lang_id}", status_code=204)
def remove_language(char_id: int, lang_id: int, db: Session = Depends(get_db)):
    _get_char_or_404(db, char_id)
    lang = db.get(CharacterLanguage, lang_id)
    if not lang or lang.character_id != char_id:
        raise HTTPException(404, "Language entry not found")
    db.delete(lang)
    db.commit()
