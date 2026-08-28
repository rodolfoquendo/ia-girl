import os
import shutil
import uuid
from pathlib import Path

import httpx
import replicate
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from core.api_keys import get_key
from db.database import get_db
from db.models import Character, CharacterMedia, MediaType

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

LIVEPORTRAIT_MODEL = "fofr/live-portrait"

router = APIRouter(prefix="/api/characters", tags=["liveportrait"])


@router.post("/{char_id}/liveportrait")
async def run_liveportrait(
    char_id: int,
    video: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    char = db.get(Character, char_id)
    if not char:
        raise HTTPException(404, "Character not found")

    # Prefer face reference photo, fall back to any photo with a file
    face_media = (
        db.query(CharacterMedia)
        .filter(
            CharacterMedia.character_id == char_id,
            CharacterMedia.file_type == MediaType.photo,
            CharacterMedia.photo_type == "face",
            CharacterMedia.file_path.isnot(None),
        )
        .first()
    )
    if not face_media:
        face_media = (
            db.query(CharacterMedia)
            .filter(
                CharacterMedia.character_id == char_id,
                CharacterMedia.file_type == MediaType.photo,
                CharacterMedia.file_path.isnot(None),
            )
            .first()
        )
    if not face_media:
        raise HTTPException(
            400,
            "No face photo found. Upload a Face Reference photo in the character media library first.",
        )

    face_path = OUTPUT_DIR / face_media.file_path.split("/")[-1]
    if not face_path.is_file():
        raise HTTPException(400, "Face photo file missing on disk.")

    token = get_key("replicate")
    if not token:
        raise HTTPException(400, "No Replicate API key configured")

    # Save driving video
    suffix = Path(video.filename or "driving.webm").suffix or ".webm"
    driving_filename = f"{uuid.uuid4().hex}{suffix}"
    driving_path = OUTPUT_DIR / driving_filename
    with open(driving_path, "wb") as f:
        shutil.copyfileobj(video.file, f)

    try:
        client = replicate.Client(api_token=token)
        output = client.run(
            LIVEPORTRAIT_MODEL,
            input={
                "face_image": open(face_path, "rb"),
                "driving_video": open(driving_path, "rb"),
            },
        )
        result_url = output if isinstance(output, str) else str(output)

        result_filename = f"{uuid.uuid4().hex}.mp4"
        result_path = OUTPUT_DIR / result_filename
        with httpx.stream("GET", result_url, timeout=120, follow_redirects=True) as r:
            r.raise_for_status()
            with open(result_path, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=8192):
                    f.write(chunk)

        return {"video": result_filename}
    except Exception as e:
        raise HTTPException(502, f"LivePortrait failed: {str(e)[:400]}")
    finally:
        driving_path.unlink(missing_ok=True)
