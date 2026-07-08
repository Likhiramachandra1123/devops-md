"""Model catalog endpoint — lists available Anthropic models with pricing.

Live list comes from the Anthropic `/v1/models` API (requires ANTHROPIC_API_KEY).
Pricing/context info is joined from the static PRICING table below (Anthropic
does not expose pricing programmatically). Update this table when Anthropic
changes prices or ships new models.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from loguru import logger

from app.config import get_settings
from app.models import ModelInfo, ModelsResponse

router = APIRouter(prefix="/models", tags=["models"])


# id-prefix → pricing metadata. Match by prefix so `-latest` and dated
# suffixes resolve to the same entry.
# Prices in USD per 1M tokens (list price, English tier). Last synced 2026-01.
PRICING: List[Dict[str, Any]] = [
    {
        "prefix": "claude-opus-4",
        "family": "opus",
        "display_name": "Claude Opus 4",
        "context_window": 200_000,
        "input": 15.00,
        "output": 75.00,
        "description": "Highest-quality reasoning. Slow / expensive.",
    },
    {
        "prefix": "claude-sonnet-4",
        "family": "sonnet",
        "display_name": "Claude Sonnet 4",
        "context_window": 200_000,
        "input": 3.00,
        "output": 15.00,
        "description": "Balanced quality + cost. Recommended default for most tasks.",
    },
    {
        "prefix": "claude-haiku-4",
        "family": "haiku",
        "display_name": "Claude Haiku 4",
        "context_window": 200_000,
        "input": 1.00,
        "output": 5.00,
        "description": "Fast + cheap. Good for high-volume simple tasks.",
    },
    {
        "prefix": "claude-3-5-sonnet",
        "family": "sonnet",
        "display_name": "Claude 3.5 Sonnet",
        "context_window": 200_000,
        "input": 3.00,
        "output": 15.00,
        "description": "Previous-gen balanced model.",
    },
    {
        "prefix": "claude-3-5-haiku",
        "family": "haiku",
        "display_name": "Claude 3.5 Haiku",
        "context_window": 200_000,
        "input": 0.80,
        "output": 4.00,
        "description": "Cheapest widely-available model. Great for testing.",
    },
    {
        "prefix": "claude-3-opus",
        "family": "opus",
        "display_name": "Claude 3 Opus",
        "context_window": 200_000,
        "input": 15.00,
        "output": 75.00,
        "description": "Older Opus (superseded by Opus 4).",
    },
    {
        "prefix": "claude-3-haiku",
        "family": "haiku",
        "display_name": "Claude 3 Haiku",
        "context_window": 200_000,
        "input": 0.25,
        "output": 1.25,
        "description": "Legacy Haiku — cheapest ever, but weaker.",
    },
]


def _lookup_pricing(model_id: str) -> Optional[Dict[str, Any]]:
    for row in PRICING:
        if model_id.startswith(row["prefix"]):
            return row
    return None


def _static_fallback() -> List[ModelInfo]:
    """When no API key is set, return the static catalog with placeholder ids."""
    out: List[ModelInfo] = []
    id_map = {
        "claude-opus-4": "claude-opus-4-latest",
        "claude-sonnet-4": "claude-sonnet-4-latest",
        "claude-haiku-4": "claude-haiku-4-latest",
        "claude-3-5-sonnet": "claude-3-5-sonnet-latest",
        "claude-3-5-haiku": "claude-3-5-haiku-latest",
        "claude-3-opus": "claude-3-opus-latest",
        "claude-3-haiku": "claude-3-haiku-20240307",
    }
    for row in PRICING:
        mid = id_map.get(row["prefix"], row["prefix"] + "-latest")
        out.append(
            ModelInfo(
                id=mid,
                display_name=row["display_name"],
                family=row["family"],
                context_window=row["context_window"],
                input_price_per_mtok=row["input"],
                output_price_per_mtok=row["output"],
                description=row.get("description"),
            )
        )
    return out


@router.get("", response_model=ModelsResponse)
def list_models() -> ModelsResponse:
    s = get_settings()
    default_model = s.claude_model

    if not s.anthropic_api_key:
        models = _static_fallback()
        _mark_default(models, default_model)
        return ModelsResponse(models=models, default_model=default_model, source="static")

    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=s.anthropic_api_key)
        # SDK's Models.list() returns paginated results.
        raw = client.models.list(limit=100)
        entries = getattr(raw, "data", []) or []
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Anthropic /models call failed ({e}); falling back to static catalog.")
        models = _static_fallback()
        _mark_default(models, default_model)
        return ModelsResponse(models=models, default_model=default_model, source="static")

    models: List[ModelInfo] = []
    seen: set[str] = set()
    for m in entries:
        mid = getattr(m, "id", None)
        if not mid or mid in seen:
            continue
        seen.add(mid)
        display = getattr(m, "display_name", None) or mid
        created = getattr(m, "created_at", None)
        created_str = created.isoformat() if hasattr(created, "isoformat") else (str(created) if created else None)

        pricing = _lookup_pricing(mid)
        if pricing:
            info = ModelInfo(
                id=mid,
                display_name=pricing["display_name"],
                family=pricing["family"],
                context_window=pricing["context_window"],
                input_price_per_mtok=pricing["input"],
                output_price_per_mtok=pricing["output"],
                created_at=created_str,
                description=pricing.get("description"),
                pricing_known=True,
            )
        else:
            info = ModelInfo(
                id=mid,
                display_name=display,
                family=_infer_family(mid),
                context_window=0,
                input_price_per_mtok=None,
                output_price_per_mtok=None,
                created_at=created_str,
                pricing_known=False,
                description="Pricing unknown — not in local catalog.",
            )
        models.append(info)

    # Sort: known pricing first, then by family (opus, sonnet, haiku), then by name.
    family_order = {"opus": 0, "sonnet": 1, "haiku": 2, "claude": 3}
    models.sort(key=lambda m: (not m.pricing_known, family_order.get(m.family, 9), m.display_name))

    _mark_default(models, default_model)
    return ModelsResponse(models=models, default_model=default_model, source="api")


def _infer_family(model_id: str) -> str:
    if "opus" in model_id:
        return "opus"
    if "sonnet" in model_id:
        return "sonnet"
    if "haiku" in model_id:
        return "haiku"
    return "claude"


def _mark_default(models: List[ModelInfo], default_id: str) -> None:
    for m in models:
        if m.id == default_id or m.id.startswith(default_id.replace("-latest", "")):
            m.is_default = True
