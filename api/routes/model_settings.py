from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import ModelSetting, UsageLog
from core.usage import DEFAULTS

router = APIRouter(prefix="/api/model-settings", tags=["model-settings"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class ModelSettingIn(BaseModel):
    service: str
    use_case: str
    model_name: str
    price_per_unit: float = 0.0
    price_per_output_unit: float = 0.0
    unit_label: str = "image"


class ModelSettingOut(BaseModel):
    id: int
    service: str
    use_case: str
    model_name: str
    price_per_unit: float
    price_per_output_unit: float
    unit_label: str
    updated_at: datetime

    class Config:
        from_attributes = True


class UsageLogOut(BaseModel):
    id: int
    service: str
    use_case: str
    model: str
    units: float
    output_units: float
    cost_usd: float
    meta: Optional[dict]
    created_at: datetime

    class Config:
        from_attributes = True


class UsageSummary(BaseModel):
    service: str
    use_case: str
    model: str
    count: int
    total_cost_usd: float


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=List[ModelSettingOut])
def list_settings(db: Session = Depends(get_db)):
    return db.query(ModelSetting).order_by(ModelSetting.service, ModelSetting.use_case).all()


@router.get("/defaults")
def get_defaults():
    """Return the built-in default models and prices for all use-cases."""
    return [
        {
            "service": svc,
            "use_case": uc,
            "model_name": model,
            "price_per_unit": p_in,
            "price_per_output_unit": p_out,
            "unit_label": label,
        }
        for (svc, uc), (model, p_in, p_out, label) in DEFAULTS.items()
    ]


@router.put("/{service}/{use_case}", response_model=ModelSettingOut)
def upsert_setting(service: str, use_case: str, body: ModelSettingIn, db: Session = Depends(get_db)):
    """Create or update the model setting for a service/use-case."""
    row = db.query(ModelSetting).filter(
        ModelSetting.service == service,
        ModelSetting.use_case == use_case,
    ).first()
    if row:
        row.model_name = body.model_name
        row.price_per_unit = body.price_per_unit
        row.price_per_output_unit = body.price_per_output_unit
        row.unit_label = body.unit_label
    else:
        row = ModelSetting(
            service=service,
            use_case=use_case,
            model_name=body.model_name,
            price_per_unit=body.price_per_unit,
            price_per_output_unit=body.price_per_output_unit,
            unit_label=body.unit_label,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{service}/{use_case}", status_code=204)
def reset_setting(service: str, use_case: str, db: Session = Depends(get_db)):
    """Delete the override — reverts to built-in default."""
    row = db.query(ModelSetting).filter(
        ModelSetting.service == service,
        ModelSetting.use_case == use_case,
    ).first()
    if row:
        db.delete(row)
        db.commit()


# ── Usage log ─────────────────────────────────────────────────────────────────

@router.get("/usage", response_model=List[UsageLogOut])
def list_usage(
    days: int = Query(30, ge=1, le=365),
    service: Optional[str] = None,
    limit: int = Query(200, le=1000),
    db: Session = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(days=days)
    q = db.query(UsageLog).filter(UsageLog.created_at >= since)
    if service:
        q = q.filter(UsageLog.service == service)
    return q.order_by(UsageLog.created_at.desc()).limit(limit).all()


@router.get("/usage/summary")
def usage_summary(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)):
    """Aggregated cost by service/use_case/model for the last N days."""
    since = datetime.utcnow() - timedelta(days=days)
    rows = (
        db.query(
            UsageLog.service,
            UsageLog.use_case,
            UsageLog.model,
            sqlfunc.count(UsageLog.id).label("count"),
            sqlfunc.sum(UsageLog.cost_usd).label("total_cost_usd"),
        )
        .filter(UsageLog.created_at >= since)
        .group_by(UsageLog.service, UsageLog.use_case, UsageLog.model)
        .order_by(sqlfunc.sum(UsageLog.cost_usd).desc())
        .all()
    )
    # Total by period
    total = db.query(sqlfunc.sum(UsageLog.cost_usd)).filter(UsageLog.created_at >= since).scalar() or 0.0
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_total = db.query(sqlfunc.sum(UsageLog.cost_usd)).filter(UsageLog.created_at >= today).scalar() or 0.0
    week_start = datetime.utcnow() - timedelta(days=7)
    week_total = db.query(sqlfunc.sum(UsageLog.cost_usd)).filter(UsageLog.created_at >= week_start).scalar() or 0.0

    return {
        "today": round(today_total, 4),
        "week": round(week_total, 4),
        "period_days": days,
        "period_total": round(float(total), 4),
        "by_model": [
            {
                "service": r.service, "use_case": r.use_case, "model": r.model,
                "count": r.count, "total_cost_usd": round(float(r.total_cost_usd or 0), 4),
            }
            for r in rows
        ],
    }
