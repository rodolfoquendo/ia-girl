"""
Media libraries for Places (building photos) and Rooms (room photos).
Each photo is tagged with a predefined type (angle / area).
"""

from __future__ import annotations

import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.image_gen import generate_scene
from db.database import get_db
from db.models import Place, Room, PlaceMedia, RoomMedia

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(tags=["place-media"])

# ── Photo type catalogues ─────────────────────────────────────────────────────

PLACE_PHOTO_TYPES = [
    ("north_side",       "North Side"),
    ("west_side",        "West Side"),
    ("east_side",        "East Side"),
    ("south_side",       "South Side"),
    ("entrance",         "Entrance"),
    ("lobby",            "Lobby"),
    ("elevator_area",    "Elevator Area"),
    ("elevator_inside",  "Elevator Inside"),
    ("front_garden",     "Front Garden"),
    ("back_garden",      "Back Garden"),
    ("pool_area",        "Pool Area"),
]

ROOM_PHOTO_TYPES = [
    ("north_view",  "North View"),
    ("west_view",   "West View"),
    ("east_view",   "East View"),
    ("south_view",  "South View"),
    ("closet",      "Closet"),
    ("bathroom",    "Bathroom"),
]

CHARACTER_PHOTO_TYPES = [
    ("face",          "Face Reference"),
    ("body",          "Body Reference"),
    ("feet",          "Feet Reference"),
    ("hair",          "Hair Reference"),
    ("full_body",     "Full Body"),
    ("side_profile",  "Side Profile"),
    ("hands",         "Hands"),
]


# ── Schemas ───────────────────────────────────────────────────────────────────

class PlaceMediaOut(BaseModel):
    id: int
    apartment_id: int
    photo_type: Optional[str]
    file_path: Optional[str]
    label: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RoomMediaOut(BaseModel):
    id: int
    room_id: int
    photo_type: Optional[str]
    file_path: Optional[str]
    label: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class GenerateMediaIn(BaseModel):
    photo_type: str
    prompt: Optional[str] = None


def _save_upload(file: UploadFile) -> str:
    suffix = Path(file.filename or "photo.jpg").suffix or ".jpg"
    filename = f"{uuid.uuid4().hex}{suffix}"
    dest = OUTPUT_DIR / filename
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return filename


# ── Place media endpoints ─────────────────────────────────────────────────────

@router.get("/api/places/{place_id}/media", response_model=List[PlaceMediaOut])
def list_place_media(place_id: int, db: Session = Depends(get_db)):
    if not db.get(Place, place_id):
        raise HTTPException(404, "Place not found")
    return db.query(PlaceMedia).filter(PlaceMedia.apartment_id == place_id).order_by(PlaceMedia.photo_type, PlaceMedia.created_at).all()


@router.post("/api/places/{place_id}/media", response_model=PlaceMediaOut, status_code=201)
async def upload_place_media(
    place_id: int,
    photo_type: Optional[str] = None,
    label: Optional[str] = None,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not db.get(Place, place_id):
        raise HTTPException(404, "Place not found")
    filename = _save_upload(file)
    m = PlaceMedia(apartment_id=place_id, photo_type=photo_type, file_path=filename, label=label)
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


@router.delete("/api/places/{place_id}/media/{media_id}", status_code=204)
def delete_place_media(place_id: int, media_id: int, db: Session = Depends(get_db)):
    m = db.query(PlaceMedia).filter(PlaceMedia.id == media_id, PlaceMedia.apartment_id == place_id).first()
    if not m:
        raise HTTPException(404, "Media not found")
    if m.file_path:
        p = OUTPUT_DIR / m.file_path
        if p.is_file():
            p.unlink(missing_ok=True)
    db.delete(m)
    db.commit()


@router.post("/api/places/{place_id}/media/generate", response_model=PlaceMediaOut, status_code=201)
def generate_place_media(place_id: int, body: GenerateMediaIn, db: Session = Depends(get_db)):
    place = db.get(Place, place_id)
    if not place:
        raise HTTPException(404, "Place not found")
    type_label = next((l for v, l in PLACE_PHOTO_TYPES if v == body.photo_type), body.photo_type)
    if body.prompt:
        prompt = body.prompt
    else:
        parts = [p for p in [place.building_style, place.building_notes] if p]
        desc = ", ".join(parts) if parts else "modern apartment building"
        prompt = f"{type_label} of {desc}, exterior architecture photography, natural lighting, realistic, high detail"
    try:
        path = generate_scene(prompt, aspect_ratio="16:9")
    except Exception as e:
        raise HTTPException(502, f"Image generation failed: {str(e)[:300]}")
    m = PlaceMedia(apartment_id=place_id, photo_type=body.photo_type, file_path=path.name, label=type_label)
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


# ── Room media endpoints ──────────────────────────────────────────────────────

@router.get("/api/places/{place_id}/rooms/{room_id}/media", response_model=List[RoomMediaOut])
def list_room_media(place_id: int, room_id: int, db: Session = Depends(get_db)):
    room = db.query(Room).filter(Room.id == room_id, Room.apartment_id == place_id).first()
    if not room:
        raise HTTPException(404, "Room not found")
    return db.query(RoomMedia).filter(RoomMedia.room_id == room_id).order_by(RoomMedia.photo_type, RoomMedia.created_at).all()


@router.post("/api/places/{place_id}/rooms/{room_id}/media", response_model=RoomMediaOut, status_code=201)
async def upload_room_media(
    place_id: int,
    room_id: int,
    photo_type: Optional[str] = None,
    label: Optional[str] = None,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    room = db.query(Room).filter(Room.id == room_id, Room.apartment_id == place_id).first()
    if not room:
        raise HTTPException(404, "Room not found")
    filename = _save_upload(file)
    m = RoomMedia(room_id=room_id, photo_type=photo_type, file_path=filename, label=label)
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


@router.delete("/api/places/{place_id}/rooms/{room_id}/media/{media_id}", status_code=204)
def delete_room_media(place_id: int, room_id: int, media_id: int, db: Session = Depends(get_db)):
    m = db.query(RoomMedia).filter(RoomMedia.id == media_id, RoomMedia.room_id == room_id).first()
    if not m:
        raise HTTPException(404, "Media not found")
    if m.file_path:
        p = OUTPUT_DIR / m.file_path
        if p.is_file():
            p.unlink(missing_ok=True)
    db.delete(m)
    db.commit()


@router.post("/api/places/{place_id}/rooms/{room_id}/media/generate", response_model=RoomMediaOut, status_code=201)
def generate_room_media(place_id: int, room_id: int, body: GenerateMediaIn, db: Session = Depends(get_db)):
    room = db.query(Room).filter(Room.id == room_id, Room.apartment_id == place_id).first()
    if not room:
        raise HTTPException(404, "Room not found")
    type_label = next((l for v, l in ROOM_PHOTO_TYPES if v == body.photo_type), body.photo_type)
    if body.prompt:
        prompt = body.prompt
    else:
        parts = [p for p in [room.render_prompt, room.description] if p]
        desc = ", ".join(parts) if parts else f"{room.room_type} room"
        prompt = f"{type_label} of {desc}, interior design photography, natural lighting, realistic, high detail"
    try:
        path = generate_scene(prompt, aspect_ratio="16:9")
    except Exception as e:
        raise HTTPException(502, f"Image generation failed: {str(e)[:300]}")
    m = RoomMedia(room_id=room_id, photo_type=body.photo_type, file_path=path.name, label=type_label)
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


# ── Catalogue endpoints ───────────────────────────────────────────────────────

@router.get("/api/media-types/places")
def place_photo_types():
    return [{"value": v, "label": l} for v, l in PLACE_PHOTO_TYPES]


@router.get("/api/media-types/rooms")
def room_photo_types():
    return [{"value": v, "label": l} for v, l in ROOM_PHOTO_TYPES]


@router.get("/api/media-types/characters")
def character_photo_types():
    return [{"value": v, "label": l} for v, l in CHARACTER_PHOTO_TYPES]
