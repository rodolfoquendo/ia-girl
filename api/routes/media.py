from __future__ import annotations

import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from sqlalchemy.orm import selectinload

from db.database import get_db
from db.models import PostMedia, PostMediaRef, Post, MediaType, CharacterMedia, PlaceMedia, RoomMedia

router = APIRouter(prefix="/api/media", tags=["media"])

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./output"))


# ── Schemas ───────────────────────────────────────────────────────────────────

class MediaIn(BaseModel):
    post_id: Optional[int] = None
    character_id: Optional[int] = None
    file_path: Optional[str] = None
    reference_image: Optional[str] = None
    file_type: MediaType = MediaType.photo
    prompt: Optional[str] = None
    gen_params: Optional[dict] = None
    provider: Optional[str] = None
    position: int = 0


class MediaPatch(BaseModel):
    post_id: Optional[int] = None
    file_path: Optional[str] = None
    reference_image: Optional[str] = None
    file_type: Optional[MediaType] = None
    prompt: Optional[str] = None
    provider: Optional[str] = None
    gen_params: Optional[dict] = None
    position: Optional[int] = None
    tags: Optional[List[str]] = None


class RefOut(BaseModel):
    id: int
    file_path: str
    label: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class MediaOut(BaseModel):
    id: int
    post_id: Optional[int]
    character_id: Optional[int]
    file_path: Optional[str]
    reference_image: Optional[str] = None  # legacy single ref (kept for compat)
    file_type: MediaType
    prompt: Optional[str]
    provider: Optional[str] = None
    gen_params: Optional[dict] = None
    position: int
    tags: Optional[List[str]] = None
    refs: List[RefOut] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LibraryFile(BaseModel):
    filename: str
    file_path: str
    size_kb: int
    created_at: str
    in_use: bool = False
    media_id: Optional[int] = None
    post_id: Optional[int] = None
    tags: Optional[List[str]] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=List[MediaOut])
def list_media(
    post_id: Optional[int] = Query(None),
    character_id: Optional[int] = Query(None),
    unattached: bool = Query(False, description="Only files not assigned to any post"),
    db: Session = Depends(get_db),
):
    q = db.query(PostMedia).options(selectinload(PostMedia.refs))
    if post_id is not None:
        q = q.filter(PostMedia.post_id == post_id)
    if character_id is not None:
        q = q.filter(PostMedia.character_id == character_id)
    if unattached:
        q = q.filter(PostMedia.post_id == None)
    return q.order_by(PostMedia.post_id, PostMedia.position, PostMedia.created_at.desc()).all()


@router.get("/library", response_model=List[LibraryFile])
def library(db: Session = Depends(get_db)):
    """List all files in the output directory, newest first, with in_use flag."""
    if not OUTPUT_DIR.exists():
        return []

    used: set[str] = set()
    # map filename → (media_id, post_id, tags) for generated images
    media_map: dict[str, tuple[int, Optional[int], Optional[list]]] = {}
    for Model, col in [
        (PostMedia, PostMedia.file_path),
        (CharacterMedia, CharacterMedia.file_path),
        (PlaceMedia, PlaceMedia.file_path),
        (RoomMedia, RoomMedia.file_path),
    ]:
        for row in db.query(Model).filter(col.isnot(None)).all():
            fp = getattr(row, "file_path") or ""
            fname = fp.split("/")[-1]
            used.add(fname)
            if Model is PostMedia:
                media_map[fname] = (row.id, row.post_id, row.tags)
    # also mark reference images as in_use
    for (fp,) in db.query(PostMediaRef.file_path).all():
        used.add(fp.split("/")[-1])

    files = []
    for f in sorted(OUTPUT_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".mp4", ".mov"):
            mm = media_map.get(f.name)
            files.append(LibraryFile(
                filename=f.name,
                file_path=str(f),
                size_kb=int(f.stat().st_size / 1024),
                created_at=datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                in_use=f.name in used,
                media_id=mm[0] if mm else None,
                post_id=mm[1] if mm else None,
                tags=mm[2] if mm else None,
            ))
    return files


@router.get("/tags")
def list_tags(db: Session = Depends(get_db)):
    """Return all unique tags used across all PostMedia records, sorted."""
    rows = db.query(PostMedia.tags).filter(PostMedia.tags.isnot(None)).all()
    tags: set[str] = set()
    for (tag_list,) in rows:
        if isinstance(tag_list, list):
            tags.update(tag_list)
    return sorted(tags)


@router.get("/library/{filename}/usage")
def file_usage(filename: str, db: Session = Depends(get_db)):
    """Return everywhere a file is used: as a generated output, as a reference, or as character/place media."""
    from db.models import Character, CharacterMedia, PlaceMedia, RoomMedia, Place, Room
    filename = Path(filename).name  # strip path traversal

    def _match(fp): return fp and (fp == filename or fp.endswith(f"/{filename}"))

    output_of = []
    for pm in db.query(PostMedia).filter(PostMedia.file_path.isnot(None)).all():
        if _match(pm.file_path):
            post = db.get(Post, pm.post_id) if pm.post_id else None
            output_of.append({
                "media_id": pm.id,
                "post_id": pm.post_id,
                "post_scene": post.scene[:80] if post else None,
            })

    ref_of = []
    for ref in db.query(PostMediaRef).all():
        if _match(ref.file_path):
            pm = db.get(PostMedia, ref.post_media_id)
            output_filename = None
            if pm and pm.file_path:
                output_filename = pm.file_path.split("/")[-1]
            post = db.get(Post, pm.post_id) if pm and pm.post_id else None
            ref_of.append({
                "ref_id": ref.id,
                "media_id": ref.post_media_id,
                "post_id": pm.post_id if pm else None,
                "post_scene": post.scene[:80] if post else None,
                "output_filename": output_filename,
            })

    char_media = []
    for cm in db.query(CharacterMedia).filter(CharacterMedia.file_path.isnot(None)).all():
        if _match(cm.file_path):
            char = db.get(Character, cm.character_id)
            char_media.append({"char_media_id": cm.id, "char_id": cm.character_id, "char_name": char.name if char else "?"})

    place_media = []
    for pm in db.query(PlaceMedia).filter(PlaceMedia.file_path.isnot(None)).all():
        if _match(pm.file_path):
            place = db.get(Place, pm.apartment_id)
            place_media.append({"place_media_id": pm.id, "place_id": pm.apartment_id, "place_name": place.name if place else "?"})
    for rm in db.query(RoomMedia).filter(RoomMedia.file_path.isnot(None)).all():
        if _match(rm.file_path):
            room = db.get(Room, rm.room_id)
            place_media.append({"room_media_id": rm.id, "room_id": rm.room_id, "room_name": room.name if room else "?"})

    return {"output_of": output_of, "ref_of": ref_of, "char_media": char_media, "place_media": place_media}


@router.post("/library/upload", response_model=LibraryFile)
async def upload_to_library(file: UploadFile = File(...)):
    """Upload an image or video directly into the output directory."""
    suffix = Path(file.filename or "upload.jpg").suffix.lower() or ".jpg"
    if suffix not in (".jpg", ".jpeg", ".png", ".mp4", ".mov"):
        raise HTTPException(400, f"Unsupported file type: {suffix}")
    filename = f"upload_{uuid.uuid4().hex}{suffix}"
    dest = OUTPUT_DIR / filename
    with open(dest, "wb") as fh:
        shutil.copyfileobj(file.file, fh)
    stat = dest.stat()
    return LibraryFile(
        filename=filename,
        file_path=str(dest),
        size_kb=int(stat.st_size / 1024),
        created_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
        in_use=False,
    )


@router.delete("/library/{filename}", status_code=204)
def delete_library_file(filename: str, db: Session = Depends(get_db)):
    """Delete a file from the output directory. Refuses if the file is referenced anywhere."""
    # Safety: strip path traversal
    filename = Path(filename).name
    used = set()
    for Model, col in [
        (PostMedia, PostMedia.file_path),
        (CharacterMedia, CharacterMedia.file_path),
        (PlaceMedia, PlaceMedia.file_path),
        (RoomMedia, RoomMedia.file_path),
    ]:
        for (fp,) in db.query(col).filter(col.isnot(None)).all():
            used.add(fp.split("/")[-1])
    if filename in used:
        raise HTTPException(409, "File is still referenced by a post, character, or place — remove those references first.")
    target = OUTPUT_DIR / filename
    if not target.exists():
        raise HTTPException(404, "File not found")
    target.unlink()



@router.post("", response_model=MediaOut, status_code=201)
def create_media(body: MediaIn, db: Session = Depends(get_db)):
    """Create a media slot. Can be empty (generate later) or with an existing file_path."""
    if body.post_id and not db.get(Post, body.post_id):
        raise HTTPException(404, "Post not found")
    item = PostMedia(**body.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.post("/adopt", response_model=MediaOut)
def adopt_file(body: dict, db: Session = Depends(get_db)):
    """Create a standalone PostMedia record for an existing file that has no DB row yet."""
    filename = (body.get("filename") or "").strip()
    if not filename:
        raise HTTPException(400, "filename required")
    # Check if it already exists
    existing = db.query(PostMedia).options(selectinload(PostMedia.refs)).filter(PostMedia.file_path == filename).first()
    if existing:
        return existing
    item = PostMedia(file_path=filename, post_id=None)
    db.add(item)
    db.commit()
    db.refresh(item)
    item = db.query(PostMedia).options(selectinload(PostMedia.refs)).filter(PostMedia.id == item.id).first()
    return item


@router.get("/{media_id}", response_model=MediaOut)
def get_media(media_id: int, db: Session = Depends(get_db)):
    item = db.query(PostMedia).options(selectinload(PostMedia.refs)).filter(PostMedia.id == media_id).first()
    if not item:
        raise HTTPException(404, "Media not found")
    return item


@router.patch("/{media_id}", response_model=MediaOut)
def update_media(media_id: int, body: MediaPatch, db: Session = Depends(get_db)):
    item = db.get(PostMedia, media_id)
    if not item:
        raise HTTPException(404, "Media not found")
    if body.post_id is not None and not db.get(Post, body.post_id):
        raise HTTPException(404, "Post not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return item


@router.post("/{media_id}/refs/link", response_model=MediaOut)
def link_ref(media_id: int, body: dict, db: Session = Depends(get_db)):
    """Attach an existing output-dir file as a reference image (no upload needed)."""
    filename = Path(body.get("filename") or "").name  # strip any path traversal
    if not filename:
        raise HTTPException(400, "filename required")
    if not (OUTPUT_DIR / filename).exists():
        raise HTTPException(404, f"File '{filename}' not found in library")
    item = db.query(PostMedia).options(selectinload(PostMedia.refs)).filter(PostMedia.id == media_id).first()
    if not item:
        raise HTTPException(404, "Media not found")
    # Avoid duplicate refs to the same file
    if any(r.file_path == filename for r in item.refs):
        return item
    ref = PostMediaRef(post_media_id=media_id, file_path=filename, label=body.get("label"))
    db.add(ref)
    db.commit()
    db.refresh(item)
    return item


@router.post("/{media_id}/refs", response_model=MediaOut)
async def add_ref(media_id: int, file: UploadFile = File(...), label: Optional[str] = None, db: Session = Depends(get_db)):
    """Upload a reference image and attach it to this media slot."""
    item = db.query(PostMedia).options(selectinload(PostMedia.refs)).filter(PostMedia.id == media_id).first()
    if not item:
        raise HTTPException(404, "Media not found")
    suffix = Path(file.filename or "ref.jpg").suffix or ".jpg"
    filename = f"ref_{uuid.uuid4().hex}{suffix}"
    dest = OUTPUT_DIR / filename
    with open(dest, "wb") as fh:
        shutil.copyfileobj(file.file, fh)
    ref = PostMediaRef(post_media_id=media_id, file_path=filename, label=label)
    db.add(ref)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{media_id}/refs/{ref_id}", response_model=MediaOut)
def delete_ref(media_id: int, ref_id: int, db: Session = Depends(get_db)):
    """Remove a reference image from this media slot."""
    ref = db.query(PostMediaRef).filter(PostMediaRef.id == ref_id, PostMediaRef.post_media_id == media_id).first()
    if not ref:
        raise HTTPException(404, "Reference not found")
    try:
        (OUTPUT_DIR / ref.file_path).unlink(missing_ok=True)
    except Exception:
        pass
    db.delete(ref)
    db.commit()
    item = db.query(PostMedia).options(selectinload(PostMedia.refs)).filter(PostMedia.id == media_id).first()
    return item


# Legacy single-ref endpoints kept for backward compat
@router.post("/{media_id}/reference", response_model=MediaOut)
async def upload_reference_image_legacy(media_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    return await add_ref(media_id, file, db=db)


@router.delete("/{media_id}/reference", response_model=MediaOut)
def clear_reference_image_legacy(media_id: int, db: Session = Depends(get_db)):
    item = db.query(PostMedia).options(selectinload(PostMedia.refs)).filter(PostMedia.id == media_id).first()
    if not item:
        raise HTTPException(404, "Media not found")
    for ref in list(item.refs):
        try:
            (OUTPUT_DIR / ref.file_path).unlink(missing_ok=True)
        except Exception:
            pass
        db.delete(ref)
    db.commit()
    db.refresh(item)
    return item


@router.get("/{media_id}/preview-prompt")
def preview_prompt(media_id: int, provider: str = Query("replicate"), db: Session = Depends(get_db)):
    """Return the fully assembled prompt that would be sent to the chosen provider."""
    item = db.query(PostMedia).options(selectinload(PostMedia.refs)).filter(PostMedia.id == media_id).first()
    if not item:
        raise HTTPException(404, "Media not found")

    from core.character import load as load_char, reference_image_prompt
    from core.image_gen import _load_defaults
    from db.models import ClothingItem, Place, Room

    char_id = item.character_id
    post = db.get(Post, item.post_id) if item.post_id else None
    if not char_id and post:
        char_id = post.character_id

    char = load_char(char_id) if char_id else None
    scene = item.prompt or (post.scene if post else "lifestyle photo")

    global_positive, global_negative, global_style = _load_defaults()

    if provider == "grok" and char:
        from core.grok_gen import build_character_bible
        wardrobe_items = []
        if post and post.wardrobe_items:
            wrows = db.query(ClothingItem).filter(ClothingItem.id.in_(post.wardrobe_items)).all()
            wardrobe_items = [{"name": w.name, "color": w.color, "description": w.description, "prompt_tag": w.prompt_tag} for w in wrows]
        place_dict = room_dict = None
        if post and post.place_id:
            pl = db.get(Place, post.place_id)
            if pl:
                place_dict = {"name": pl.name, "location": pl.location, "building_style": pl.building_style, "building_notes": getattr(pl, "building_notes", None)}
        if post and post.room_id:
            rm = db.get(Room, post.room_id)
            if rm:
                room_dict = {"name": rm.name, "room_type": rm.room_type, "description": rm.description, "mood": rm.mood, "render_prompt": rm.render_prompt}
        from core.grok_gen import _strip_trigger
        bible = build_character_bible(char, wardrobe_items=wardrobe_items or None, place=place_dict, room=room_dict)
        clean_scene = _strip_trigger(scene, (char.get("trigger_word") or "").strip())
        parts = [p for p in [global_positive, bible, clean_scene, global_style] if p and p.strip()]
        full = "\n\n".join(parts)
        if len(full) > 7900:
            full = full[:7900]
        return {"prompt": full, "negative": global_negative, "provider": provider}
    else:
        if char:
            refs = reference_image_prompt(char)
            char_parts = [p for p in [char["visual"]["base_prompt"], refs] if p]
            char_prompt = f"{char['name']}: " + ", ".join(char_parts) if char_parts else ""
        else:
            char_prompt = ""
        scene_with_char = ", ".join(p for p in [item.prompt, char_prompt, scene if not item.prompt else None, char["visual"]["style"] if char else None] if p)
        parts = [p for p in [global_positive, scene_with_char, global_style] if p and p.strip()]
        full = ", ".join(parts)
        return {"prompt": full, "negative": global_negative, "provider": provider}


@router.post("/{media_id}/generate", response_model=MediaOut)
def generate_media(
    media_id: int,
    provider: str = Query("replicate", description="Image provider: 'replicate' or 'grok'"),
    raw: bool = Query(False, description="Use item.prompt as the final prompt verbatim, skip all assembly"),
    db: Session = Depends(get_db),
):
    """Generate an image for this media slot. provider='grok' uses xAI Grok with a character bible."""
    item = db.query(PostMedia).options(selectinload(PostMedia.refs)).filter(PostMedia.id == media_id).first()
    if not item:
        raise HTTPException(404, "Media not found")

    from core.character import load as load_char, reference_image_prompt
    from core.image_gen import generate as replicate_generate
    from db.models import ClothingItem, Place, Room

    char_id = item.character_id
    post = db.get(Post, item.post_id) if item.post_id else None
    if not char_id and post:
        char_id = post.character_id

    char_ids = []
    if char_id:
        char_ids.append(char_id)
    if post:
        for post_char_id in post.character_ids or []:
            if post_char_id and post_char_id not in char_ids:
                char_ids.append(post_char_id)
    chars = [load_char(cid) for cid in char_ids] or [load_char(char_id)]
    char = chars[0]

    if raw and item.prompt:
        # User edited the full assembled prompt — send it verbatim, skip all assembly
        full_prompt = item.prompt
        scene = item.prompt
    else:
        scene = item.prompt or (post.scene if post else "lifestyle photo")
        # Build character context for replicate-style prompts
        character_prompts = []
        for c in chars:
            refs = reference_image_prompt(c)
            parts = [p for p in [c["visual"]["base_prompt"], refs] if p]
            if parts:
                character_prompts.append(f"{c['name']}: " + ", ".join(parts))
        characters_prompt = "Characters in scene: " + "; ".join(character_prompts) if character_prompts else ""
        full_prompt = ", ".join(p for p in [
            item.prompt,
            characters_prompt,
            scene if not item.prompt else None,
            char["visual"]["style"],
        ] if p)

    aspect = "4:5" if item.file_type == MediaType.photo else "9:16"

    # Collect reference images — use new refs table, fall back to legacy reference_image
    ref_files = [r.file_path for r in (item.refs or [])]
    if not ref_files and item.reference_image:
        ref_files = [item.reference_image]
    primary_ref = ref_files[0] if ref_files else None

    try:
        if provider == "grok":
            from core.grok_gen import generate as grok_generate

            # Load wardrobe items for this post
            wardrobe_items = []
            if post and post.wardrobe_items:
                wrows = db.query(ClothingItem).filter(ClothingItem.id.in_(post.wardrobe_items)).all()
                wardrobe_items = [
                    {"name": w.name, "color": w.color, "description": w.description, "prompt_tag": w.prompt_tag}
                    for w in wrows
                ]

            # Load place/room for this post
            place_dict = room_dict = None
            if post and post.place_id:
                pl = db.get(Place, post.place_id)
                if pl:
                    place_dict = {
                        "name": pl.name, "location": pl.location,
                        "building_style": pl.building_style, "building_notes": getattr(pl, "building_notes", None),
                    }
            if post and post.room_id:
                rm = db.get(Room, post.room_id)
                if rm:
                    room_dict = {
                        "name": rm.name, "room_type": rm.room_type,
                        "description": rm.description, "mood": rm.mood,
                        "render_prompt": rm.render_prompt,
                    }

            path = grok_generate(
                scene=scene,
                char=char,
                full_prompt=full_prompt if (item.prompt or raw) else None,
                raw=raw,
                aspect_ratio=aspect,
                wardrobe_items=wardrobe_items or None,
                place=place_dict,
                room=room_dict,
            )
        elif primary_ref:
            path = _generate_with_reference(primary_ref, full_prompt, char, aspect, item.gen_params)
        else:
            path = replicate_generate(scene, char=char, aspect_ratio=aspect, full_prompt=full_prompt, gen_params=item.gen_params, raw=raw)
    except Exception as exc:
        raise HTTPException(500, str(exc))

    item.file_path = str(path)
    item.provider = provider if provider != "replicate" or not item.reference_image else "replicate-kontext"
    db.commit()
    db.refresh(item)
    return item


def _generate_with_reference(reference_filename: str, prompt: str, char: dict, aspect_ratio: str, gen_params: dict | None = None) -> Path:
    """Generate using flux-kontext-pro (reference image guided)."""
    import httpx, uuid, replicate as _rep
    from core.api_keys import get_key
    from core.image_gen import _load_defaults, _effective_gen_params, OUTPUT_DIR as _OUT

    token = get_key("replicate")
    global_positive, global_negative, global_style = _load_defaults()
    eff = _effective_gen_params(gen_params)
    # aspect_ratio arg takes precedence over gen_params for kontext (caller sets it from file_type)
    eff["aspect_ratio"] = aspect_ratio

    # If character has a trained LoRA, prepend trigger word so kontext-pro sees it
    trigger = (char.get("trigger_word") or "").strip()
    if trigger and not prompt.startswith(trigger):
        prompt = f"{trigger}, {prompt}"

    parts = [p for p in [global_positive, prompt, global_style] if p]
    final_prompt = ", ".join(parts)

    # Upload reference image to Replicate Files API so kontext-pro can read it
    ref_path = _OUT / reference_filename
    with open(ref_path, "rb") as fh:
        ref_bytes = fh.read()

    r = httpx.post(
        "https://api.replicate.com/v1/files",
        headers={"Authorization": f"Bearer {token}"},
        files={"content": (reference_filename, ref_bytes, "image/jpeg")},
        timeout=60,
    )
    r.raise_for_status()
    ref_url = r.json()["urls"]["get"]

    run_input: dict = {
        "prompt": final_prompt,
        "input_image": ref_url,
        "aspect_ratio": eff["aspect_ratio"],
        "output_format": eff["output_format"],
        "output_quality": eff["output_quality"],
        "safety_tolerance": eff["safety_tolerance"],
        "prompt_upsampling": eff["prompt_upsampling"],
    }
    if eff.get("seed") is not None:
        run_input["seed"] = eff["seed"]

    client = _rep.Client(api_token=token)
    output = client.run("black-forest-labs/flux-kontext-pro", input=run_input)

    item_out = output[0] if isinstance(output, list) else output
    filename = _OUT / f"{uuid.uuid4().hex}.{eff['output_format']}"
    if hasattr(item_out, "read"):
        with open(filename, "wb") as f:
            f.write(item_out.read())
    else:
        url = str(getattr(item_out, "url", item_out))
        with httpx.stream("GET", url, timeout=120) as resp:
            resp.raise_for_status()
            with open(filename, "wb") as f:
                for chunk in resp.iter_bytes():
                    f.write(chunk)

    return filename


@router.delete("/{media_id}", status_code=204)
def delete_media(media_id: int, delete_file: bool = Query(False), db: Session = Depends(get_db)):
    item = db.get(PostMedia, media_id)
    if not item:
        raise HTTPException(404, "Media not found")
    if delete_file and item.file_path:
        try:
            Path(item.file_path).unlink(missing_ok=True)
        except Exception:
            pass
    db.delete(item)
    db.commit()
