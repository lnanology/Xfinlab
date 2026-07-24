"""
MX Record Verification -- free, self-hosted email deliverability check
(2026-07-24 anti-abuse batch, layer 2 of the registration architecture:
"Email真實存在" audited against services/disposable_email_domains.py's
existing string-match blocklist).

What this checks: whether the email's domain actually has a mail
exchanger (MX record) -- or, per RFC 5321 5.1, an A/AAAA record it can
fall back to -- meaning SOME mail server exists that could plausibly
accept mail for it. This catches typo'd domains (`gmial.com`), made-up
domains (`fake-domain.com`), and domains that exist for other purposes
but run no mail service at all.

Deliberately scoped to MX-lookup only, NOT a full SMTP RCPT-TO probe
(actually connecting to the mail server and asking "does this specific
mailbox exist"). That's a well-known unreliable technique in practice:
many mail providers (Gmail included) don't answer RCPT TO honestly to
avoid enabling spammer address-harvesting, some silently accept-then-
bounce (catch-all), and probing from a cloud host's IP risks that IP
being flagged/blocked by receiving mail servers as spam-like behaviour.
An MX-only check is the honest, reliable subset of "layer 2" that can
actually be built for free without those failure modes -- this is a
known, stated scope limitation, not a silent omission, matching this
codebase's established practice (see services/backtest_service.py's own
docstring for the same convention).

Fails OPEN on any DNS error/timeout other than a definitive "this domain
doesn't exist" or "this domain has no mail capability" answer -- a
flaky/slow DNS resolver (this runs on every registration, so must not
become a way for infra hiccups to lock out real signups) should never be
the reason a legitimate registration gets rejected. This mirrors
services/audit_log_service.py's count_recent_failed_logins() fail-open
convention.
"""
import logging

logger = logging.getLogger(__name__)

_DNS_TIMEOUT_SECONDS = 3.0


def has_mx_record(email: str) -> bool:
    """True if the email's domain has an MX record, or (per RFC 5321 5.1)
    an A/AAAA record to fall back to. False only on a definitive
    NXDOMAIN/no-mail-capability answer -- never on a timeout or resolver
    error, which fail open (return True) instead."""
    if not email or "@" not in email:
        return False
    domain = email.strip().rsplit("@", 1)[-1].strip().lower()
    if not domain:
        return False

    try:
        import dns.resolver
    except ImportError:
        # dnspython not installed for some reason -- fail open rather than
        # block every single registration on a missing optional dependency.
        logger.warning("dnspython not available -- MX check skipped (fail open)")
        return True

    resolver = dns.resolver.Resolver()
    resolver.timeout = _DNS_TIMEOUT_SECONDS
    resolver.lifetime = _DNS_TIMEOUT_SECONDS

    try:
        answers = resolver.resolve(domain, "MX")
        return len(answers) > 0
    except dns.resolver.NXDOMAIN:
        return False  # domain doesn't exist at all -- definitive
    except dns.resolver.NoAnswer:
        # No MX record, but the domain might still accept mail via a
        # direct A/AAAA record per RFC 5321 5.1 (rare, mostly small
        # personal/self-hosted domains) -- check before concluding
        # there's no mail capability at all.
        try:
            resolver.resolve(domain, "A")
            return True
        except Exception:
            try:
                resolver.resolve(domain, "AAAA")
                return True
            except Exception:
                return False  # confirmed: no MX, no A, no AAAA
    except Exception as e:
        # Timeout, resolver misconfiguration, transient network blip, etc.
        # -- NOT a confirmed "this domain can't receive mail", so fail
        # open rather than block a legitimate signup on a DNS hiccup.
        logger.warning(
            "MX lookup for domain=%s failed/timed out (%s) -- failing open",
            domain, e,
        )
        return True
