"""
LoRA model training via Replicate.

Workflow:
  1. Zip character's CharacterMedia photos
  2. Upload zip to Replicate Files API
  3. Fetch trainer latest version (ostris/flux-dev-lora-trainer)
  4. Create destination model on Replicate (if not exists)
  5. Start training job
  6. Store training ID + status on Character
"""

from __future__ import annotations

import io
import os
import re
import zipfile
from pathlib import Path
from typing import Optional

import httpx
import replicate
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.api_keys import get_key
from db.database import get_db
from db.models import Character, CharacterMedia, Place, Room, PlaceMedia, RoomMedia

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./output"))
TRAINER_MODEL = "ostris/flux-dev-lora-trainer"

router = APIRouter(prefix="/api/characters", tags=["training"])


class TrainRequest(BaseModel):
    trigger_word: Optional[str] = None  # defaults to character name uppercased
    steps: int = 1000                   # 500–2000; more = better quality + more cost
    place_id: Optional[int] = None      # include this place's room renders in training


class TrainingOut(BaseModel):
    training_id: Optional[str]
    training_status: Optional[str]
    replicate_model: Optional[str]
    trigger_word: Optional[str]

    class Config:
        from_attributes = True


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9-]", "-", name.lower().strip())
    return re.sub(r"-+", "-", slug).strip("-")


def _get_trainer_version(token: str) -> str:
    r = httpx.get(
        f"https://api.replicate.com/v1/models/{TRAINER_MODEL}/versions",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    r.raise_for_status()
    versions = r.json().get("results", [])
    if not versions:
        raise RuntimeError("Could not fetch trainer versions from Replicate")
    return versions[0]["id"]


def _get_replicate_username(token: str) -> str:
    r = httpx.get(
        "https://api.replicate.com/v1/account",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["username"]


def _upload_zip(token: str, zip_bytes: bytes) -> str:
    """Upload zip to Replicate Files API. Returns the accessible URL."""
    r = httpx.post(
        "https://api.replicate.com/v1/files",
        headers={"Authorization": f"Bearer {token}"},
        files={"content": ("training_images.zip", zip_bytes, "application/zip")},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["urls"]["get"]


def _ensure_model(client: replicate.Client, username: str, model_name: str):
    """Create the destination model on Replicate if it doesn't exist."""
    try:
        client.models.get(f"{username}/{model_name}")
    except Exception:
        client.models.create(
            owner=username,
            name=model_name,
            visibility="private",
            hardware="gpu-t4",
        )


@router.post("/{char_id}/train", response_model=TrainingOut)
def start_training(
    char_id: int,
    body: TrainRequest,
    db: Session = Depends(get_db),
):
    char = db.get(Character, char_id)
    if not char:
        raise HTTPException(404, "Character not found")

    token = get_key("replicate")
    if not token:
        raise HTTPException(400, "No Replicate API key configured")

    # Collect photo files
    media_items = (
        db.query(CharacterMedia)
        .filter(CharacterMedia.character_id == char_id, CharacterMedia.file_type == "photo")
        .order_by(CharacterMedia.position)
        .all()
    )
    photo_paths = [OUTPUT_DIR / m.file_path.split("/")[-1] for m in media_items]
    photo_paths = [p for p in photo_paths if p.is_file()]

    if len(photo_paths) < 5:
        raise HTTPException(
            400,
            f"Need at least 5 photos in character media. Found {len(photo_paths)}. "
            "Upload more photos in the Characters → Media tab first."
        )

    # Collect place/room media photos if a place was selected
    place_render_paths: list[Path] = []
    if body.place_id:
        place_media = db.query(PlaceMedia).filter(PlaceMedia.apartment_id == body.place_id).all()
        for pm in place_media:
            if pm.file_path:
                p = OUTPUT_DIR / pm.file_path
                if p.is_file():
                    place_render_paths.append(p)
        room_ids = [r.id for r in db.query(Room).filter(Room.apartment_id == body.place_id).all()]
        if room_ids:
            room_media_items = db.query(RoomMedia).filter(RoomMedia.room_id.in_(room_ids)).all()
            for rm in room_media_items:
                if rm.file_path:
                    p = OUTPUT_DIR / rm.file_path
                    if p.is_file():
                        place_render_paths.append(p)

    # Build zip
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in photo_paths:
            zf.write(p, f"character/{p.name}")
        for p in place_render_paths:
            zf.write(p, f"place/{p.name}")
    zip_bytes = buf.getvalue()

    # Upload + resolve account
    try:
        file_url = _upload_zip(token, zip_bytes)
        username = _get_replicate_username(token)
        trainer_version = _get_trainer_version(token)
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"Replicate API error: {e.response.text[:300]}")
    except Exception as e:
        raise HTTPException(502, f"Replicate error: {str(e)[:300]}")

    trigger = (body.trigger_word or char.name).upper().replace(" ", "_")
    model_name = f"ia-girl-{_slugify(char.name)}"
    destination = f"{username}/{model_name}"

    rep_client = replicate.Client(api_token=token)
    try:
        _ensure_model(rep_client, username, model_name)
    except Exception as e:
        raise HTTPException(502, f"Could not create destination model: {str(e)[:300]}")

    try:
        training = rep_client.trainings.create(
            version=f"{TRAINER_MODEL}:{trainer_version}",
            input={
                "input_images": file_url,
                "trigger_word": trigger,
                "steps": max(500, min(2000, body.steps)),
                "lora_rank": 16,
                "learning_rate": 0.0004,
                "autocaption": True,
                "autocaption_prefix": f"A photo of {trigger}",
            },
            destination=destination,
        )
    except Exception as e:
        raise HTTPException(502, f"Training start failed: {str(e)[:300]}")

    char.trigger_word = trigger
    char.replicate_model = destination
    char.replicate_training_id = training.id
    char.training_status = "starting"
    char.training_place_id = body.place_id
    db.commit()

    return TrainingOut(
        training_id=training.id,
        training_status="starting",
        replicate_model=destination,
        trigger_word=trigger,
    )


@router.post("/{char_id}/training-status", response_model=TrainingOut)
def refresh_training_status(char_id: int, db: Session = Depends(get_db)):
    """Poll Replicate for current training status and update the character."""
    char = db.get(Character, char_id)
    if not char:
        raise HTTPException(404, "Character not found")
    if not char.replicate_training_id:
        raise HTTPException(400, "No training has been started for this character")

    token = get_key("replicate")
    if not token:
        raise HTTPException(400, "No Replicate API key configured")

    try:
        rep_client = replicate.Client(api_token=token)
        training = rep_client.trainings.get(char.replicate_training_id)
        char.training_status = training.status
        # When training succeeds, store the versioned model ID from output
        if training.status == "succeeded" and training.output:
            versioned = (training.output or {}).get("version")
            if versioned:
                char.replicate_model = versioned
        db.commit()
    except Exception as e:
        raise HTTPException(502, f"Replicate error: {str(e)[:300]}")

    return TrainingOut(
        training_id=char.replicate_training_id,
        training_status=char.training_status,
        replicate_model=char.replicate_model,
        trigger_word=char.trigger_word,
    )


@router.delete("/{char_id}/training", status_code=204)
def clear_training(char_id: int, db: Session = Depends(get_db)):
    """Remove training link from character (does not delete the Replicate model)."""
    char = db.get(Character, char_id)
    if not char:
        raise HTTPException(404, "Character not found")
    char.replicate_model = None
    char.replicate_training_id = None
    char.training_status = None
    db.commit()
