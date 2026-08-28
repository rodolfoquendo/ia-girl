from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Character, CharacterRelationship, RelationshipType

router = APIRouter(prefix="/api/characters", tags=["relationships"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class RelationshipIn(BaseModel):
    linked_character_id: int
    relationship_type: RelationshipType = RelationshipType.friend
    notes: Optional[str] = None


class RelationshipOut(BaseModel):
    id: int
    character_a_id: int
    character_b_id: int
    relationship_type: RelationshipType
    notes: Optional[str]
    created_at: datetime
    # Resolved names for display
    character_a_name: Optional[str] = None
    character_b_name: Optional[str] = None

    class Config:
        from_attributes = True


# ── Helpers ───────────────────────────────────────────────────────────────────

def _enrich(rel: CharacterRelationship) -> RelationshipOut:
    out = RelationshipOut.model_validate(rel)
    out.character_a_name = rel.character_a.name if rel.character_a else None
    out.character_b_name = rel.character_b.name if rel.character_b else None
    return out


def _get_char_or_404(db: Session, char_id: int) -> Character:
    c = db.get(Character, char_id)
    if not c:
        raise HTTPException(404, "Character not found")
    return c


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/{char_id}/relationships", response_model=List[RelationshipOut])
def list_relationships(char_id: int, db: Session = Depends(get_db)):
    _get_char_or_404(db, char_id)
    rels = (
        db.query(CharacterRelationship)
        .filter(
            (CharacterRelationship.character_a_id == char_id) |
            (CharacterRelationship.character_b_id == char_id)
        )
        .all()
    )
    return [_enrich(r) for r in rels]


@router.post("/{char_id}/relationships", response_model=RelationshipOut, status_code=201)
def create_relationship(char_id: int, body: RelationshipIn, db: Session = Depends(get_db)):
    _get_char_or_404(db, char_id)
    _get_char_or_404(db, body.linked_character_id)
    if char_id == body.linked_character_id:
        raise HTTPException(400, "Cannot link a character to itself")
    # Prevent duplicates (check both directions)
    existing = db.query(CharacterRelationship).filter(
        ((CharacterRelationship.character_a_id == char_id) & (CharacterRelationship.character_b_id == body.linked_character_id)) |
        ((CharacterRelationship.character_a_id == body.linked_character_id) & (CharacterRelationship.character_b_id == char_id))
    ).first()
    if existing:
        raise HTTPException(409, "Relationship already exists")
    rel = CharacterRelationship(
        character_a_id=char_id,
        character_b_id=body.linked_character_id,
        relationship_type=body.relationship_type,
        notes=body.notes,
    )
    db.add(rel)
    db.commit()
    db.refresh(rel)
    return _enrich(rel)


@router.patch("/{char_id}/relationships/{rel_id}", response_model=RelationshipOut)
def update_relationship(char_id: int, rel_id: int, body: RelationshipIn, db: Session = Depends(get_db)):
    rel = db.get(CharacterRelationship, rel_id)
    if not rel or (rel.character_a_id != char_id and rel.character_b_id != char_id):
        raise HTTPException(404, "Relationship not found")
    rel.relationship_type = body.relationship_type
    if body.notes is not None:
        rel.notes = body.notes
    db.commit()
    db.refresh(rel)
    return _enrich(rel)


@router.delete("/{char_id}/relationships/{rel_id}", status_code=204)
def delete_relationship(char_id: int, rel_id: int, db: Session = Depends(get_db)):
    rel = db.get(CharacterRelationship, rel_id)
    if not rel or (rel.character_a_id != char_id and rel.character_b_id != char_id):
        raise HTTPException(404, "Relationship not found")
    db.delete(rel)
    db.commit()
