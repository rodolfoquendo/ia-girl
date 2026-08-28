from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from db.database import get_db
from db.models import Post, PostMedia, PostStatus, MediaType, Network, Character, CharacterMedia

router = APIRouter(prefix="/api/podcast", tags=["podcast"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class ScriptLine(BaseModel):
    speaker: str
    text: str


class PodcastScriptRequest(BaseModel):
    character_a_id: int
    character_b_id: int
    topic: str
    exchanges: int = 8


class PodcastEpisodeRequest(BaseModel):
    character_a_id: int
    character_b_id: int
    topic: str
    exchanges: int = 8
    network: Network = Network.instagram
    scheduled_at: Optional[datetime] = None


class PodcastEpisodeOut(BaseModel):
    post_id: int
    audio_path: str
    script: List[ScriptLine]
    duration_hint: str


class VoiceOut(BaseModel):
    voice_id: str
    name: str
    category: Optional[str] = None


class TTSPreviewRequest(BaseModel):
    character_id: int
    text: str


class TTSPreviewOut(BaseModel):
    id: int
    file_path: str
    url: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_char_dict(char: Character) -> dict:
    from core.character import _to_dict
    return _to_dict(char)


def _get_char(db: Session, char_id: int) -> Character:
    c = db.get(Character, char_id)
    if not c:
        raise HTTPException(404, f"Character {char_id} not found")
    return c


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/voices", response_model=List[VoiceOut])
def get_voices():
    """List all ElevenLabs voices available on the account."""
    from core.audio_gen import list_voices
    try:
        voices = list_voices()
        return [VoiceOut(
            voice_id=v["voice_id"],
            name=v["name"],
            category=v.get("category"),
        ) for v in voices]
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/script", response_model=List[ScriptLine])
def generate_script(body: PodcastScriptRequest, db: Session = Depends(get_db)):
    """Generate a podcast dialogue script without producing audio."""
    char_a = _get_char(db, body.character_a_id)
    char_b = _get_char(db, body.character_b_id)
    from core.audio_gen import podcast_script
    try:
        lines = podcast_script(
            _load_char_dict(char_a),
            _load_char_dict(char_b),
            body.topic,
            body.exchanges,
        )
        return [ScriptLine(**l) for l in lines]
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/episode", response_model=PodcastEpisodeOut, status_code=201)
def generate_episode(body: PodcastEpisodeRequest, db: Session = Depends(get_db)):
    """
    Full pipeline: script → TTS per line → ffmpeg mix → save as Post + PostMedia.
    Takes ~60-120 s depending on episode length.
    """
    char_a = _get_char(db, body.character_a_id)
    char_b = _get_char(db, body.character_b_id)

    for c in (char_a, char_b):
        if not c.voice_id:
            raise HTTPException(400, f'Character "{c.name}" has no voice_id set. Add one in the character editor.')

    from core.audio_gen import podcast_episode

    try:
        episode_path, script = podcast_episode(
            _load_char_dict(char_a),
            _load_char_dict(char_b),
            body.topic,
            body.exchanges,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))

    # Build caption from script
    caption_lines = [f"{l['speaker']}: {l['text']}" for l in script]
    caption = f"🎙️ {body.topic}\n\n" + "\n\n".join(caption_lines[:4]) + ("\n\n[...]" if len(script) > 4 else "")

    status = PostStatus.to_be_published if body.scheduled_at else PostStatus.pending
    post = Post(
        character_id=body.character_a_id,
        scene=f"Podcast episode: {body.topic}",
        mood="podcast",
        caption=caption,
        media_type=MediaType.audio,
        network=body.network,
        status=status,
        scheduled_at=body.scheduled_at,
        script=script,
    )
    db.add(post)
    db.flush()

    db.add(PostMedia(
        post_id=post.id,
        character_id=body.character_a_id,
        file_path=str(episode_path),
        file_type=MediaType.audio,
        prompt=f"Podcast: {body.topic} — {char_a.name} & {char_b.name}",
        position=0,
    ))
    db.commit()
    db.refresh(post)

    approx_minutes = len(script) * 15 // 60
    return PodcastEpisodeOut(
        post_id=post.id,
        audio_path=str(episode_path),
        script=[ScriptLine(**l) for l in script],
        duration_hint=f"~{approx_minutes} min",
    )


@router.post("/preview-tts", response_model=TTSPreviewOut, status_code=201)
def preview_tts(body: TTSPreviewRequest, db: Session = Depends(get_db)):
    """Generate a short TTS audio clip from text using the character's voice. Saved as CharacterMedia."""
    from core.audio_gen import ELEVENLABS_KEY, tts
    if not ELEVENLABS_KEY:
        raise HTTPException(400, "ELEVENLABS_API_KEY is not set")
    char = _get_char(db, body.character_id)
    if not char.voice_id:
        raise HTTPException(400, f'Character "{char.name}" has no voice_id set. Add one in Edit Character.')
    try:
        audio_path = tts(body.text, char.voice_id)
    except Exception as e:
        raise HTTPException(500, str(e))
    media = CharacterMedia(
        character_id=char.id,
        file_path=str(audio_path),
        file_type=MediaType.audio,
        prompt=body.text,
        label="voice preview",
        position=999,
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    fname = audio_path.name
    return TTSPreviewOut(id=media.id, file_path=str(audio_path), url=f"/media/{fname}")
