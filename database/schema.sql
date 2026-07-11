-- XFINLAB Database Schema (SQLite) — 2026-07-11 重寫
--
-- 呢份文件之前用緊Postgres語法（SERIAL/JSONB）,同實際production用嘅SQLite
-- 完全唔一致,仲有損壞嘅重複內容（duplicate table definitions + 一段散落嘅
-- dict-literal文字）,純粹係過時、行唔到嘅文件,冇任何code會讀呢個檔。
--
-- 依家改為如實反映實際情況：每個table都係由對應嘅service/router檔案用
-- `CREATE TABLE IF NOT EXISTS`喺app啟動時自己建立（唔係靠呢份.sql跑一次過
-- 建晒全部table）,所以呢份文件純粹係「文件」用途,方便一眼睇晒成個DB結構,
-- 唔係真正嘅migration來源。如果想改table結構,要去返對應嘅.py檔案改。
--
-- DB實際位置：repo根目錄 xfinlab.db（由litestream.yml備份去Cloudflare R2）。


-- ============================================================
-- Auth（backend/auth/auth.py, backend/auth/password_reset.py,
--       backend/auth/email_verification.py）
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,           -- bcrypt hash
    name TEXT NOT NULL,
    plan TEXT DEFAULT 'free',         -- 'free' | 'pro'
    email_verified INTEGER DEFAULT 0, -- 由 email_verifications 流程加返嚟嘅欄位
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS password_resets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    token TEXT UNIQUE NOT NULL,
    expires_at TEXT NOT NULL,
    used INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS email_verifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token TEXT UNIQUE NOT NULL,
    verified INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);


-- ============================================================
-- Security & Operations（services/audit_log_service.py,
--                        services/db_migration.py）
-- ============================================================

-- user_id 刻意 nullable：2026-07-11 之前係NOT NULL,淨係記錄到成功嘅登入/
-- 註冊/admin操作。而家連失敗嘅登入嘗試（action='login_failed:<email>',
-- user_id=NULL）都記錄到,方便偵測brute-force/credential-stuffing。
-- 呢個schema變更由services/db_migration.py嘅
-- migrate_audit_logs_nullable_user_id() 喺每次app啟動時自我修復（idempotent,
-- 對已經係nullable嘅DB會直接no-op）。
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,                  -- NULL = 未認證嘅嘗試（例如login_failed）
    action TEXT NOT NULL,
    ip_address TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);


-- ============================================================
-- Quota / Referral / Onboarding（增長相關）
-- ============================================================

-- services/quota_service.py：每日/每個功能嘅使用次數限制
CREATE TABLE IF NOT EXISTS quota_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    feature TEXT NOT NULL,
    date TEXT NOT NULL,
    count INTEGER DEFAULT 0,
    UNIQUE(user_id, feature, date)
);

-- services/email_sequences.py：追蹤每個用戶收咗邊啲自動化郵件
CREATE TABLE IF NOT EXISTS email_sequences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    sequence_type TEXT NOT NULL,
    sent_at TEXT DEFAULT (datetime('now')),
    UNIQUE(user_id, sequence_type)
);

-- services/referral_service.py
CREATE TABLE IF NOT EXISTS referrals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    referral_code TEXT UNIQUE NOT NULL,
    referred_count INTEGER DEFAULT 0,
    reward_days INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS referral_uses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referral_code TEXT NOT NULL,
    new_user_id INTEGER NOT NULL,
    used_at TEXT DEFAULT (datetime('now'))
);

-- api/onboarding.py：新用戶引導流程進度
CREATE TABLE IF NOT EXISTS onboarding (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE NOT NULL,
    step INTEGER DEFAULT 0,
    completed INTEGER DEFAULT 0,
    bonus_given INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);


-- ============================================================
-- 產品功能
-- ============================================================

-- services/watchlist_service.py
CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    ticker TEXT NOT NULL,
    added_at TEXT DEFAULT (datetime('now')),
    UNIQUE(user_id, ticker)
);

-- database/event_database.py：事件歷史（財報/CEO change/監管消息等），
-- 用嚟訓練/校準 engines/anomaly_engine.py 嘅事件影響評分
CREATE TABLE IF NOT EXISTS event_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_date TEXT NOT NULL,
    price_before REAL NOT NULL,
    price_after_1d REAL,
    price_after_7d REAL,
    price_after_30d REAL,
    created_at TEXT DEFAULT (datetime('now'))
);

-- api/feedback.py
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    message TEXT NOT NULL,
    email TEXT,
    user_id INTEGER,
    status TEXT DEFAULT 'new',        -- 'new' | 'reviewed' | 'resolved'
    created_at TEXT DEFAULT (datetime('now'))
);


-- ============================================================
-- Analytics（services/user_analytics.py, api/analytics.py）
-- ============================================================

-- admin.html嘅Dashboard/Trending全部靠呢個table：DAU/MAU用DISTINCT
-- user_id計,今日分析次數/熱門搜尋用WHERE event_type='search'計。
-- 前端由js/nav.js（全站）+ js/mvp-api.js（8個分析頁）+ dashboard.html/
-- chart-analysis.html自己嘅trackEvent()一齊寫入。
CREATE TABLE IF NOT EXISTS user_analytics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,                  -- NULL = 未登入嘅訪客
    session_id TEXT,
    event_type TEXT NOT NULL,         -- 'page_view' | 'search' | ...
    event_data TEXT,                  -- JSON string，例如 {"ticker":"AAPL"}
    page TEXT,
    ip TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
