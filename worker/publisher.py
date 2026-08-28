"""
Publisher worker — runs on a schedule, picks up to_be_published posts
whose scheduled_at has passed and sends them to the target network.
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from db.database import SessionLocal
from db.models import Post, PostStatus, Network, Character


def publish_due_posts() -> None:
    db: Session = SessionLocal()
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        due = (
            db.query(Post)
            .options(joinedload(Post.media_items))
            .filter(
                Post.status == PostStatus.to_be_published,
                Post.scheduled_at <= now,
            )
            .all()
        )

        if not due:
            return

        print(f"[publisher] {len(due)} post(s) due for publishing.")

        for post in due:
            char = db.get(Character, post.character_id) if post.character_id else None
            try:
                published = _publish(post, char)
                post.status = PostStatus.published
                post.published_at = datetime.now(timezone.utc).replace(tzinfo=None)
                if published:
                    post.publish_error = None
                    print(f"[publisher] Post {post.id} published to {post.network}.")
                else:
                    post.publish_error = "Queued — no platform credentials configured yet."
                    print(f"[publisher] Post {post.id} queued (no credentials).")
            except Exception as exc:
                post.status = PostStatus.failed
                post.publish_error = str(exc)
                print(f"[publisher] Post {post.id} FAILED: {exc}")

        db.commit()
    finally:
        db.close()


def _has_instagram(char: Optional[Character]) -> bool:
    ig_user = (char.instagram_username if char else None) or os.getenv("INSTAGRAM_USERNAME", "")
    ig_session = (char.instagram_session_id if char else None) or ""
    ig_pass = (char.instagram_password if char else None) or os.getenv("INSTAGRAM_PASSWORD", "")
    return bool(ig_user and (ig_session or ig_pass))


def _has_tiktok(char: Optional[Character]) -> bool:
    session = (char.tiktok_session_id if char else None) or os.getenv("TIKTOK_SESSION_ID", "")
    return bool(session)


def _has_twitter() -> bool:
    from platforms.twitter import has_credentials
    return has_credentials()


def _publish(post: Post, char: Optional[Character]) -> bool:
    """Publish post to configured platforms. Returns True if actually sent, False if skipped (no creds)."""
    primary_item = next((m for m in sorted(post.media_items, key=lambda m: m.position) if m.file_path), None)
    media_path = Path(primary_item.file_path) if primary_item else None

    sent = False

    if post.network in (Network.instagram, Network.both):
        if _has_instagram(char):
            _publish_instagram(post, media_path, char)
            sent = True
        else:
            print(f"[publisher] Post {post.id}: Instagram skipped — no credentials.")

    if post.network in (Network.tiktok, Network.both):
        if _has_tiktok(char):
            _publish_tiktok(post, media_path, char)
            sent = True
        else:
            print(f"[publisher] Post {post.id}: TikTok skipped — no credentials.")

    if post.network == Network.twitter:
        if _has_twitter():
            _publish_twitter(post, media_path)
            sent = True
        else:
            print(f"[publisher] Post {post.id}: Twitter skipped — no credentials.")

    if post.network == Network.wordpress:
        sent = True

    return sent


def _publish_instagram(post: Post, media_path: Optional[Path], char: Optional[Character]) -> None:
    import os as _os
    username = (char.instagram_username if char else None) or _os.getenv("INSTAGRAM_USERNAME", "")
    password = (char.instagram_password if char else None) or _os.getenv("INSTAGRAM_PASSWORD", "")
    session_id = (char.instagram_session_id if char else None) or None

    from platforms.instagram import client_for
    cl = client_for(username, password, session_id=session_id)

    if not media_path or not media_path.exists():
        raise FileNotFoundError(f"Media file not found: {media_path}")

    if post.media_type.value == "video":
        cl.clip_upload(str(media_path), post.caption or "")
    else:
        cl.photo_upload(str(media_path), post.caption or "")


def _publish_tiktok(post: Post, media_path: Optional[Path], char: Optional[Character]) -> None:
    from platforms.tiktok import upload

    if not media_path or not media_path.exists():
        raise FileNotFoundError(f"Media file not found: {media_path}")

    upload(media_path, post.caption)


def _publish_twitter(post: Post, media_path: Optional[Path]) -> None:
    from platforms.twitter import post_tweet
    text = post.caption or ""
    post_tweet(text, media_path=media_path)
