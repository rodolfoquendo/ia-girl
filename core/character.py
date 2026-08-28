"""
Character loading.

load(character_id)  → loads from DB, returns standard dict
load_yaml()         → loads from character.yaml (used only for seeding)

The returned dict always has the same shape so image_gen, content_gen,
renders, etc. need no changes.
"""

from __future__ import annotations
from typing import Optional


def load(character_id: Optional[int] = None) -> dict:
    """
    Load a character from the database.

    If character_id is None, returns the first active character.
    Raises RuntimeError if no characters exist.
    """
    from db.database import SessionLocal
    from db.models import Character
    from sqlalchemy.orm import selectinload

    db = SessionLocal()
    try:
        opts = (selectinload(Character.languages), selectinload(Character.media))
        if character_id is not None:
            char = db.query(Character).options(*opts).filter(Character.id == character_id).first()
        else:
            char = db.query(Character).options(*opts).filter(Character.is_active == True).first()

        if not char:
            raise RuntimeError("No characters in the database. Run the API once to seed the default character.")

        return _to_dict(char)
    finally:
        db.close()


def load_yaml(path: str = "character.yaml") -> dict:
    """Load from character.yaml — used only for seeding the first character."""
    import yaml
    from pathlib import Path
    with open(Path(path)) as f:
        return yaml.safe_load(f)


def _to_dict(char) -> dict:
    """Convert a Character ORM object to the standard character dict."""
    reference_prompts = []
    for media in (char.media or []):
        file_type = getattr(media.file_type, "value", media.file_type)
        prompt = (media.prompt or "").strip()
        if file_type == "photo" and prompt:
            reference_prompts.append(prompt)

    return {
        "id": char.id,
        "name": char.name,
        "full_name": char.full_name,
        "age": char.age,
        "nationality": char.nationality,
        "location": char.location,
        "personality": {
            "traits": char.personality_traits or [],
            "interests": char.personality_interests or [],
            "language_style": char.language_style or "",
        },
        "visual": {
            "base_prompt": char.visual_base_prompt or "",
            "style": char.visual_style or "",
            "negative_prompt": char.visual_negative_prompt or "",
            "settings": char.visual_settings or [],
            "reference_prompts": reference_prompts,
        },
        "posting": {
            "frequency_per_week": char.posting_frequency,
            "best_times_utc": char.posting_times_utc or [],
        },
        "platforms": {
            "instagram": {
                "enabled": char.instagram_enabled,
                "username": char.instagram_username,
                "content_types": ["photo", "reel", "story"],
            },
            "tiktok": {
                "enabled": char.tiktok_enabled,
                "session_id": char.tiktok_session_id,
                "content_types": ["video"],
            },
        },
        "voice_id": char.voice_id,
        "character_bible": char.character_bible,
        "trigger_word": char.trigger_word,
        "replicate_model": char.replicate_model,
        "training_status": char.training_status,
        "languages": [
            {"code": l.language_code, "name": l.language_name, "is_primary": l.is_primary, "proficiency": l.proficiency}
            for l in (char.languages or [])
        ],
        "context": {},
    }


def yaml_to_db_fields(y: dict) -> dict:
    """Convert a YAML character dict to Character model kwargs."""
    return {
        "name": y.get("name", "Unknown"),
        "full_name": y.get("full_name"),
        "age": y.get("age"),
        "nationality": y.get("nationality"),
        "location": y.get("location"),
        "personality_traits": y.get("personality", {}).get("traits", []),
        "personality_interests": y.get("personality", {}).get("interests", []),
        "language_style": y.get("personality", {}).get("language_style", ""),
        "visual_base_prompt": y.get("visual", {}).get("base_prompt", ""),
        "visual_style": y.get("visual", {}).get("style", ""),
        "visual_negative_prompt": y.get("visual", {}).get("negative_prompt", ""),
        "visual_settings": y.get("visual", {}).get("settings", []),
        "posting_frequency": y.get("posting", {}).get("frequency_per_week", 5),
        "posting_times_utc": y.get("posting", {}).get("best_times_utc", []),
        "instagram_enabled": y.get("platforms", {}).get("instagram", {}).get("enabled", True),
        "tiktok_enabled": y.get("platforms", {}).get("tiktok", {}).get("enabled", True),
    }


# Keep these helpers working unchanged for image_gen / content_gen / renders

def base_image_prompt(char: dict) -> str:
    return char["visual"]["base_prompt"].strip()


def negative_prompt(char: dict) -> str:
    return char["visual"]["negative_prompt"].strip()


def reference_image_prompt(char: dict) -> str:
    refs = []
    seen = set()
    for prompt in char.get("visual", {}).get("reference_prompts", []) or []:
        prompt = prompt.strip()
        key = prompt.lower()
        if prompt and key not in seen:
            refs.append(prompt)
            seen.add(key)
    if not refs:
        return ""
    return "Character reference image prompts: " + "; ".join(refs)


def persona_system_prompt(char: dict) -> str:
    p = char["personality"]
    traits = ", ".join(p["traits"])
    interests = ", ".join(p["interests"])
    style = p["language_style"].strip()
    ctx = char.get("context", {})
    apartment = ctx.get("apartment", {})
    apt_note = ""
    if apartment:
        rooms = apartment.get("rooms", {})
        living = rooms.get("living_room", {}).get("description", "")
        if living:
            apt_note = f"\nYour apartment: {apartment.get('location', '')}. Living room: {living}"

    langs = char.get("languages", [])
    primary = next((l for l in langs if l["is_primary"]), langs[0] if langs else None)
    lang_note = ""
    if primary:
        other_langs = [l["name"] for l in langs if not l["is_primary"]]
        lang_note = f"\nWrite in {primary['name']}."
        if other_langs:
            lang_note += f" You also speak: {', '.join(other_langs)}."

    return (
        f"You are {char['name']}, a {char['age']}-year-old {char['nationality']} "
        f"living in {char['location']}.\n"
        f"Your personality: {traits}.\n"
        f"Your interests: {interests}.\n"
        f"{apt_note}{lang_note}\n\n"
        f"Writing style:\n{style}"
    )
