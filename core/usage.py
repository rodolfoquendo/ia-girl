"""
Usage logging + model resolution helpers.

Every AI call should call log_usage() after completion so costs are tracked.
get_model(service, use_case) returns the configured model name (or the default).
"""
from __future__ import annotations

from typing import Optional


# ── Default models + prices ───────────────────────────────────────────────────
# (service, use_case) → (model_name, price_per_unit, price_per_output_unit, unit_label)
DEFAULTS: dict[tuple[str, str], tuple[str, float, float, str]] = {
    ("replicate", "base_image"):    ("black-forest-labs/flux-1.1-pro",   0.04, 0.0, "image"),
    ("replicate", "kontext_image"): ("black-forest-labs/flux-kontext-pro", 0.04, 0.0, "image"),
    ("xai",       "grok_image"):    ("grok-imagine-image",                0.07, 0.0, "image"),
    ("anthropic", "caption"):       ("claude-sonnet-4-6",                  3.0, 15.0, "1M tokens"),
    ("anthropic", "content"):       ("claude-sonnet-4-6",                  3.0, 15.0, "1M tokens"),
    ("openai",    "caption"):       ("gpt-4o",                             2.5, 10.0, "1M tokens"),
    ("openai",    "content"):       ("gpt-4o",                             2.5, 10.0, "1M tokens"),
}


def get_model(service: str, use_case: str) -> str:
    """Return the configured model for service/use_case, falling back to DEFAULTS."""
    try:
        from db.database import SessionLocal
        from db.models import ModelSetting
        db = SessionLocal()
        try:
            row = db.query(ModelSetting).filter(
                ModelSetting.service == service,
                ModelSetting.use_case == use_case,
            ).first()
            if row:
                return row.model_name
        finally:
            db.close()
    except Exception:
        pass
    return DEFAULTS.get((service, use_case), (None,))[0] or ""


def _get_prices(service: str, use_case: str, model: str) -> tuple[float, float, str]:
    """Return (price_per_unit, price_per_output_unit, unit_label) for a model."""
    try:
        from db.database import SessionLocal
        from db.models import ModelSetting
        db = SessionLocal()
        try:
            row = db.query(ModelSetting).filter(
                ModelSetting.service == service,
                ModelSetting.use_case == use_case,
            ).first()
            if row:
                return row.price_per_unit, row.price_per_output_unit, row.unit_label
        finally:
            db.close()
    except Exception:
        pass
    d = DEFAULTS.get((service, use_case))
    if d:
        return d[1], d[2], d[3]
    return 0.0, 0.0, "unit"


def log_usage(
    service: str,
    use_case: str,
    model: str,
    units: float = 1.0,
    output_units: float = 0.0,
    meta: Optional[dict] = None,
) -> None:
    """Log one AI call to usage_log. units = images generated or input_tokens/1M."""
    try:
        price_in, price_out, _ = _get_prices(service, use_case, model)
        cost = units * price_in + output_units * price_out

        from db.database import SessionLocal
        from db.models import UsageLog
        db = SessionLocal()
        try:
            row = UsageLog(
                service=service,
                use_case=use_case,
                model=model,
                units=units,
                output_units=output_units,
                cost_usd=cost,
                meta=meta,
            )
            db.add(row)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        print(f"[usage] log failed: {e}")
