"""Slack request signature verification (HMAC-SHA256)."""
from __future__ import annotations

import hashlib
import hmac
import logging
import time

_log = logging.getLogger("prompt_validator.slack.verification")


def verify_slack_request(
    signing_secret: str,
    raw_body: bytes,
    timestamp: str,
    signature: str,
) -> bool:
    """Return True when the Slack request signature is valid.

    Slack signs every incoming request with HMAC-SHA256 using the app's
    Signing Secret.  We recompute the signature and compare in constant
    time to guard against timing attacks.

    Rejects requests whose timestamp is more than 5 minutes old to
    prevent replay attacks.

    Args:
        signing_secret: Value of SLACK_SIGNING_SECRET from .env.
        raw_body:       Raw bytes of the HTTP request body (URL-encoded).
        timestamp:      Value of X-Slack-Request-Timestamp header.
        signature:      Value of X-Slack-Signature header (``v0=<hex>``).
    """
    if not signing_secret:
        _log.warning("SLACK_SIGNING_SECRET is not configured — skipping verification")
        return True  # dev-mode: allow through when secret not set

    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        _log.warning("Invalid Slack timestamp: %r", timestamp)
        return False

    if abs(time.time() - ts) > 300:  # 5-minute replay window
        _log.warning("Slack request timestamp too old: %s", timestamp)
        return False

    sig_basestring = f"v0:{timestamp}:{raw_body.decode('utf-8', errors='replace')}"
    computed = (
        "v0="
        + hmac.new(
            key=signing_secret.encode("utf-8"),
            msg=sig_basestring.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()
    )

    if not hmac.compare_digest(computed, signature):
        _log.warning("Slack signature mismatch — possible forged request")
        return False

    return True
