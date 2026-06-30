import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_APP_PASSWORD")


class EmailService:
    """XFINLAB Email Service - Sends notification emails"""

    @staticmethod
    def send(to_email: str, subject: str, html_body: str) -> bool:
        """
        Send an email

        Args:
            to_email: Recipient email
            subject: Email subject
            html_body: HTML email content

        Returns:
            bool: True if sent successfully
        """
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"XFINLAB <{EMAIL_ADDRESS}>"
            msg['To'] = to_email

            html_part = MIMEText(html_body, 'html')
            msg.attach(html_part)

            with smtplib.SMTP('smtp.gmail.com', 587) as server:
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
            <a href="https://finlab-ai.vercel.app/ai-analysis.html" style="background:#00d4ff;color:#000;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:bold;display:inline-block;margin:16px 0;">開始分析</a>
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
            <a href="https://finlab-ai.vercel.app/pricing.html" style="background:#00d4ff;color:#000;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:bold;display:inline-block;margin:16px 0;">立即升級</a>
        </div>
        """
        return EmailService.send(to_email, "額度即將用完 - XFINLAB", html)

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
            <a href="https://finlab-ai.vercel.app/ai-analysis.html?ticker={ticker}" style="background:#00d4ff;color:#000;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:bold;display:inline-block;">查看完整分析</a>
        </div>
        """
        return EmailService.send(to_email, f"{ticker} 市場異動提醒 - XFINLAB", html)
