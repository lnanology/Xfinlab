import os
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_APP_PASSWORD")
# 2026-08-01: was hardcoded to smtp.gmail.com -- now configurable so this
# can send via a real support@xfinlab.com mailbox (e.g. Namecheap Private
# Email: mail.privateemail.com:587) instead of only a personal Gmail
# account. Defaults preserve the exact previous behavior if these two
# env vars are left unset, so this is a no-op change until you set them.
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))

# 2026-08-27 (AJ hit "Key was issued but the confirmation email failed to
# send" on Intelligence API self-serve signup -- diagnosed via the new
# /admin/email-debug endpoint: `connect` step to mail.privateemail.com:587
# timed out. Not a credentials/config bug -- Railway blocks outbound SMTP
# (ports 25/465/587) on all plans below Pro, confirmed via Railway's own
# help station. The SMTP path above is unusable on this deployment
# regardless of what EMAIL_ADDRESS/EMAIL_APP_PASSWORD/SMTP_HOST are set to.
#
# Resend's HTTP API sends over plain HTTPS (port 443, never blocked) so it
# sidesteps the platform restriction entirely -- same "dormant until
# configured" pattern as EIA_API_KEY/FRED_API_KEY elsewhere in this
# codebase: if RESEND_API_KEY is unset, send() below falls through to the
# exact same SMTP path as before (a no-op change for any deployment where
# SMTP already works, e.g. a future Railway Pro upgrade, or running this
# outside Railway entirely).
#
# RESEND_FROM_EMAIL must be an address on a domain verified in the Resend
# dashboard (DNS records) to send to arbitrary recipients -- Resend's
# unverified default (onboarding@resend.dev) only delivers to the
# account's own signup email, fine for a first connectivity test but not
# for real users. Falls back to EMAIL_ADDRESS (the existing Namecheap
# mailbox) as a working default so this doesn't require a fresh decision
# just to unblock this fix.
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL") or EMAIL_ADDRESS or "onboarding@resend.dev"


class EmailService:
    """XFINLAB Email Service - Sends notification emails"""

    @staticmethod
    def send(to_email: str, subject: str, html_body: str) -> bool:
        """
        Send an email. Uses Resend's HTTP API when RESEND_API_KEY is set
        (see module docstring above for why -- Railway blocks outbound
        SMTP below its Pro plan); otherwise falls back to the original
        direct-SMTP path unchanged.

        Args:
            to_email: Recipient email
            subject: Email subject
            html_body: HTML email content

        Returns:
            bool: True if sent successfully
        """
        if RESEND_API_KEY:
            try:
                from_field = RESEND_FROM_EMAIL if "<" in RESEND_FROM_EMAIL else f"XFINLAB <{RESEND_FROM_EMAIL}>"
                resp = requests.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {RESEND_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "from": from_field,
                        "to": [to_email],
                        "subject": subject,
                        "html": html_body,
                    },
                    timeout=15,
                )
                if resp.status_code in (200, 201):
                    return True
                print(f"Resend error: {resp.status_code} {resp.text}")
                return False
            except Exception as e:
                print(f"Resend error: {e}")
                return False

        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"XFINLAB <{EMAIL_ADDRESS}>"
            msg['To'] = to_email

            html_part = MIMEText(html_body, 'html')
            msg.attach(html_part)

            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                server.send_message(msg)

            return True
        except Exception as e:
            print(f"Email error: {e}")
            return False

    @staticmethod
    def send_welcome(to_email: str, name: str) -> bool:
        """Send welcome email to new user"""
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:500px;margin:0 auto;background:#080c14;color:#e2e8f0;padding:40px;border-radius:12px;">
            <h1 style="color:#00d4ff;">歡迎來到 XFINLAB！</h1>
            <p>你好 {name}，</p>
            <p>感謝你註冊 XFINLAB AI 投資決策平台！</p>
            <p>立即開始你的第一次 AI 股票分析：</p>
            <a href="https://xfinlab.com/ai-analysis.html" style="background:#00d4ff;color:#000;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:bold;display:inline-block;margin:16px 0;">開始分析</a>
            <p style="color:#64748b;font-size:0.85rem;">XFINLAB Team</p>
        </div>
        """
        return EmailService.send(to_email, "歡迎來到 XFINLAB 🚀", html)

    @staticmethod
    def send_quota_warning(to_email: str, name: str, feature: str, remaining: int) -> bool:
        """Send quota warning email"""
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:500px;margin:0 auto;background:#080c14;color:#e2e8f0;padding:40px;border-radius:12px;">
            <h1 style="color:#f59e0b;">額度即將用完 ⚠️</h1>
            <p>你好 {name}，</p>
            <p>你今日的 {feature} 額度只剩 {remaining} 次。</p>
            <p>升級 Pro 享受無限次數使用：</p>
            <a href="https://xfinlab.com/pricing.html" style="background:#00d4ff;color:#000;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:bold;display:inline-block;margin:16px 0;">立即升級</a>
        </div>
        """
        return EmailService.send(to_email, "額度即將用完 - XFINLAB", html)

    @staticmethod
    def send_intelligence_api_quota_exceeded(to_email: str, tier: str, limit: int) -> bool:
        """2026-08-18: fires once per key per day, at the exact moment a
        free-tier Intelligence API key hits its daily call limit (see
        api/intelligence.py's _check_and_spend_quota + services/
        intelligence_quota_service.py's should_send_upgrade_nudge dedup).
        English, not Chinese -- this is the developer API's own audience
        (intelligence-api.html is English-first), unlike the consumer-app
        send_quota_warning() above. Honest framing: no urgency-manufacturing
        countdown, no fake scarcity -- the free tier really does reset
        tomorrow, and this just tells them that plus what Pro actually
        costs."""
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;background:#080c14;color:#e2e8f0;padding:40px;border-radius:12px;">
            <h1 style="color:#00d4ff;font-size:1.3rem;">You've hit today's free-tier limit</h1>
            <p>Your XFINLAB Intelligence API key ({tier} tier) has used its {limit} weighted calls for today.</p>
            <p>Two options:</p>
            <ul style="padding-left:20px;">
                <li>Nothing to do -- your free quota resets automatically at midnight UTC.</li>
                <li>Or upgrade to Pro: 5,000 calls/day for $49/month.</li>
            </ul>
            <a href="https://www.xfinlab.com/intelligence-api.html#access" style="background:#00d4ff;color:#000;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:bold;display:inline-block;margin:16px 0;">Request Pro access</a>
            <p style="color:#64748b;font-size:0.82rem;">You're getting this because your API key just returned a 429. This is a one-time note for today -- you won't get another one until you hit the limit again on a different day.</p>
        </div>
        """
        return EmailService.send(to_email, "XFINLAB Intelligence API -- daily free-tier limit reached", html)

    @staticmethod
    def send_intelligence_api_endpoint_cap_reached(to_email: str, endpoint: str, cap: int) -> bool:
        """2026-08-25 (AJ: "FREEKEY 點樣延續人付費" -- how does the free key
        lead into a paid conversion): distinct from send_intelligence_api_
        quota_exceeded above on purpose. That one fires when the whole
        300-call/day pool is exhausted -- a rare event now that the pool is
        generous. This one fires when the free tier's separate, much lower
        daily cap on ONE specific high-value endpoint (debate or intel --
        see FREE_TIER_ENDPOINT_DAILY_CAP in intelligence_quota_service.py)
        is hit, which will happen far sooner for anyone actually using the
        feature that best demonstrates the product. That's the real
        highest-intent moment: they've proven they want exactly the thing
        Pro removes the cap on, not just "ran out of calls" in the
        abstract. Same honest, no-fake-urgency framing as the pool email."""
        endpoint_label = {"debate": "AI Debate", "intel": "AI Intelligence Feed"}.get(endpoint, endpoint)
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;background:#080c14;color:#e2e8f0;padding:40px;border-radius:12px;">
            <h1 style="color:#00d4ff;font-size:1.3rem;">You've hit today's {endpoint_label} cap</h1>
            <p>Your XFINLAB Intelligence API key (free tier) has used its {cap} {endpoint_label} calls for today. Your other endpoints (technical, forecast, events, sentiment, etc.) are unaffected -- this cap is specific to {endpoint_label}.</p>
            <p>Two options:</p>
            <ul style="padding-left:20px;">
                <li>Nothing to do -- this cap resets automatically at midnight UTC.</li>
                <li>Or upgrade to Pro: 5,000 calls/day, no per-endpoint cap, for $49/month.</li>
            </ul>
            <a href="https://www.xfinlab.com/intelligence-api.html#access" style="background:#00d4ff;color:#000;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:bold;display:inline-block;margin:16px 0;">Request Pro access</a>
            <p style="color:#64748b;font-size:0.82rem;">You're getting this because your API key just returned a 429 on {endpoint_label} specifically. This is a one-time note for today -- you won't get another one until you hit this same cap again on a different day.</p>
        </div>
        """
        return EmailService.send(to_email, f"XFINLAB Intelligence API -- daily {endpoint_label} cap reached", html)

    @staticmethod
    def send_price_alert(to_email: str, name: str, ticker: str, price: float, change: str) -> bool:
        """Send price alert email"""
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:500px;margin:0 auto;background:#080c14;color:#e2e8f0;padding:40px;border-radius:12px;">
            <h1 style="color:#00d4ff;">市場異動提醒 🔔</h1>
            <p>你好 {name}，</p>
            <p><strong>{ticker}</strong> 出現重要變動：</p>
            <div style="background:#0d1525;border:1px solid #1e2d45;border-radius:8px;padding:20px;margin:16px 0;">
                <div style="font-size:2rem;font-weight:bold;color:#00d4ff;">${price}</div>
                <div style="color:#64748b;">{change}</div>
            </div>
            <a href="https://xfinlab.com/ai-analysis.html?symbols={ticker}" style="background:#00d4ff;color:#000;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:bold;display:inline-block;">查看完整分析</a>
        </div>
        """
        return EmailService.send(to_email, f"{ticker} 市場異動提醒 - XFINLAB", html)
