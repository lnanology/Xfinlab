import logging

logger = logging.getLogger(__name__)


class EventBus:
    """
    Minimal in-process, synchronous pub/sub. Written early but never wired
    up to anything real (Phase 3 of XFINLAB_PRODUCTION_ARCHITECTURE.md) --
    first real use is backend/auth/auth.py publishing "user_registered" so
    welcome email / verification email / audit log become independent
    subscribers instead of three inline calls in the endpoint.

    Deliberately simple: no async, no persistence, no cross-process
    delivery. That's fine for the current single-instance Railway
    deployment and for non-critical side effects; anything that MUST
    happen (e.g. actually saving the user row) should stay a direct call,
    not an event, so its failure is never silently swallowed.
    """
    subscribers = {}

    @classmethod
    def subscribe(cls, event, fn):
        cls.subscribers.setdefault(event, []).append(fn)

    @classmethod
    def publish(cls, event, data):
        for fn in cls.subscribers.get(event, []):
            try:
                fn(data)
            except Exception as e:
                # One broken subscriber must never block the others, and
                # must never propagate back to whoever called publish() --
                # publishing an event is fire-and-forget by design.
                logger.warning(
                    "EventBus: subscriber %r for event %r raised: %s",
                    getattr(fn, "__name__", fn), event, e,
                )
