"""
Image generation via Replicate (Flux 1.1 Pro).

Each call returns a local file path to the downloaded image.
The character base prompt is always prepended so visual consistency
is maintained across all generated photos.
"""

from __future__ import annotations

import os
import uuid
import httpx
import replicate
from pathlib import Path

from core.character import load, base_image_prompt, negative_prompt, reference_image_prompt
from core.api_keys import get_key

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Flux 1.1 Pro on Replicate — best photorealism + prompt adherence
MODEL = "black-forest-labs/flux-1.1-pro"


def _load_defaults() -> tuple[str, str, str]:
    """Return (positive, negative, style) from the prompt_defaults singleton row."""
    try:
        from db.database import SessionLocal
        from db.models import PromptDefaults
        db = SessionLocal()
        try:
            row = db.get(PromptDefaults, 1)
            if row:
                return (row.positive or "", row.negative or "", row.style or "")
        finally:
            db.close()
    except Exception:
        pass
    return ("", "", "")


def _load_gen_defaults() -> dict:
    """Return generation params from prompt_defaults (safety, quality, format, etc.)."""
    try:
        from db.database import SessionLocal
        from db.models import PromptDefaults
        db = SessionLocal()
        try:
            row = db.get(PromptDefaults, 1)
            if row:
                return {
                    "safety_tolerance": row.safety_tolerance if row.safety_tolerance is not None else 5,
                    "output_quality": row.output_quality if row.output_quality is not None else 90,
                    "output_format": row.output_format or "jpg",
                    "prompt_upsampling": bool(row.prompt_upsampling),
                    "seed": row.seed,
                    "aspect_ratio": row.aspect_ratio or "4:5",
                }
        finally:
            db.close()
    except Exception:
        pass
    return {"safety_tolerance": 5, "output_quality": 90, "output_format": "jpg",
            "prompt_upsampling": False, "seed": None, "aspect_ratio": "4:5"}


def _effective_gen_params(overrides: dict | None) -> dict:
    """Merge DB defaults with per-image overrides (None values are ignored)."""
    params = _load_gen_defaults()
    if overrides:
        for k, v in overrides.items():
            if v is not None and k in params:
                params[k] = v
    return params


def generate(
    scene: str,
    char: dict | None = None,
    aspect_ratio: str | None = None,
    output_format: str | None = None,
    full_prompt: str | None = None,
    force_base_model: bool = False,
    gen_params: dict | None = None,
    raw: bool = False,
) -> Path:
    """
    Generate a character image for the given scene description.

    Prompt order:
        global_positive → char_base → char_references → outfit → room → scene → char_style → global_style

    The global defaults (prompt_defaults table) are always merged in so every
    character gets the same quality/realism baseline regardless of their individual
    visual fields.
    """
    if char is None:
        char = load()

    eff = _effective_gen_params(gen_params)
    # Function args override gen_params (backward compat for callers that pass aspect_ratio/format directly)
    if aspect_ratio is not None:
        eff["aspect_ratio"] = aspect_ratio
    if output_format is not None:
        eff["output_format"] = output_format

    global_positive, global_negative, global_style = _load_defaults()
    char_neg = negative_prompt(char)
    # Merge negatives: global first so it always wins
    merged_neg = ", ".join(p for p in [global_negative, char_neg] if p)

    trained_model = char.get("replicate_model")
    training_ok = char.get("training_status") == "succeeded"
    if not force_base_model and trained_model and training_ok:
        model_to_use = trained_model
    else:
        from core.usage import get_model as _get_model
        configured = _get_model("replicate", "base_image")
        model_to_use = configured or MODEL

    if raw and full_prompt:
        # User edited the full assembled prompt — send verbatim, no wrapping
        final_prompt = full_prompt
    else:
        if full_prompt is None:
            base = base_image_prompt(char)
            references = reference_image_prompt(char)
            char_style = char["visual"]["style"]
            full_prompt = ", ".join(p for p in [base, references, scene, char_style] if p)

        if trained_model and training_ok:
            trigger = (char.get("trigger_word") or "").strip()
            if trigger and not full_prompt.startswith(trigger):
                full_prompt = f"{trigger}, {full_prompt}"

        # Wrap with globals: quality prefix first, style suffix last
        parts = [p for p in [global_positive, full_prompt, global_style] if p]
        final_prompt = ", ".join(parts)
    if not final_prompt.strip():
        raise ValueError("Prompt is empty — set a character base prompt or provide a scene description.")

    run_input: dict = {
        "prompt": final_prompt,
        "negative_prompt": merged_neg,
        "aspect_ratio": eff["aspect_ratio"],
        "output_format": eff["output_format"],
        "output_quality": eff["output_quality"],
        "safety_tolerance": eff["safety_tolerance"],
        "prompt_upsampling": eff["prompt_upsampling"],
    }
    if eff.get("seed") is not None:
        run_input["seed"] = eff["seed"]

    client = replicate.Client(api_token=get_key("replicate"))
    output = client.run(model_to_use, input=run_input)

    # Replicate returns a URL string, FileOutput object, or list thereof
    item = output[0] if isinstance(output, list) else output
    filename = OUTPUT_DIR / f"{uuid.uuid4().hex}.{eff['output_format']}"

    if hasattr(item, "read"):
        # FileOutput (replicate SDK ≥ 0.25): read directly
        with open(filename, "wb") as f:
            f.write(item.read())
    else:
        url = str(getattr(item, "url", item))
        with httpx.stream("GET", url, timeout=120) as r:
            r.raise_for_status()
            with open(filename, "wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)

    print(f"[image_gen] Saved → {filename}")
    from core.usage import log_usage
    log_usage("replicate", "base_image", model_to_use, units=1.0, meta={"char": char.get("name")})
    return filename


def generate_batch(scenes: list[str], **kwargs) -> list[Path]:
    """Generate multiple images for a content batch."""
    return [generate(scene, **kwargs) for scene in scenes]


def generate_scene(
    prompt: str,
    aspect_ratio: str = "16:9",
    output_format: str = "jpg",
) -> Path:
    """Generate a location/environment image with no character context."""
    global_positive, global_negative, global_style = _load_defaults()
    parts = [p for p in [global_positive, prompt, global_style] if p]
    final_prompt = ", ".join(parts)

    client = replicate.Client(api_token=get_key("replicate"))
    output = client.run(
        MODEL,
        input={
            "prompt": final_prompt,
            "negative_prompt": global_negative or "",
            "aspect_ratio": aspect_ratio,
            "output_format": output_format,
            "output_quality": 90,
            "safety_tolerance": 5,
        },
    )

    url = output[0] if isinstance(output, list) else str(output)
    filename = OUTPUT_DIR / f"{uuid.uuid4().hex}.{output_format}"

    with httpx.stream("GET", url, timeout=120) as r:
        r.raise_for_status()
        with open(filename, "wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)

    print(f"[image_gen] Saved → {filename}")
    return filename
