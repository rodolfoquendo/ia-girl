from datetime import datetime
from typing import Optional, List
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from db.database import get_db
from db.models import Post, PostMedia, PostStatus, MediaType, Network, ClothingItem, Room
from core import character as char_module
from core.character import reference_image_prompt
from core.image_gen import generate
from core.content_gen import caption as gen_caption, content_ideas, blog_post, twitter_thread
from core.video_gen import slideshow

router = APIRouter(prefix="/api/posts", tags=["posts"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class CreateRequest(BaseModel):
    character_id: int
    character_ids: Optional[List[int]] = None
    scene: Optional[str] = None
    mood: str = "casual"
    caption_prompt: Optional[str] = None
    image_prompt: Optional[str] = None
    language: Optional[str] = None
    caption_length_words: Optional[int] = None
    media_type: MediaType = MediaType.photo
    network: Network = Network.instagram
    scheduled_at: Optional[datetime] = None
    wardrobe_items: Optional[List[int]] = None
    place_id: Optional[int] = None
    room_id: Optional[int] = None


class GenerateRequest(BaseModel):
    character_id: int
    character_ids: Optional[List[int]] = None
    scene: Optional[str] = None
    mood: str = "casual"
    language: Optional[str] = None
    caption_length_words: Optional[int] = None
    media_type: MediaType = MediaType.photo
    network: Network = Network.instagram


class ScheduleRequest(BaseModel):
    scheduled_at: datetime
    network: Optional[Network] = None


class UpdateRequest(BaseModel):
    character_ids: Optional[List[int]] = None
    scene: Optional[str] = None
    mood: Optional[str] = None
    caption: Optional[str] = None
    caption_prompt: Optional[str] = None
    image_prompt: Optional[str] = None
    language: Optional[str] = None
    caption_length_words: Optional[int] = None
    status: Optional[PostStatus] = None
    scheduled_at: Optional[datetime] = None
    network: Optional[Network] = None
    media_type: Optional[MediaType] = None
    wardrobe_items: Optional[List[int]] = None
    place_id: Optional[int] = None
    room_id: Optional[int] = None


class MediaItemOut(BaseModel):
    id: int
    file_path: Optional[str]
    file_type: MediaType
    prompt: Optional[str]
    position: int
    created_at: datetime

    class Config:
        from_attributes = True


class PostOut(BaseModel):
    id: int
    character_id: Optional[int]
    character_ids: Optional[list] = None
    scene: str
    mood: Optional[str]
    caption_prompt: Optional[str]
    image_prompt: Optional[str]
    language: Optional[str]
    caption_length_words: Optional[int]
    caption: Optional[str]
    media_type: MediaType
    media_items: List[MediaItemOut] = []
    script: Optional[list] = None
    wardrobe_items: Optional[list] = None
    place_id: Optional[int] = None
    room_id: Optional[int] = None
    network: Network
    status: PostStatus
    scheduled_at: Optional[datetime]
    published_at: Optional[datetime]
    publish_error: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_char(character_id: int) -> dict:
    return char_module.load(character_id)


def _normalize_character_ids(primary_id: int | None, character_ids: list[int] | None = None) -> list[int]:
    ids = []
    if primary_id:
        ids.append(int(primary_id))
    for char_id in character_ids or []:
        if char_id and int(char_id) not in ids:
            ids.append(int(char_id))
    return ids


def _post_character_ids(post: Post) -> list[int]:
    return _normalize_character_ids(post.character_id, post.character_ids or [])


def _get_chars(character_ids: list[int]) -> list[dict]:
    if not character_ids:
        return [char_module.load(None)]
    return [char_module.load(char_id) for char_id in character_ids]


def _pick_scene(char: dict) -> str:
    import random
    settings = char["visual"].get("settings", [])
    if not settings:
        return "lifestyle photo"
    return random.choice(settings)


def _outfit_tags(item_ids: list, db: Session) -> str:
    """Return a comma-joined string of prompt_tags for the given clothing item IDs."""
    if not item_ids:
        return ""
    items = db.query(ClothingItem).filter(ClothingItem.id.in_(item_ids)).all()
    tags = [i.prompt_tag for i in items if i.prompt_tag]
    return ", ".join(tags)


def _outfit_caption_hint(item_ids: list, db: Session) -> str:
    """Return a natural outfit description for caption context."""
    if not item_ids:
        return ""
    items = db.query(ClothingItem).filter(ClothingItem.id.in_(item_ids)).all()
    names = [i.name for i in items]
    if not names:
        return ""
    if len(names) == 1:
        return f" She is wearing {names[0]}."
    return f" She is wearing {', '.join(names[:-1])} and {names[-1]}."


def _co_character_caption_hint(chars: list[dict]) -> str:
    names = [char.get("name") for char in chars[1:] if char.get("name")]
    if not names:
        return ""
    if len(names) == 1:
        return f" Other character in the scene: {names[0]}."
    return f" Other characters in the scene: {', '.join(names[:-1])} and {names[-1]}."


def _generate_media(scene: str, media_type: MediaType, char: dict, full_prompt: str | None = None) -> Path:
    if media_type == MediaType.video:
        from core.image_gen import generate_batch
        images = generate_batch([scene] * 3, char=char, aspect_ratio="9:16", full_prompt=full_prompt)
        return slideshow(images)
    return generate(scene, char=char, aspect_ratio="4:5", full_prompt=full_prompt)


def _characters_image_prompt(chars: list[dict]) -> str:
    if not chars:
        return ""
    prompts = []
    for char in chars:
        visual = char.get("visual", {})
        refs = reference_image_prompt(char)
        parts = [p for p in [visual.get("base_prompt"), refs] if p]
        if parts:
            prompts.append(f"{char.get('name', 'Character')}: " + ", ".join(parts))
    if not prompts:
        return ""
    return "Characters in scene: " + "; ".join(prompts)


def _base_post_image_prompt(chars: list[dict], scene: str) -> str:
    primary = chars[0] if chars else {}
    return ", ".join(p for p in [
        _characters_image_prompt(chars),
        scene,
        primary.get("visual", {}).get("style"),
    ] if p)


def _char_for_post(char: dict, language: str | None) -> dict:
    if not language:
        return char
    char = {**char, "languages": [*char.get("languages", [])]}
    matched = None
    for lang in char["languages"]:
        if language.lower() in {str(lang.get("code", "")).lower(), str(lang.get("name", "")).lower()}:
            matched = {**lang, "is_primary": True}
            break
    if not matched:
        matched = {"code": language.lower(), "name": language, "is_primary": True, "proficiency": None}
    char["languages"] = [matched] + [
        {**lang, "is_primary": False}
        for lang in char["languages"]
        if str(lang.get("code", "")).lower() != str(matched.get("code", "")).lower()
        and str(lang.get("name", "")).lower() != str(matched.get("name", "")).lower()
    ]
    return char


def _caption_word_target(post: Post) -> int | None:
    if post.network == Network.wordpress:
        return max(500, post.caption_length_words or 500)
    return post.caption_length_words


def _get_or_404(db: Session, post_id: int) -> Post:
    post = db.query(Post).options(joinedload(Post.media_items)).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(404, "Post not found")
    return post


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", response_model=PostOut, status_code=201)
def create_post(body: CreateRequest, db: Session = Depends(get_db)):
    """Save post record immediately — no generation. Fast."""
    char = _get_char(body.character_id)
    character_ids = _normalize_character_ids(body.character_id, body.character_ids)
    scene = body.scene or _pick_scene(char)
    status = PostStatus.to_be_published if body.scheduled_at else PostStatus.pending

    post = Post(
        character_id=body.character_id,
        character_ids=character_ids,
        scene=scene,
        mood=body.mood,
        caption_prompt=body.caption_prompt,
        image_prompt=body.image_prompt,
        language=body.language,
        caption_length_words=max(500, body.caption_length_words or 500) if body.network == Network.wordpress else body.caption_length_words,
        media_type=body.media_type,
        network=body.network,
        status=status,
        scheduled_at=body.scheduled_at,
        wardrobe_items=body.wardrobe_items or [],
        place_id=body.place_id,
        room_id=body.room_id,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


@router.post("/{post_id}/generate-caption", response_model=PostOut)
def generate_caption(post_id: int, db: Session = Depends(get_db)):
    post = _get_or_404(db, post_id)
    chars = _get_chars(_post_character_ids(post))
    char = _char_for_post(chars[0], post.language)
    outfit_hint = _outfit_caption_hint(post.wardrobe_items or [], db)
    co_char_hint = _co_character_caption_hint(chars)
    word_target = _caption_word_target(post)
    place_hint = ""
    if post.room_id:
        room = db.get(Room, post.room_id)
        if room:
            place_hint = f" at the {room.name or room.room_type}"
    if post.network == Network.wordpress:
        topic = post.caption_prompt or post.scene
        if outfit_hint:
            topic += f"\n\nOutfit context: {outfit_hint}"
        if place_hint:
            topic += f"\n\nLocation context: {place_hint}"
        if co_char_hint:
            topic += f"\n\nPeople context: {co_char_hint.strip()}"
        post.caption = blog_post(topic, mood=post.mood or "casual", char=char, min_words=word_target or 500)
    elif post.caption_prompt:
        from core.content_gen import _chat
        from core.character import persona_system_prompt
        system = persona_system_prompt(char)
        user_prompt = post.caption_prompt
        if outfit_hint:
            user_prompt += f"\n\nOutfit context: {outfit_hint}"
        if place_hint:
            user_prompt += f"\n\nLocation context: {place_hint}"
        if co_char_hint:
            user_prompt += f"\n\nPeople context: {co_char_hint.strip()}"
        if word_target:
            user_prompt += f"\n\nLength: write about {word_target} words."
        max_tokens = min(4096, max(512, int((word_target or 150) * 2.2)))
        post.caption = _chat(system, user_prompt, max_tokens=max_tokens)
    else:
        scene_with_context = post.scene + place_hint + (outfit_hint if outfit_hint else "") + (co_char_hint if co_char_hint else "")
        post.caption = gen_caption(scene_with_context, mood=post.mood or "casual", char=char, text_length_words=word_target)
    db.commit()
    db.refresh(post)
    return post


@router.post("/{post_id}/generate-image", response_model=PostOut)
def generate_image(post_id: int, db: Session = Depends(get_db)):
    post = _get_or_404(db, post_id)
    chars = _get_chars(_post_character_ids(post))
    char = chars[0]
    # Build full prompt: custom image_prompt OR assembled from char + outfit + place + scene
    characters_prompt = _characters_image_prompt(chars)
    if post.image_prompt:
        effective_prompt = ", ".join(p for p in [post.image_prompt, characters_prompt] if p)
    else:
        outfit = _outfit_tags(post.wardrobe_items or [], db)
        style = char['visual']['style']
        room_prompt = ""
        if post.room_id:
            room = db.get(Room, post.room_id)
            if room and room.render_prompt:
                room_prompt = room.render_prompt
            elif room and room.description:
                room_prompt = room.description
        parts = [p for p in [characters_prompt, outfit, room_prompt, post.scene, style] if p]
        effective_prompt = ", ".join(parts)
    media_path = _generate_media(post.scene, post.media_type, char, full_prompt=effective_prompt)
    prompt_used = effective_prompt
    existing = [m for m in post.media_items if m.position == 0]
    if existing:
        existing[0].file_path = str(media_path)
        existing[0].prompt = prompt_used
    else:
        db.add(PostMedia(
            post_id=post.id, character_id=post.character_id,
            file_path=str(media_path), file_type=post.media_type,
            prompt=prompt_used, position=0,
        ))
    db.commit()
    db.refresh(post)
    return post


@router.post("/generate", response_model=PostOut, status_code=201)
def generate_post(body: GenerateRequest, db: Session = Depends(get_db)):
    """One-shot: create + caption + image in one call (~30 s)."""
    character_ids = _normalize_character_ids(body.character_id, body.character_ids)
    chars = _get_chars(character_ids)
    char = _char_for_post(chars[0], body.language)
    scene = body.scene or _pick_scene(char)
    effective_prompt = _base_post_image_prompt(chars, scene)
    media_path = _generate_media(scene, body.media_type, char, full_prompt=effective_prompt)
    word_target = max(500, body.caption_length_words or 500) if body.network == Network.wordpress else body.caption_length_words
    if body.network == Network.wordpress:
        caption = blog_post(scene, mood=body.mood, char=char, min_words=word_target or 500)
    else:
        caption = gen_caption(scene, mood=body.mood, char=char, text_length_words=word_target)

    post = Post(
        character_id=body.character_id,
        character_ids=character_ids,
        scene=scene,
        mood=body.mood,
        language=body.language,
        caption_length_words=word_target,
        caption=caption,
        media_type=body.media_type,
        network=body.network,
        status=PostStatus.pending,
    )
    db.add(post)
    db.flush()
    db.add(PostMedia(
        post_id=post.id, character_id=body.character_id,
        file_path=str(media_path), file_type=body.media_type,
        prompt=effective_prompt, position=0,
    ))
    db.commit()
    db.refresh(post)
    return post


@router.get("/ideas")
def get_ideas(character_id: int = Query(...), n: int = 7):
    char = _get_char(character_id)
    return {"ideas": content_ideas(n, char=char)}


@router.get("", response_model=List[PostOut])
def list_posts(
    character_id: Optional[int] = Query(None),
    status: Optional[PostStatus] = None,
    network: Optional[Network] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = db.query(Post).options(joinedload(Post.media_items))
    if character_id is not None:
        q = q.filter(Post.character_id == character_id)
    if status:
        q = q.filter(Post.status == status)
    if network:
        q = q.filter(Post.network == network)
    return q.order_by(Post.created_at.desc()).offset(offset).limit(limit).all()


@router.get("/{post_id}", response_model=PostOut)
def get_post(post_id: int, db: Session = Depends(get_db)):
    post = db.query(Post).options(joinedload(Post.media_items)).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(404, "Post not found")
    return post


@router.patch("/{post_id}", response_model=PostOut)
def update_post(post_id: int, body: UpdateRequest, db: Session = Depends(get_db)):
    post = _get_or_404(db, post_id)
    for field in ("scene", "mood", "caption", "caption_prompt", "image_prompt", "language", "caption_length_words", "status", "scheduled_at", "network", "media_type", "wardrobe_items", "place_id", "room_id", "character_ids"):
        val = getattr(body, field)
        if val is not None:
            setattr(post, field, val)
    post.character_ids = _normalize_character_ids(post.character_id, post.character_ids or [])
    if post.network == Network.wordpress:
        post.caption_length_words = max(500, post.caption_length_words or 500)
    db.commit()
    db.refresh(post)
    return post


@router.post("/{post_id}/schedule", response_model=PostOut)
def schedule_post(post_id: int, body: ScheduleRequest, db: Session = Depends(get_db)):
    post = _get_or_404(db, post_id)
    if post.status == PostStatus.published:
        raise HTTPException(400, "Post is already published")
    post.scheduled_at = body.scheduled_at
    post.status = PostStatus.to_be_published
    if body.network:
        post.network = body.network
    if post.network == Network.wordpress:
        post.caption_length_words = max(500, post.caption_length_words or 500)
    db.commit()
    db.refresh(post)
    return post


@router.post("/{post_id}/generate-blog", response_model=PostOut)
def generate_blog(post_id: int, db: Session = Depends(get_db)):
    """Generate a full WordPress-style blog article and store it in caption."""
    post = _get_or_404(db, post_id)
    chars = _get_chars(_post_character_ids(post))
    char = _char_for_post(chars[0], post.language)
    topic = post.caption_prompt or post.scene
    co_char_hint = _co_character_caption_hint(chars)
    if co_char_hint:
        topic += f"\n\nPeople context: {co_char_hint.strip()}"
    post.caption = blog_post(topic, mood=post.mood or "casual", char=char, min_words=_caption_word_target(post) or 500)
    post.network = Network.wordpress
    post.caption_length_words = max(500, post.caption_length_words or 500)
    db.commit()
    db.refresh(post)
    return post


@router.post("/{post_id}/generate-thread", response_model=PostOut)
def generate_thread(post_id: int, db: Session = Depends(get_db)):
    """Generate a Twitter/X thread (numbered tweets) and store it in caption."""
    post = _get_or_404(db, post_id)
    chars = _get_chars(_post_character_ids(post))
    char = _char_for_post(chars[0], post.language)
    topic = post.caption_prompt or post.scene
    co_char_hint = _co_character_caption_hint(chars)
    if co_char_hint:
        topic += f"\n\nPeople context: {co_char_hint.strip()}"
    post.caption = twitter_thread(topic, mood=post.mood or "casual", char=char)
    post.network = Network.twitter
    db.commit()
    db.refresh(post)
    return post


@router.delete("/{post_id}", status_code=204)
def delete_post(post_id: int, db: Session = Depends(get_db)):
    post = _get_or_404(db, post_id)
    db.delete(post)
    db.commit()


@router.post("/{post_id}/reset", response_model=PostOut)
def reset_post(post_id: int, db: Session = Depends(get_db)):
    """Reset a failed or published post back to pending so it can be rescheduled."""
    post = _get_or_404(db, post_id)
    post.status = PostStatus.pending
    post.scheduled_at = None
    post.published_at = None
    post.publish_error = None
    db.commit()
    db.refresh(post)
    return post


@router.post("/{post_id}/post-to-x", response_model=PostOut)
def post_to_x(post_id: int, db: Session = Depends(get_db)):
    """Immediately post to Twitter/X. Uses caption as tweet text; attaches first media image if present."""
    from datetime import timezone
    from platforms.twitter import post_tweet, has_credentials

    if not has_credentials():
        raise HTTPException(400, "Twitter credentials not configured — add them in Settings → X / Twitter")

    post = db.query(Post).options(joinedload(Post.media_items)).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(404, "Post not found")
    if not post.caption:
        raise HTTPException(400, "Post has no caption — generate one first")

    primary = next((m for m in sorted(post.media_items, key=lambda m: m.position) if m.file_path), None)
    media_path = Path(primary.file_path) if primary else None

    tweet_id = post_tweet(post.caption, media_path=media_path)

    post.status = PostStatus.published
    post.published_at = datetime.now(timezone.utc).replace(tzinfo=None)
    post.publish_error = None
    post.network = Network.twitter
    db.commit()
    db.refresh(post)
    return post
