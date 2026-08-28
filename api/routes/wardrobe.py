from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import ClothingItem, ClothingCategory, ClothingStyle, Character, Gender

router = APIRouter(prefix="/api/wardrobe", tags=["wardrobe"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class ClothingIn(BaseModel):
    character_id: int
    name: str
    category: ClothingCategory
    style: ClothingStyle = ClothingStyle.casual
    brand: Optional[str] = None
    color: Optional[str] = None
    description: Optional[str] = None
    prompt_tag: Optional[str] = None
    gender: Optional[Gender] = None
    notes: Optional[str] = None


class ClothingPatch(BaseModel):
    character_id: Optional[int] = None   # change owner = transfer
    name: Optional[str] = None
    category: Optional[ClothingCategory] = None
    style: Optional[ClothingStyle] = None
    brand: Optional[str] = None
    color: Optional[str] = None
    description: Optional[str] = None
    prompt_tag: Optional[str] = None
    gender: Optional[Gender] = None
    notes: Optional[str] = None


class ClothingOut(BaseModel):
    id: int
    character_id: int
    name: str
    category: ClothingCategory
    style: ClothingStyle
    brand: Optional[str]
    color: Optional[str]
    description: Optional[str]
    prompt_tag: Optional[str]
    gender: Optional[Gender]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TransferRequest(BaseModel):
    to_character_id: int


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=List[ClothingOut])
def list_items(
    character_id: Optional[int] = Query(None),
    category: Optional[ClothingCategory] = None,
    style: Optional[ClothingStyle] = None,
    db: Session = Depends(get_db),
):
    q = db.query(ClothingItem)
    if character_id is not None:
        q = q.filter(ClothingItem.character_id == character_id)
    if category:
        q = q.filter(ClothingItem.category == category)
    if style:
        q = q.filter(ClothingItem.style == style)
    return q.order_by(ClothingItem.category, ClothingItem.name).all()


@router.post("", response_model=ClothingOut, status_code=201)
def create_item(body: ClothingIn, db: Session = Depends(get_db)):
    if not db.get(Character, body.character_id):
        raise HTTPException(404, "Character not found")
    item = ClothingItem(**body.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/{item_id}", response_model=ClothingOut)
def get_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(ClothingItem, item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    return item


@router.patch("/{item_id}", response_model=ClothingOut)
def update_item(item_id: int, body: ClothingPatch, db: Session = Depends(get_db)):
    item = db.get(ClothingItem, item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    if body.character_id is not None and not db.get(Character, body.character_id):
        raise HTTPException(404, "Target character not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return item


@router.post("/{item_id}/transfer", response_model=ClothingOut)
def transfer_item(item_id: int, body: TransferRequest, db: Session = Depends(get_db)):
    """Transfer a clothing item to a different character."""
    item = db.get(ClothingItem, item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    if not db.get(Character, body.to_character_id):
        raise HTTPException(404, "Target character not found")
    item.character_id = body.to_character_id
    db.commit()
    db.refresh(item)
    return item


@router.post("/{item_id}/duplicate", response_model=ClothingOut, status_code=201)
def duplicate_item(item_id: int, db: Session = Depends(get_db)):
    """Clone a clothing item, keeping the same owner."""
    item = db.get(ClothingItem, item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    new_item = ClothingItem(
        character_id=item.character_id,
        name=f"{item.name} (copy)",
        category=item.category,
        style=item.style,
        brand=item.brand,
        color=item.color,
        description=item.description,
        prompt_tag=item.prompt_tag,
        gender=item.gender,
        notes=item.notes,
    )
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return new_item


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(ClothingItem, item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    db.delete(item)
    db.commit()
