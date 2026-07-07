import os
import sqlite3
from datetime import datetime, timedelta
from services.email_service import EmailService

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend", "xfinlab.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_email_sequence_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS email_sequences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            sequence_type TEXT NOT NULL,
            sent_at TEXT DEFAULT (datetime('now')),
            UNIQUE(user_id, sequence_type)
        )
    """)
    conn.commit()
    conn.close()

init_email_sequence_table()


class EmailSequences:

    @staticmethod
    def send_day1(user_id: int, email: str, name: str):
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:500px;margin:0 auto;background:#080c14;color:#e2e8f0;padding:40px;border-radius:12px;">
            <h1 style="color:#00d4ff;">你知道 XFINLAB 可以做到呢啲嗎？</h1>
            <p>你好 {name}，</p>
            <p>你昨日註冊了 XFINLAB，想確保你知道所有功能：</p>
            <div style="background:#0d1525;border-radius:8px;padding:16px;margin:16px 0">
                <p>📊 <strong>AI 全面分析</strong> — 輸入任何股票代號即時分析</p>
                <p>🔍 <strong>智能篩選器</strong> — AI 幫你找出潛力股</p>
                <p>📰 <strong>新聞情緒分析</strong> — 即時市場情緒評估</p>
                <p>📈 <strong>AI 研究報告</strong> — 完整投資研究（每日3次免費）</p>
            </div>
            <a href="https://finlab-ai.vercel.app/ai-analysis.html" style="background:#00d4ff;color:#000;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:bold;display:inline-block;margin:16px 0;">立即試用 →</a>
            <p style="color:#64748b;font-size:0.85rem;">XFINLAB Team</p>
        </div>
        """
        result = EmailService.send(email, "你還未試過 XFINLAB 最強功能 📊", html)
        if result:
            conn = get_db()
            try:
                conn.execute("INSERT INTO email_sequences (user_id, sequence_type) VALUES (?, ?)", (user_id, "day1"))
                conn.commit()
            except:
                pass
            conn.close()
        return result

    @staticmethod
    def send_day3(user_id: int, email: str, name: str):
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:500px;margin:0 auto;background:#080c14;color:#e2e8f0;padding:40px;border-radius:12px;">
            <h1 style="color:#00d4ff;">AI 研究報告 — 像基金經理一樣分析股票</h1>
            <p>你好 {name}，</p>
            <p>XFINLAB 的 AI 研究報告功能可以幫你生成：</p>
            <div style="background:#0d1525;border-radius:8px;padding:16px;margin:16px 0">
                <p>✅ 公司概況與競爭優勢</p>
                <p>✅ 財務分析（營收、利潤、估值）</p>
                <p>✅ 風險評估</p>
                <p>✅ AI 投資建議與目標價</p>
                <p>✅ 可下載 PDF 報告</p>
            </div>
            <p>免費用戶每日 3 次，Pro 用戶無限次。</p>
            <a href="https://finlab-ai.vercel.app/dashboard.html" style="background:#00d4ff;color:#000;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:bold;display:inline-block;margin:16px 0;">生成我的研究報告 →</a>
            <p style="color:#64748b;font-size:0.85rem;">XFINLAB Team</p>
        </div>
        """
        result = EmailService.send(email, "免費生成 AI 股票研究報告 📑", html)
        if result:
            conn = get_db()
            try:
                conn.execute("INSERT INTO email_sequences (user_id, sequence_type) VALUES (?, ?)", (user_id, "day3"))
                conn.commit()
            except:
                pass
            conn.close()
        return result

    @staticmethod
    def send_day7(user_id: int, email: str, name: str):
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:500px;margin:0 auto;background:#080c14;color:#e2e8f0;padding:40px;border-radius:12px;">
            <h1 style="color:#00d4ff;">升級 Pro，解鎖無限分析 🚀</h1>
            <p>你好 {name}，</p>
            <p>你已經使用 XFINLAB 一週了！升級 Pro 享受：</p>
            <div style="background:#0d1525;border-radius:8px;padding:16px;margin:16px 0">
                <p>✅ <strong>無限</strong> AI 股票分析</p>
                <p>✅ <strong>無限</strong> AI 研究報告</p>
                <p>✅ <strong>無限</strong> PDF 報告下載</p>
                <p>✅ 組合追蹤（10隻股票）</p>
                <p>✅ 異常波動即時提醒</p>
            </div>
            <div style="text-align:center;margin:24px 0">
                <div style="font-size:2rem;font-weight:bold;color:#00d4ff">$19/月</div>
                <div style="color:#64748b;font-size:0.85rem">或 $15/月（年付節省20%）</div>
            </div>
            <a href="https://finlab-ai.vercel.app/pricing.html" style="background:#00d4ff;color:#000;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:bold;display:inline-block;margin:16px 0;width:100%;text-align:center;">立即升級 Pro →</a>
            <p style="color:#64748b;font-size:0.85rem;">14天退款保證 · 隨時取消</p>
        </div>
        """
        result = EmailService.send(email, "🚀 升級 Pro — 無限 AI 投資分析", html)
        if result:
            conn = get_db()
            try:
                conn.execute("INSERT INTO email_sequences (user_id, sequence_type) VALUES (?, ?)", (user_id, "day7"))
                conn.commit()
            except:
                pass
            conn.close()
        return result

    @staticmethod
    def run_scheduler():
        """每日跑一次，發送應該發的 email"""
        conn = get_db()
        users = conn.execute("SELECT * FROM users WHERE plan='free'").fetchall()
        conn.close()

        sent = 0
        for user in users:
            user_id = user["id"]
            email = user["email"]
            name = user["name"]
            created = datetime.fromisoformat(user["created_at"].replace(" ", "T"))
            days = (datetime.now() - created).days

            conn = get_db()
            sent_sequences = [r["sequence_type"] for r in conn.execute(
                "SELECT sequence_type FROM email_sequences WHERE user_id=?", (user_id,)
            ).fetchall()]
            conn.close()

            if days >= 1 and "day1" not in sent_sequences:
                if EmailSequences.send_day1(user_id, email, name):
                    sent += 1
                    print(f"Sent day1 to {email}")

            elif days >= 3 and "day3" not in sent_sequences:
                if EmailSequences.send_day3(user_id, email, name):
                    sent += 1
                    print(f"Sent day3 to {email}")

            elif days >= 7 and "day7" not in sent_sequences:
                if EmailSequences.send_day7(user_id, email, name):
                    sent += 1
                    print(f"Sent day7 to {email}")

        print(f"Email sequence run complete. {sent} emails sent.")
        return sent


if __name__ == "__main__":
    EmailSequences.run_scheduler()
