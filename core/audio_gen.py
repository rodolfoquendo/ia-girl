"""
Audio generation pipeline.

tts(text, voice_id)            → Path to .mp3
podcast_script(a, b, topic)    → [{speaker, text}, ...]
podcast_episode(a, b, topic)   → (Path to mixed .mp3, script)
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Optional

import httpx

from core.api_keys import get_key

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TTS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
ELEVENLABS_BASE = "https://api.elevenlabs.io/v1"


# ── TTS ───────────────────────────────────────────────────────────────────────

def tts(
    text: str,
    voice_id: str,
    output_path: Optional[Path] = None,
    stability: float = 0.5,
    similarity_boost: float = 0.75,
) -> Path:
    """Generate speech for text using an ElevenLabs voice. Returns path to .mp3."""
    el_key = get_key("elevenlabs")
    if not el_key:
        raise RuntimeError("No ElevenLabs API key configured")
    if output_path is None:
        output_path = OUTPUT_DIR / f"{uuid.uuid4().hex}.mp3"

    r = httpx.post(
        f"{ELEVENLABS_BASE}/text-to-speech/{voice_id}",
        headers={"xi-api-key": el_key, "Content-Type": "application/json"},
        json={
            "text": text,
            "model_id": TTS_MODEL,
            "voice_settings": {
                "stability": stability,
                "similarity_boost": similarity_boost,
            },
        },
        timeout=60,
    )
    r.raise_for_status()
    output_path.write_bytes(r.content)
    print(f"[audio_gen] TTS saved → {output_path}")
    return output_path


def list_voices() -> list[dict]:
    """Return all available voices on the ElevenLabs account."""
    el_key = get_key("elevenlabs")
    if not el_key:
        raise RuntimeError("No ElevenLabs API key configured")
    r = httpx.get(
        f"{ELEVENLABS_BASE}/voices",
        headers={"xi-api-key": el_key},
        timeout=15,
    )
    r.raise_for_status()
    return r.json().get("voices", [])


# ── Podcast script ────────────────────────────────────────────────────────────

def podcast_script(
    char_a: dict,
    char_b: dict,
    topic: str,
    exchanges: int = 8,
) -> list[dict]:
    """Use Claude to generate a podcast dialogue. Returns [{speaker, text}, ...]."""
    import anthropic

    client = anthropic.Anthropic(api_key=get_key("anthropic"))
    name_a, name_b = char_a["name"], char_b["name"]

    def _desc(c: dict) -> str:
        parts = []
        if c.get("age"):
            parts.append(f"{c['age']} years old")
        if c.get("nationality"):
            parts.append(c["nationality"])
        if c.get("location"):
            parts.append(f"based in {c['location']}")
        return ", ".join(parts)

    prompt = (
        f"Write a natural, engaging podcast conversation between {name_a} and {name_b} about: {topic}\n\n"
        f"{name_a}: {_desc(char_a)}\n"
        f"{name_b}: {_desc(char_b)}\n\n"
        f"Write {exchanges} exchanges total (each person speaks {exchanges // 2} times, alternating). "
        f"Keep each turn 1–3 natural sentences. Start with {name_a} opening the episode.\n\n"
        f"Return ONLY a valid JSON array, no markdown, no other text:\n"
        f'[{{"speaker": "{name_a}", "text": "..."}}, {{"speaker": "{name_b}", "text": "..."}}, ...]'
    )

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()

    # Strip markdown code fences if model wraps in them
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip().rstrip("```").strip()

    return json.loads(raw)


# ── Episode mixer ─────────────────────────────────────────────────────────────

def podcast_episode(
    char_a: dict,
    char_b: dict,
    topic: str,
    exchanges: int = 8,
) -> tuple[Path, list[dict]]:
    """
    Full pipeline: script → per-line TTS → ffmpeg mix.
    Returns (episode_mp3_path, script_lines).
    """
    voice_map = {
        char_a["name"]: char_a.get("voice_id"),
        char_b["name"]: char_b.get("voice_id"),
    }
    for name, vid in voice_map.items():
        if not vid:
            raise ValueError(f'Character "{name}" has no ElevenLabs voice_id configured')

    script = podcast_script(char_a, char_b, topic, exchanges)

    tmp = Path(tempfile.mkdtemp())
    line_files: list[Path] = []

    for i, line in enumerate(script):
        speaker = line["speaker"]
        voice_id = voice_map.get(speaker)
        if not voice_id:
            continue
        out = tmp / f"line_{i:03d}.mp3"
        tts(line["text"], voice_id, out)
        line_files.append(out)

    if not line_files:
        raise RuntimeError("No audio lines were generated")

    # Write ffmpeg concat list
    concat_list = tmp / "concat.txt"
    concat_list.write_text("\n".join(f"file '{f}'" for f in line_files))

    episode_path = OUTPUT_DIR / f"podcast_{uuid.uuid4().hex}.mp3"
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy",
            str(episode_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr}")

    print(f"[audio_gen] Episode saved → {episode_path}")
    return episode_path, script
