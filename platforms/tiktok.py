"""
TikTok adapter.

TikTok doesn't have an official upload API for individual creators,
so we use the TikTokApi library (browser automation via Playwright)
for reading data, and the TikTok Content Posting API for uploads
when you have a developer account.

For personal use without a dev account, the upload() function
saves the video to a staging folder and prints instructions.
"""

import os
import shutil
from pathlib import Path

STAGING_DIR = Path(os.getenv("OUTPUT_DIR", "./output")) / "tiktok_staging"
STAGING_DIR.mkdir(parents=True, exist_ok=True)


def upload(video_path: Path, caption: str) -> None:
    """
    Stage a TikTok video for upload.

    If TIKTOK_SESSION_ID is set, attempts API upload.
    Otherwise copies to staging folder with a caption sidecar file.
    """
    session_id = os.getenv("TIKTOK_SESSION_ID")

    if session_id:
        _api_upload(video_path, caption, session_id)
    else:
        _stage_for_manual_upload(video_path, caption)


def _api_upload(video_path: Path, caption: str, session_id: str) -> None:
    """
    Upload via TikTok Content Posting API (requires approved developer access).
    https://developers.tiktok.com/doc/content-posting-api-get-started
    """
    import httpx

    # Step 1: Initialize upload
    with httpx.Client() as http:
        init_resp = http.post(
            "https://open.tiktokapis.com/v2/post/publish/video/init/",
            headers={
                "Authorization": f"Bearer {session_id}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            json={
                "post_info": {
                    "title": caption[:2200],  # TikTok caption limit
                    "privacy_level": "PUBLIC_TO_EVERYONE",
                    "disable_duet": False,
                    "disable_comment": False,
                    "disable_stitch": False,
                },
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": video_path.stat().st_size,
                    "chunk_size": video_path.stat().st_size,
                    "total_chunk_count": 1,
                },
            },
        )
        init_resp.raise_for_status()
        data = init_resp.json()["data"]
        publish_id = data["publish_id"]
        upload_url = data["upload_url"]

    # Step 2: Upload video binary
    with open(video_path, "rb") as f:
        video_bytes = f.read()

    with httpx.Client() as http:
        up_resp = http.put(
            upload_url,
            content=video_bytes,
            headers={
                "Content-Type": "video/mp4",
                "Content-Range": f"bytes 0-{len(video_bytes)-1}/{len(video_bytes)}",
            },
        )
        up_resp.raise_for_status()

    print(f"[tiktok] Video uploaded. Publish ID: {publish_id}")


def _stage_for_manual_upload(video_path: Path, caption: str) -> None:
    dest = STAGING_DIR / video_path.name
    shutil.copy2(video_path, dest)
    caption_file = dest.with_suffix(".txt")
    caption_file.write_text(caption)
    print(
        f"[tiktok] No TIKTOK_SESSION_ID set. Video staged at:\n"
        f"  Video:   {dest}\n"
        f"  Caption: {caption_file}\n"
        f"Upload manually or set TIKTOK_SESSION_ID for API upload."
    )
