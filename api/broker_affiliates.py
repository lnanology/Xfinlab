"""2026-07-31 (monetization batch, task #599): public endpoint backing the
neutral "explore brokers" CTA shown under analysis results (see
services/broker_affiliate_config.py for why every URL starts out empty,
and js/broker-cta.js for the frontend widget that calls this).
"""
from typing import Optional

from fastapi import APIRouter

from services.broker_affiliate_config import get_active_brokers

router = APIRouter()


@router.get("/broker-affiliates")
def broker_affiliates(region: Optional[str] = None):
    """Public, unauthenticated -- returns [] until at least one broker in
    services/broker_affiliate_config.py has a real affiliate_url set.
    Intentionally NOT gated behind login/plan tier: this is a neutral
    informational panel, not a premium feature."""
    return {"brokers": get_active_brokers(region)}
