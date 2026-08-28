"""
Apartment render pipeline.

Generates photorealistic reference images of Alex's apartment in Buenos Aires.
These are establishing shots (no person) used to feed the LoRA training
and maintain visual consistency across posts set in the apartment.

Each render is saved to output/renders/<room>_<n>.jpg
"""

from __future__ import annotations

import os
import uuid
import httpx
import replicate
from pathlib import Path

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./output")) / "renders"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# flux-1.1-pro: best quality (~$0.04/img). flux-schnell: fast & cheap (~$0.003/img).
MODEL = os.getenv("RENDER_MODEL", "black-forest-labs/flux-1.1-pro")

STYLE = (
    "photorealistic interior photography, 35mm lens, natural light, "
    "film grain, high detail, architectural photography, lived-in feel, "
    "no people, no text, no watermark"
)

NEGATIVE = (
    "cartoon, render, cgi, illustration, painting, 3d render, "
    "ugly, distorted, deformed, blurry, low quality, watermark, text, "
    "people, person, figure, staged, sterile, showroom"
)

# Every room gets a dict with:
#   key       → slug used in filename
#   shots     → list of (prompt_suffix, aspect_ratio) tuples
SCENES: list[dict] = [
    {
        "key": "building_facade",
        "shots": [
            (
                "exterior facade of a classic pre-war residential apartment building "
                "in Palermo or Recoleta, Buenos Aires, Argentina. ornate stone facade, "
                "tall iron balconies with plants, large windows with wood shutters, "
                "street level view, morning light, cobblestone sidewalk",
                "16:9",
            ),
            (
                "close-up of ornate building entrance door and intercom panel, "
                "classic Buenos Aires residential building, brass hardware, "
                "decorative plaster arch, tiled entrance floor visible inside, "
                "warm afternoon light",
                "4:5",
            ),
        ],
    },
    {
        "key": "elevator",
        "shots": [
            (
                "classic old hydraulic cage elevator inside a Buenos Aires apartment building. "
                "ornate wrought-iron outer sliding gate, folding inner wood-and-glass door, "
                "small elevator cabin with mirror on the back wall, brass call button panel, "
                "warm incandescent bulb, decorative plaster landing walls with moldings, "
                "black-and-white hexagonal tile floor on the landing",
                "4:5",
            ),
            (
                "looking up the elevator shaft of a vintage Buenos Aires building, "
                "ornate iron cage elevator visible ascending, decorative railings on each floor, "
                "warm incandescent light, plaster walls with moldings, high ceilings",
                "4:5",
            ),
        ],
    },
    {
        "key": "hallway",
        "shots": [
            (
                "apartment hallway landing of an old Buenos Aires building. "
                "tiled black-and-white floor, high ceiling, decorative plaster moldings, "
                "warm incandescent wall sconce, two apartment doors with brass handles, "
                "small potted plant in the corner, slightly dim intimate lighting",
                "4:5",
            ),
        ],
    },
    {
        "key": "living_room",
        "shots": [
            (
                "living room of a Buenos Aires apartment. high ceilings (3.5m) with decorative "
                "plaster moldings. parquet hardwood floor. large light gray L-shaped corner sofa. "
                "rectangular coffee table on a fluffy cream shaggy rug. flat screen TV on a "
                "black industrial metal rack system. tall windows with natural morning light. "
                "round industrial dining table with black metal legs near the kitchen. "
                "lived-in cozy feel",
                "16:9",
            ),
            (
                "close-up of the gray corner sofa area, fluffy cream shaggy rug, "
                "industrial coffee table with a book and a mug on it, "
                "warm morning light through tall windows, "
                "Buenos Aires apartment, parquet floor, high ceilings visible",
                "4:5",
            ),
            (
                "round industrial dining table with black metal legs, "
                "two or three wooden chairs, morning sunrise light through tall window, "
                "open kitchen visible in the background, Buenos Aires apartment, "
                "journal and pen and a Starbucks cup on the table",
                "4:5",
            ),
        ],
    },
    {
        "key": "office",
        "shots": [
            (
                "home office study in a Buenos Aires apartment. "
                "floor-to-ceiling wooden bookshelf completely filled with books covering the entire wall. "
                "white modern standing desk against the opposite wall, clean surface with MacBook. "
                "large comfortable reading armchair in warm fabric beside the desk. "
                "round ottoman puff on the parquet floor. "
                "good natural window light, warm and focused atmosphere, high ceilings",
                "16:9",
            ),
            (
                "close-up of the floor-to-ceiling bookshelf wall in a home office, "
                "wooden shelves completely packed with books of all sizes and colors, "
                "small decorative objects between books, warm ambient light, "
                "parquet floor visible at the base, Buenos Aires apartment",
                "4:5",
            ),
            (
                "white standing desk in a home office, MacBook open on the desk, "
                "clean minimalist surface, bookshelf wall blurred in the background, "
                "comfortable armchair partially visible to the side, natural window light, "
                "Buenos Aires apartment",
                "4:5",
            ),
        ],
    },
    {
        "key": "bedroom",
        "shots": [
            (
                "bedroom of a Buenos Aires apartment. queen bed with neutral linen bedding "
                "centered against the wall. two white minimalist nightstands with small lamps. "
                "large wooden dresser with a 50-inch flat screen TV on top. "
                "parquet hardwood floor. tall windows with white linen curtains letting in "
                "soft morning light. clean and minimal, no clutter. high ceilings.",
                "16:9",
            ),
            (
                "close-up of the white nightstand area in a minimal bedroom, "
                "small lamp, book and phone on the nightstand, "
                "neutral linen bedding, soft morning window light, "
                "Buenos Aires apartment, parquet floor",
                "4:5",
            ),
        ],
    },
    {
        "key": "kitchen",
        "shots": [
            (
                "open kitchen connected to the living room in a Buenos Aires apartment. "
                "modern appliances, white subway tile backsplash, "
                "small breakfast nook in the corner with a table for two and wooden chairs "
                "by a tall window, morning golden light, "
                "Starbucks cup and phone on the breakfast nook table, "
                "parquet floor, high ceilings visible",
                "16:9",
            ),
            (
                "breakfast nook close-up in a Buenos Aires apartment kitchen, "
                "small square table for two by a tall window, "
                "soft morning light flooding in, Starbucks cup and a Kindle on the table, "
                "warm and quiet morning atmosphere",
                "4:5",
            ),
        ],
    },
    {
        "key": "bathroom",
        "shots": [
            (
                "clean minimal bathroom in a Buenos Aires apartment. "
                "white subway tiles, pedestal or under-mount sink with chrome fittings, "
                "frameless mirror with a warm sconce, small wooden shelf with toiletries, "
                "good lighting, classic and functional",
                "4:5",
            ),
        ],
    },
]


def _generate_one(prompt_suffix: str, aspect_ratio: str, retries: int = 4) -> Path:
    import time
    full_prompt = f"{prompt_suffix}, {STYLE}"

    for attempt in range(retries):
        try:
            output = replicate.run(
                MODEL,
                input={
                    "prompt": full_prompt,
                    "negative_prompt": NEGATIVE,
                    "aspect_ratio": aspect_ratio,
                    "output_format": "jpg",
                    "output_quality": 95,
                    "safety_tolerance": 5,
                },
            )
            break
        except Exception as e:
            if "429" in str(e) and attempt < retries - 1:
                wait = 15 * (attempt + 1)
                print(f"[renders]   rate limited, waiting {wait}s…")
                time.sleep(wait)
            else:
                raise

    url = output[0] if isinstance(output, list) else str(output)
    filename = OUTPUT_DIR / f"{uuid.uuid4().hex}.jpg"

    with httpx.stream("GET", url) as r:
        r.raise_for_status()
        with open(filename, "wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)

    # Pause between calls to stay within rate limits
    import time
    time.sleep(12)

    return filename


def generate_all(only: list[str] | None = None) -> dict[str, list[Path]]:
    """
    Generate all apartment renders.

    Args:
        only: Optional list of room keys to generate (e.g. ["living_room", "office"]).
              Generates everything if None.

    Returns:
        Dict mapping room key → list of saved file paths.
    """
    results: dict[str, list[Path]] = {}

    scenes = [s for s in SCENES if only is None or s["key"] in only]

    total = sum(len(s["shots"]) for s in scenes)
    done = 0

    for scene in scenes:
        key = scene["key"]
        paths: list[Path] = []
        print(f"\n[renders] ── {key.upper().replace('_', ' ')} ({'·' * len(scene['shots'])})")

        for i, (prompt, aspect) in enumerate(scene["shots"]):
            done += 1
            print(f"[renders]   shot {i+1}/{len(scene['shots'])}  ({done}/{total} total)…")
            path = _generate_one(prompt, aspect)
            # Rename to a readable filename
            readable = OUTPUT_DIR / f"{key}_{i+1:02d}_{path.stem[:8]}.jpg"
            path.rename(readable)
            paths.append(readable)
            print(f"[renders]   → {readable.name}")

        results[key] = paths

    print(f"\n[renders] Done. {total} images saved to {OUTPUT_DIR}")
    return results
