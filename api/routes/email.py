from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Character

router = APIRouter(prefix="/api/email", tags=["email"])


def _email_config(char_id: int, db: Session) -> dict:
    char = db.get(Character, char_id)
    if not char:
        raise HTTPException(404, "Character not found")
    return {
        "email_address":  char.email_address,
        "email_password": char.email_password,
        "email_imap_host": char.email_imap_host or "imap.gmail.com",
        "email_imap_port": char.email_imap_port or 993,
        "email_smtp_host": char.email_smtp_host or "smtp.gmail.com",
        "email_smtp_port": char.email_smtp_port or 587,
    }


class SendIn(BaseModel):
    to: str
    subject: str
    body: str
    reply_to_message_id: Optional[str] = None
    references: Optional[str] = None


@router.get("/{char_id}/inbox")
def get_inbox(char_id: int, folder: str = "INBOX", limit: int = 50, db: Session = Depends(get_db)):
    from core.email_client import fetch_inbox
    cfg = _email_config(char_id, db)
    try:
        return fetch_inbox(cfg, folder=folder, limit=limit)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"IMAP error: {e}")


@router.get("/{char_id}/message/{uid}")
def get_message(char_id: int, uid: str, folder: str = "INBOX", db: Session = Depends(get_db)):
    from core.email_client import fetch_message
    cfg = _email_config(char_id, db)
    try:
        return fetch_message(cfg, uid, folder=folder)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"IMAP error: {e}")


@router.get("/{char_id}/folders")
def get_folders(char_id: int, db: Session = Depends(get_db)):
    from core.email_client import list_folders
    cfg = _email_config(char_id, db)
    try:
        return list_folders(cfg)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"IMAP error: {e}")


@router.post("/{char_id}/send")
def send(char_id: int, body: SendIn, db: Session = Depends(get_db)):
    from core.email_client import send_email
    cfg = _email_config(char_id, db)
    try:
        send_email(
            cfg,
            to=body.to,
            subject=body.subject,
            body=body.body,
            reply_to_message_id=body.reply_to_message_id,
            references=body.references,
        )
        return {"ok": True}
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"SMTP error: {e}")
