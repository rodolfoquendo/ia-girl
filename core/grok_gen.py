"""
Image generation via xAI Grok (grok-2-image).

Uses the OpenAI-compatible endpoint at api.x.ai/v1.
The key difference from Replicate: no LoRA support, so we compensate with
a rich "character bible" injected into every prompt.
"""

from __future__ import annotations

import os
import uuid
import httpx
from pathlib import Path
from typing import Optional

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

GROK_IMAGE_MODEL = "grok-imagine-image"


def _strip_trigger(text: str, trigger: str) -> str:
    """Remove LoRA trigger word from a text string (case-insensitive, handles trailing comma/space)."""
    if not trigger or not text:
        return text
    import re
    # Match trigger word optionally followed by comma+space or space
    pattern = re.compile(re.escape(trigger) + r'\s*,?\s*', re.IGNORECASE)
    return pattern.sub('', text).strip(', ').strip()


def build_character_bible(char: dict, wardrobe_items: list[dict] | None = None,
                          place: dict | None = None, room: dict | None = None) -> str:
    """
    Build a rich character description for Grok to maintain visual consistency.
    Since Grok doesn't use LoRA weights, everything about the character must live
    in the text prompt. Trigger words (LoRA tokens) are stripped and replaced
    by the full verbal description.
    """
    lines: list[str] = []
    trigger = (char.get("trigger_word") or "").strip()

    # Identity
    name = char.get("name", "")
    age = char.get("age")
    nationality = char.get("nationality", "")
    gender = str(char.get("gender") or "female")
    location = char.get("location", "")

    identity_parts = [p for p in [
        name,
        f"{age} years old" if age else None,
        nationality,
        gender,
        f"based in {location}" if location else None,
    ] if p]
    if identity_parts:
        lines.append(f"CHARACTER: {', '.join(identity_parts)}")

    # Physical appearance — strip trigger word so Grok never sees the LoRA token
    base_prompt = _strip_trigger(
        (char.get("visual", {}).get("base_prompt") or "").strip(),
        trigger,
    )
    if base_prompt:
        lines.append(f"APPEARANCE: {base_prompt}")

    # Structured physical attributes from visual_settings (list of {label, value} dicts)
    settings = char.get("visual", {}).get("settings") or []
    if settings:
        trait_parts = []
        for s in settings:
            if isinstance(s, dict):
                label = s.get("label") or s.get("key") or ""
                value = s.get("value") or ""
                if label and value:
                    trait_parts.append(f"{label}: {value}")
                elif value:
                    trait_parts.append(value)
        if trait_parts:
            lines.append("PHYSICAL TRAITS: " + "; ".join(trait_parts))

    # Reference photo prompts (from character media – labelled shots)
    ref_prompts = char.get("visual", {}).get("reference_prompts") or []
    # Also strip trigger word from any reference prompts
    cleaned_refs = [_strip_trigger(p, trigger) for p in ref_prompts if p]
    cleaned_refs = [p for p in cleaned_refs if p]
    if cleaned_refs:
        lines.append("REFERENCE DETAILS: " + "; ".join(cleaned_refs))

    # Visual style / aesthetic
    style = (char.get("visual", {}).get("style") or "").strip()
    if style:
        lines.append(f"VISUAL STYLE: {style}")

    # Wardrobe
    if wardrobe_items:
        outfit_parts = []
        for w in wardrobe_items:
            parts = [p for p in [
                w.get("prompt_tag") or w.get("name", ""),
                w.get("color"),
                w.get("description"),
            ] if p]
            if parts:
                outfit_parts.append(", ".join(parts))
        if outfit_parts:
            lines.append("OUTFIT: " + "; ".join(outfit_parts))

    # Place / room context
    if place:
        place_parts = [p for p in [place.get("name"), place.get("location"), place.get("building_style")] if p]
        if place_parts:
            lines.append(f"LOCATION: {', '.join(place_parts)}")
        if place.get("building_notes"):
            lines.append(f"LOCATION NOTES: {place['building_notes']}")

    if room:
        room_parts = [p for p in [room.get("name") or room.get("room_type"), room.get("description"), room.get("mood")] if p]
        if room_parts:
            lines.append(f"ROOM: {', '.join(room_parts)}")
        if room.get("render_prompt"):
            lines.append(f"ROOM VISUAL: {room['render_prompt']}")

    return "\n".join(lines)


def generate(
    scene: str,
    char: dict | None = None,
    full_prompt: str | None = None,
    aspect_ratio: str = "4:5",
    wardrobe_items: list[dict] | None = None,
    place: dict | None = None,
    room: dict | None = None,
    raw: bool = False,
) -> Path:
    """
    Generate an image using Grok (xAI) grok-2-image.

    The character bible is prepended so Grok has maximum context about how
    the character looks, what they're wearing, and where they are.
    """
    from openai import OpenAI
    from core.api_keys import get_key
    from core.image_gen import _load_defaults

    xai_key = get_key("xai")
    if not xai_key:
        raise RuntimeError("xAI API key not configured. Add it via Settings → API Keys (service: xai).")

    if char is None:
        from core.character import load
        char = load()

    global_positive, global_negative, global_style = _load_defaults()

    trigger = (char.get("trigger_word") or "").strip()

    if raw and full_prompt:
        # User edited the full assembled prompt — send verbatim, no bible wrapping
        final_prompt = full_prompt
        if len(final_prompt) > 7900:
            final_prompt = final_prompt[:7900]
    else:
        # Use manually saved bible if present, otherwise auto-build
        stored_bible = (char.get("character_bible") or "").strip()
        if stored_bible:
            # Append wardrobe/place/room context on top of the stored base bible
            extra_lines = []
            if wardrobe_items:
                outfit_parts = [", ".join(p for p in [w.get("prompt_tag") or w.get("name",""), w.get("color"), w.get("description")] if p) for w in wardrobe_items]
                extra_lines.append("OUTFIT: " + "; ".join(p for p in outfit_parts if p))
            if place:
                place_parts = [p for p in [place.get("name"), place.get("location"), place.get("building_style")] if p]
                if place_parts: extra_lines.append(f"LOCATION: {', '.join(place_parts)}")
            if room:
                room_parts = [p for p in [room.get("name") or room.get("room_type"), room.get("description"), room.get("mood")] if p]
                if room_parts: extra_lines.append(f"ROOM: {', '.join(room_parts)}")
                if room.get("render_prompt"): extra_lines.append(f"ROOM VISUAL: {room['render_prompt']}")
            bible = stored_bible + ("\n" + "\n".join(extra_lines) if extra_lines else "")
        else:
            bible = build_character_bible(char, wardrobe_items=wardrobe_items, place=place, room=room)

        # Build the scene prompt — strip LoRA trigger word from any text path
        if full_prompt:
            scene_text = _strip_trigger(full_prompt, trigger)
        else:
            scene_text = _strip_trigger(scene, trigger)

        # Assemble: bible first so Grok grounds the character, then scene, then quality hints
        parts = [p for p in [global_positive, bible, scene_text, global_style] if p and p.strip()]
        final_prompt = "\n\n".join(parts)
    # Grok image models cap at 8000 chars — truncate from the end (style suffix is least critical)
    if len(final_prompt) > 7900:
        final_prompt = final_prompt[:7900]

    from core.usage import get_model as _get_model
    model_to_use = _get_model("xai", "grok_image") or GROK_IMAGE_MODEL

    client = OpenAI(api_key=xai_key, base_url="https://api.x.ai/v1")
    response = client.images.generate(
        model=model_to_use,
        prompt=final_prompt,
        n=1,
        response_format="url",
    )

    url = response.data[0].url
    filename = OUTPUT_DIR / f"{uuid.uuid4().hex}.jpg"

    with httpx.stream("GET", url, timeout=120) as r:
        r.raise_for_status()
        with open(filename, "wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)

    print(f"[grok_gen] Saved → {filename}")
    from core.usage import log_usage
    log_usage("xai", "grok_image", model_to_use, units=1.0, meta={"char": char.get("name") if char else None})
    return filename


