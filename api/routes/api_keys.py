from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import ApiKey

SUPPORTED_SERVICES = {"replicate", "elevenlabs", "anthropic", "openai", "xai"}

router = APIRouter(prefix="/api/api-keys", tags=["api-keys"])


class ApiKeyIn(BaseModel):
    service: str
    label: str
    key_value: str


class ApiKeyOut(BaseModel):
    id: int
    service: str
    label: str
    key_masked: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_masked(cls, row: ApiKey) -> "ApiKeyOut":
        val = row.key_value or ""
        masked = val[:6] + "…" + val[-4:] if len(val) > 10 else "****"
        return cls(
            id=row.id,
            service=row.service,
            label=row.label,
            key_masked=masked,
            is_active=row.is_active,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


@router.get("", response_model=List[ApiKeyOut])
def list_keys(service: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(ApiKey)
    if service:
        q = q.filter(ApiKey.service == service)
    return [ApiKeyOut.from_orm_masked(r) for r in q.order_by(ApiKey.service, ApiKey.created_at).all()]


@router.post("", response_model=ApiKeyOut, status_code=201)
def create_key(body: ApiKeyIn, db: Session = Depends(get_db)):
    if body.service not in SUPPORTED_SERVICES:
        raise HTTPException(400, f"service must be one of: {', '.join(sorted(SUPPORTED_SERVICES))}")
    row = ApiKey(service=body.service, label=body.label, key_value=body.key_value, is_active=False)
    db.add(row)
    db.commit()
    db.refresh(row)
    return ApiKeyOut.from_orm_masked(row)


@router.post("/{key_id}/activate", response_model=List[ApiKeyOut])
def activate_key(key_id: int, db: Session = Depends(get_db)):
    """Set this key as active and deactivate all others for the same service."""
    row = db.get(ApiKey, key_id)
    if not row:
        raise HTTPException(404, "Key not found")
    db.query(ApiKey).filter(ApiKey.service == row.service).update({"is_active": False})
    row.is_active = True
    db.commit()
    rows = db.query(ApiKey).filter(ApiKey.service == row.service).order_by(ApiKey.created_at).all()
    return [ApiKeyOut.from_orm_masked(r) for r in rows]


@router.delete("/{key_id}", status_code=204)
def delete_key(key_id: int, db: Session = Depends(get_db)):
    row = db.get(ApiKey, key_id)
    if not row:
        raise HTTPException(404, "Key not found")
    db.delete(row)
    db.commit()
