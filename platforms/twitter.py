"""
Post to Twitter/X via API v2 (OAuth 1.0a User Context).

Credentials (all four required):
  consumer_key        — service: twitter_consumer_key
  consumer_secret     — service: twitter_consumer_secret
  access_token        — service: twitter_access_token
  access_token_secret — service: twitter_access_token_secret

Media upload uses the v1.1 endpoint (still required for media attachments).
Tweet creation uses v2.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def _creds() -> tuple[str, str, str, str]:
    from core.api_keys import get_key
    ck  = get_key("twitter_consumer_key")
    cs  = get_key("twitter_consumer_secret")
    at  = get_key("twitter_access_token")
    ats = get_key("twitter_access_token_secret")
    missing = [n for n, v in [
        ("consumer_key", ck), ("consumer_secret", cs),
        ("access_token", at), ("access_token_secret", ats),
    ] if not v]
    if missing:
        raise RuntimeError(f"Twitter credentials missing: {', '.join(missing)}")
    return ck, cs, at, ats


def _client():
    import tweepy
    ck, cs, at, ats = _creds()
    return tweepy.Client(
        consumer_key=ck, consumer_secret=cs,
        access_token=at, access_token_secret=ats,
    )


def _v1_api():
    """v1.1 API — needed only for media upload."""
    import tweepy
    ck, cs, at, ats = _creds()
    auth = tweepy.OAuth1UserHandler(ck, cs, at, ats)
    return tweepy.API(auth)


def post_tweet(text: str, media_path: Optional[Path] = None) -> str:
    """
    Post a tweet. Returns the tweet ID.
    If media_path is provided, uploads the image/video first and attaches it.
    """
    client = _client()
    media_ids = None

    if media_path and Path(media_path).exists():
        api = _v1_api()
        ext = Path(media_path).suffix.lower()
        if ext in ('.mp4', '.mov'):
            media = api.media_upload(str(media_path), media_category="tweet_video", chunked=True)
            # Video processing — wait for it
            import time
            for _ in range(30):
                info = api.get_media_upload_status(media.media_id)
                state = info.processing_info.get("state", "")
                if state == "succeeded":
                    break
                if state == "failed":
                    raise RuntimeError("Twitter video processing failed")
                time.sleep(info.processing_info.get("check_after_secs", 3))
        else:
            media = api.media_upload(str(media_path))
        media_ids = [media.media_id]

    kwargs: dict = {"text": text}
    if media_ids:
        kwargs["media_ids"] = media_ids

    resp = client.create_tweet(**kwargs)
    tweet_id = str(resp.data["id"])
    print(f"[twitter] Tweet posted: {tweet_id}")
    return tweet_id


def has_credentials() -> bool:
    try:
        _creds()
        return True
    except RuntimeError:
        return False
