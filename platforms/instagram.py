"""
Instagram adapter via instagrapi.

Handles login, photo posts, reels, stories, and DM polling.
Session is persisted to disk to avoid re-login on every run.
"""

from __future__ import annotations

import os
import json
from pathlib import Path
from instagrapi import Client
from instagrapi.exceptions import LoginRequired

# Use OUTPUT_DIR so the session file lives alongside generated media,
# not in the working directory where Docker may create a conflicting directory.
_DATA_DIR = Path(os.getenv("OUTPUT_DIR", "./output"))
_DATA_DIR.mkdir(parents=True, exist_ok=True)


def _session_file(username: str) -> Path:
    safe = username.replace("@", "").replace("/", "_")
    return _DATA_DIR / f".ig_session_{safe}.json"


def client_for(username: str, password: str, session_id: str | None = None) -> Client:
    """Return an authenticated instagrapi Client for the given credentials.

    If session_id (browser cookie) is provided, uses it to avoid username/password
    login which Instagram flags as automation.
    """
    session_file = _session_file(username)
    cl = Client()
    cl.delay_range = [2, 5]

    # Prefer session ID login (from browser cookie) — never triggers bot detection.
    # Always start from a blank Client — stale settings from failed logins corrupt
    # the auth state and cause LoginRequired on write operations (account_edit, etc.)
    if session_id:
        try:
            session_file.unlink(missing_ok=True)  # discard any stale session file
            cl.login_by_sessionid(session_id)
            cl.dump_settings(session_file)
            print(f"[instagram] Logged in via session ID for {username}.")
            return cl
        except Exception as e:
            print(f"[instagram] Session ID login failed: {e}")
            raise

    # Fall back to saved session file (no re-login if session is still valid)
    if session_file.is_file():
        try:
            cl.load_settings(session_file)
            cl.set_user(username, password)
            cl.get_timeline_feed()  # verify without re-authenticating
            print(f"[instagram] Resumed session for {username}.")
            return cl
        except LoginRequired:
            print(f"[instagram] Session expired for {username}, re-logging in.")
            session_file.unlink(missing_ok=True)
        except Exception as e:
            print(f"[instagram] Session check failed: {e}, re-logging in.")
            session_file.unlink(missing_ok=True)

    cl.login(username, password)
    cl.dump_settings(session_file)
    print(f"[instagram] Logged in as {username}.")
    return cl


# Legacy env-var-based singleton (kept for backward compat with main.py CLI)
_client: Client | None = None


def client() -> Client:
    global _client
    if _client is None:
        _client = client_for(
            os.environ["INSTAGRAM_USERNAME"],
            os.environ["INSTAGRAM_PASSWORD"],
        )
    return _client


def post_photo(image_path: Path, caption: str) -> str:
    """Upload a photo post. Returns the media ID."""
    cl = client()
    media = cl.photo_upload(str(image_path), caption)
    print(f"[instagram] Photo posted: {media.pk}")
    return str(media.pk)


def post_reel(video_path: Path, caption: str, thumbnail: Path | None = None) -> str:
    """Upload a Reel. Returns the media ID."""
    cl = client()
    media = cl.clip_upload(
        str(video_path),
        caption,
        thumbnail=str(thumbnail) if thumbnail else None,
    )
    print(f"[instagram] Reel posted: {media.pk}")
    return str(media.pk)


def post_story_photo(image_path: Path) -> str:
    """Upload a photo Story."""
    cl = client()
    media = cl.photo_upload_to_story(str(image_path))
    print(f"[instagram] Story posted: {media.pk}")
    return str(media.pk)


def get_pending_dms(limit: int = 20) -> list[dict]:
    """
    Fetch recent unanswered DMs.

    Returns a list of dicts: {thread_id, user_id, username, message}.
    Only returns threads where the last message is from the other person.
    """
    cl = client()
    threads = cl.direct_threads(amount=limit)
    pending = []
    for thread in threads:
        if not thread.messages:
            continue
        last = thread.messages[0]
        # Skip if we sent the last message
        if str(last.user_id) == str(cl.user_id):
            continue
        user = thread.users[0] if thread.users else None
        pending.append({
            "thread_id": str(thread.id),
            "user_id": str(last.user_id),
            "username": user.username if user else "unknown",
            "message": last.text or "",
        })
    return pending


def send_dm(thread_id: str, text: str) -> None:
    """Send a text reply to a DM thread."""
    cl = client()
    cl.direct_send(text, thread_ids=[thread_id])
    print(f"[instagram] DM sent to thread {thread_id}")
