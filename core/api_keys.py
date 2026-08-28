"""
Resolve API keys: DB (active row) → env var fallback.
"""
from __future__ import annotations

import os


_ENV_VARS = {
    "replicate":               "REPLICATE_API_TOKEN",
    "elevenlabs":              "ELEVENLABS_API_KEY",
    "anthropic":               "ANTHROPIC_API_KEY",
    "openai":                  "OPENAI_API_KEY",
    "xai":                     "XAI_API_KEY",
    "twitter_consumer_key":    "TWITTER_CONSUMER_KEY",
    "twitter_consumer_secret": "TWITTER_CONSUMER_SECRET",
    "twitter_access_token":    "TWITTER_ACCESS_TOKEN",
    "twitter_access_token_secret": "TWITTER_ACCESS_TOKEN_SECRET",
}


def get_key(service: str) -> str:
    """Return the active key for the service, falling back to the env var."""
    try:
        from db.database import SessionLocal
        from db.models import ApiKey
        db = SessionLocal()
        try:
            row = db.query(ApiKey).filter(
                ApiKey.service == service,
                ApiKey.is_active == True,
            ).first()
            if row and row.key_value:
                return row.key_value
        finally:
            db.close()
    except Exception:
        pass
    return os.getenv(_ENV_VARS.get(service, ""), "")
