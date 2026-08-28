"""
Video generation for Reels/TikTok.

Two modes:
  1. slideshow — combine multiple images into a video with ffmpeg (free, fast)
  2. runway — use Runway ML Gen-3 to animate a single image (paid, cinematic)

Both produce an MP4 at 9:16 aspect ratio ready for upload.
"""

from __future__ import annotations

import os
import uuid
import subprocess
from pathlib import Path

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def slideshow(
    image_paths: list[Path],
    duration_per_image: float = 3.0,
    audio_path: Path | None = None,
    fps: int = 30,
) -> Path:
    """
    Create a slideshow reel from a list of images using ffmpeg.

    Args:
        image_paths: Ordered list of image files.
        duration_per_image: Seconds each image is shown.
        audio_path: Optional background audio (MP3/M4A).
        fps: Output framerate.

    Returns:
        Path to the output MP4.
    """
    if not image_paths:
        raise ValueError("At least one image is required.")

    out_path = OUTPUT_DIR / f"{uuid.uuid4().hex}.mp4"

    # Build ffmpeg concat input file
    concat_file = OUTPUT_DIR / f"{uuid.uuid4().hex}.txt"
    with open(concat_file, "w") as f:
        for img in image_paths:
            f.write(f"file '{img.resolve()}'\n")
            f.write(f"duration {duration_per_image}\n")
        # ffmpeg needs the last file listed twice (no trailing duration)
        f.write(f"file '{image_paths[-1].resolve()}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
        "-r", str(fps),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
    ]

    if audio_path:
        cmd += ["-i", str(audio_path), "-c:a", "aac", "-shortest"]

    cmd.append(str(out_path))

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{result.stderr}")

    concat_file.unlink(missing_ok=True)
    print(f"[video_gen] Slideshow → {out_path}")
    return out_path


def animate_with_runway(image_path: Path, prompt: str) -> Path:
    """
    Animate a single image using Runway ML Gen-3 Alpha Turbo.

    Requires RUNWAY_API_KEY in environment.
    Returns Path to downloaded MP4.
    """
    import httpx
    import time

    api_key = os.getenv("RUNWAY_API_KEY")
    if not api_key:
        raise EnvironmentError("RUNWAY_API_KEY not set.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "X-Runway-Version": "2024-11-06",
        "Content-Type": "application/json",
    }

    # Upload image as base64
    import base64
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    ext = image_path.suffix.lstrip(".")
    image_data_uri = f"data:image/{ext};base64,{b64}"

    # Create task
    with httpx.Client() as client:
        resp = client.post(
            "https://api.dev.runwayml.com/v1/image_to_video",
            headers=headers,
            json={
                "model": "gen3a_turbo",
                "promptImage": image_data_uri,
                "promptText": prompt,
                "duration": 5,
                "ratio": "768:1344",  # ~9:16
            },
            timeout=30,
        )
        resp.raise_for_status()
        task_id = resp.json()["id"]

    # Poll until done
    with httpx.Client() as client:
        while True:
            r = client.get(
                f"https://api.dev.runwayml.com/v1/tasks/{task_id}",
                headers=headers,
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
            status = data.get("status")
            if status == "SUCCEEDED":
                video_url = data["output"][0]
                break
            elif status in ("FAILED", "CANCELLED"):
                raise RuntimeError(f"Runway task {task_id} {status}: {data}")
            time.sleep(5)

    out_path = OUTPUT_DIR / f"{uuid.uuid4().hex}.mp4"
    with httpx.stream("GET", video_url) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)

    print(f"[video_gen] Runway animation → {out_path}")
    return out_path
