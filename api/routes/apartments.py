from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from db.database import get_db
from db.models import Place, Room, Character
from core.image_gen import generate_scene

router = APIRouter(prefix="/api/places", tags=["places"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class RoomIn(BaseModel):
    room_type: str
    name: Optional[str] = None
    description: Optional[str] = None
    mood: Optional[str] = None
    render_prompt: Optional[str] = None


class RoomOut(BaseModel):
    id: int
    apartment_id: int  # DB column name kept for compat
    room_type: str
    name: Optional[str]
    description: Optional[str]
    mood: Optional[str]
    render_prompt: Optional[str]
    render_image: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PlaceIn(BaseModel):
    character_id: int
    name: str
    place_type: Optional[str] = None  # apartment, office, park, café, studio, gym…
    location: Optional[str] = None
    building_style: Optional[str] = None
    building_notes: Optional[str] = None
    is_primary: bool = True


class PlaceOut(BaseModel):
    id: int
    character_id: int
    name: str
    place_type: Optional[str]
    location: Optional[str]
    building_style: Optional[str]
    building_notes: Optional[str]
    render_image: Optional[str] = None
    is_primary: bool
    rooms: List[RoomOut] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── Place endpoints ────────────────────────────────────────────────────────────

@router.get("", response_model=List[PlaceOut])
def list_places(character_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(Place).options(joinedload(Place.rooms))
    if character_id:
        q = q.filter(Place.character_id == character_id)
    return q.order_by(Place.created_at).all()


@router.post("", response_model=PlaceOut, status_code=201)
def create_place(body: PlaceIn, db: Session = Depends(get_db)):
    if not db.get(Character, body.character_id):
        raise HTTPException(404, "Character not found")
    place = Place(**body.model_dump())
    db.add(place)
    db.commit()
    db.refresh(place)
    return place


@router.get("/{place_id}", response_model=PlaceOut)
def get_place(place_id: int, db: Session = Depends(get_db)):
    place = db.query(Place).options(joinedload(Place.rooms)).filter(Place.id == place_id).first()
    if not place:
        raise HTTPException(404, "Place not found")
    return place


@router.patch("/{place_id}", response_model=PlaceOut)
def update_place(place_id: int, body: PlaceIn, db: Session = Depends(get_db)):
    place = db.get(Place, place_id)
    if not place:
        raise HTTPException(404, "Place not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(place, field, value)
    db.commit()
    db.refresh(place)
    return place


@router.delete("/{place_id}", status_code=204)
def delete_place(place_id: int, db: Session = Depends(get_db)):
    place = db.get(Place, place_id)
    if not place:
        raise HTTPException(404, "Place not found")
    db.delete(place)
    db.commit()


@router.post("/{place_id}/duplicate", response_model=PlaceOut, status_code=201)
def duplicate_place(place_id: int, character_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Clone a place and all its areas. character_id defaults to the original owner."""
    place = db.query(Place).options(joinedload(Place.rooms)).filter(Place.id == place_id).first()
    if not place:
        raise HTTPException(404, "Place not found")
    target_char = character_id or place.character_id
    if not db.get(Character, target_char):
        raise HTTPException(404, "Character not found")
    new_place = Place(
        character_id=target_char,
        name=f"{place.name} (copy)",
        place_type=place.place_type,
        location=place.location,
        building_style=place.building_style,
        building_notes=place.building_notes,
        is_primary=False,
    )
    db.add(new_place)
    db.flush()
    for r in place.rooms:
        db.add(Room(
            apartment_id=new_place.id,
            room_type=r.room_type,
            name=r.name,
            description=r.description,
            mood=r.mood,
            render_prompt=r.render_prompt,
        ))
    db.commit()
    return db.query(Place).options(joinedload(Place.rooms)).filter(Place.id == new_place.id).first()


@router.patch("/{place_id}/resident", response_model=PlaceOut)
def set_resident(place_id: int, character_id: int, db: Session = Depends(get_db)):
    """Assign a different character as the owner/resident of this place."""
    place = db.query(Place).options(joinedload(Place.rooms)).filter(Place.id == place_id).first()
    if not place:
        raise HTTPException(404, "Place not found")
    if not db.get(Character, character_id):
        raise HTTPException(404, "Character not found")
    place.character_id = character_id
    db.commit()
    db.refresh(place)
    return place


# ── Room/Area endpoints ────────────────────────────────────────────────────────

@router.post("/{place_id}/rooms", response_model=RoomOut, status_code=201)
def create_room(place_id: int, body: RoomIn, db: Session = Depends(get_db)):
    if not db.get(Place, place_id):
        raise HTTPException(404, "Place not found")
    room = Room(apartment_id=place_id, **body.model_dump())
    db.add(room)
    db.commit()
    db.refresh(room)
    return room


@router.patch("/{place_id}/rooms/{room_id}", response_model=RoomOut)
def update_room(place_id: int, room_id: int, body: RoomIn, db: Session = Depends(get_db)):
    room = db.query(Room).filter(Room.id == room_id, Room.apartment_id == place_id).first()
    if not room:
        raise HTTPException(404, "Area not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(room, field, value)
    db.commit()
    db.refresh(room)
    return room


@router.delete("/{place_id}/rooms/{room_id}", status_code=204)
def delete_room(place_id: int, room_id: int, db: Session = Depends(get_db)):
    room = db.query(Room).filter(Room.id == room_id, Room.apartment_id == place_id).first()
    if not room:
        raise HTTPException(404, "Area not found")
    db.delete(room)
    db.commit()


@router.post("/{place_id}/render", response_model=PlaceOut)
def render_place(place_id: int, db: Session = Depends(get_db)):
    """Generate an exterior/building image for this place."""
    place = db.query(Place).options(joinedload(Place.rooms)).filter(Place.id == place_id).first()
    if not place:
        raise HTTPException(404, "Place not found")
    parts = [p for p in [
        place.building_style,
        place.building_notes,
        place.place_type,
        place.name,
    ] if p]
    if not parts:
        raise HTTPException(400, "Place has no building style or notes to render")
    prompt = ", ".join(parts) + ", architectural photography, empty, no people"
    path = generate_scene(prompt, aspect_ratio="16:9")
    place.render_image = path.name
    db.commit()
    db.refresh(place)
    return place


@router.post("/{place_id}/rooms/{room_id}/render", response_model=RoomOut)
def render_room(place_id: int, room_id: int, db: Session = Depends(get_db)):
    """Generate an interior image for this room."""
    room = db.query(Room).filter(Room.id == room_id, Room.apartment_id == place_id).first()
    if not room:
        raise HTTPException(404, "Area not found")
    prompt = room.render_prompt or ", ".join(p for p in [
        room.room_type,
        room.description,
        room.mood,
    ] if p)
    if not prompt:
        raise HTTPException(400, "Room has no render prompt or description")
    prompt += ", interior photography, empty room, no people"
    path = generate_scene(prompt, aspect_ratio="16:9")
    room.render_image = path.name
    db.commit()
    db.refresh(room)
    return room


@router.post("/{place_id}/rooms/{room_id}/duplicate", response_model=RoomOut, status_code=201)
def duplicate_room(place_id: int, room_id: int, db: Session = Depends(get_db)):
    """Clone an area within the same place."""
    room = db.query(Room).filter(Room.id == room_id, Room.apartment_id == place_id).first()
    if not room:
        raise HTTPException(404, "Area not found")
    new_room = Room(
        apartment_id=place_id,
        room_type=room.room_type,
        name=f"{room.name or room.room_type} (copy)",
        description=room.description,
        mood=room.mood,
        render_prompt=room.render_prompt,
    )
    db.add(new_room)
    db.commit()
    db.refresh(new_room)
    return new_room
