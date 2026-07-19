"""
Direction Probability Service -- Stage 2 roadmap item 1 (2026-07-19):
"LSTM 短期方向機率模型" (short-term direction probability model).

The roadmap document calls this "LSTM", but a true LSTM needs torch/
tensorflow (~500MB+) added to a backend that today has zero ML
dependencies and runs as a single small Railway dyno (see Procfile --
plain `uvicorn backend.main:app`, no worker pool). Adding that weight
purely to match a label in a planning document, when a much lighter
model delivers the same honest outcome the roadmap actually wants (a
real, backtested N-day direction probability from real OHLCV history),
was flagged to the user as a real deploy-size/cold-start risk before
building this -- the user chose the lightweight path: scikit-learn
(GradientBoostingClassifier), no GPU, small pure-Python-plus-C
dependency, CPU-only training that finishes in seconds per symbol.

Honesty contract (same standard as the rest of this codebase):
  - "新引擎必須經過backtesting驗證，先可以正式展示比用戶" (new engines must
    pass backtesting before being shown to users) is enforced IN CODE,
    not just documentation: train_and_backtest() evaluates the model on
    a chronologically-later holdout slice it never trained on (a simple
    time-ordered split, not shuffled k-fold CV, specifically to avoid
    leaking future information into training) and only marks the model
    "validated" if it beats both a 50% coin-flip AND the naive majority-
    class baseline by a real margin on that real holdout. A model that
    fails this gate is still saved (for visibility/debugging) but
    predict() will not serve its output.
  - predict()/get_direction_probability() never trains on the fly during
    a live request -- if no validated, sufficiently fresh model exists
    for a symbol, they return {"available": False, "message": "..."}
    honestly instead of a slow/inconsistent just-in-time fit.
  - Models are retrained by running scripts/train_direction_models.py
    (a real training/retraining pipeline needing live market data --
    this sandbox has no network access to run it against real tickers,
    so it's validated here against synthetic data instead; see that
    script's own docstring).
"""

import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import joblib
import numpy as np
import pandas as pd
from scipy.stats import binomtest
from sklearn.ensemble import GradientBoostingClassifier

from services.technical_analysis_service import TechnicalAnalysisService, fetch_ohlc_history

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")
MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models")

DEFAULT_HORIZON_DAYS = 5
MIN_OBSERVATIONS = 500  # ~2 trading years -- see the overlapping-label note below on why this needs to be bigger than it might look
HOLDOUT_FRACTION = 0.25
# A label at row t depends on the close `horizon_days` ahead, so
# consecutive rows' labels overlap by (horizon_days - 1) days -- this
# means naively scoring every holdout row treats ~horizon_days
# autocorrelated observations as if they were independent, silently
# inflating the EFFECTIVE sample size and making a lucky/unlucky single
# split look far more (or less) significant than it really is. Verified
# empirically before shipping this: scoring every row on 10 seeds of
# PURE RANDOM WALK data spuriously "validated" models as often as not.
# Fix: only score every `horizon_days`-th holdout row, so each evaluated
# point's label window doesn't overlap the next one -- a genuinely
# independent test set, at the cost of needing more raw history to reach
# a usable count of them.
MIN_HOLDOUT_SAMPLES = 30  # independent (non-overlapping) evaluation points, not raw holdout rows
# The backtest gate is a one-sided binomial significance test (via
# scipy.stats.binomtest, already a scikit-learn dependency -- no new
# package needed): does this model beat the naive majority-class
# baseline on the independent holdout by more than chance, at p < 0.05?
# This replaced an earlier flat "accuracy >= 54%" threshold that was
# shown (via the random-walk check above) to pass on pure noise too
# often given how few independent points a single ticker's holdout
# actually contains -- a real number, not an arbitrary-looking one, is
# only claimed when the data can actually support that claim.
SIGNIFICANCE_ALPHA = 0.05
MODEL_MAX_AGE_DAYS = 30  # "定期重新訓練" -- a model older than this is treated as stale, not served

FEATURE_NAMES = [
    "return_1d", "return_5d", "return_10d",
    "rsi_14", "macd_hist", "volatility_20d",
    "volume_ratio", "dist_from_sma20_pct", "dist_from_sma50_pct",
]


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_table():
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS direction_model_registry (
            symbol TEXT NOT NULL,
            horizon_days INTEGER NOT NULL,
            model_path TEXT NOT NULL,
            trained_at TEXT NOT NULL,
            n_train_samples INTEGER NOT NULL,
            n_holdout_samples INTEGER NOT NULL,
            holdout_accuracy_pct REAL NOT NULL,
            baseline_accuracy_pct REAL NOT NULL,
            p_value REAL NOT NULL,
            validated INTEGER NOT NULL,
            PRIMARY KEY (symbol, horizon_days)
        )
    """)
    conn.commit()
    conn.close()


_init_table()
os.makedirs(MODELS_DIR, exist_ok=True)


def build_features(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """
    df: OHLCV DataFrame (Open/High/Low/Close/Volume, oldest-first) from
    services.technical_analysis_service.fetch_ohlc_history(). Returns a
    DataFrame of real technical features (same columns as FEATURE_NAMES,
    same row index as `df`), reusing TechnicalAnalysisService's existing
    indicator functions rather than reimplementing them -- or None if
    `df` is missing required columns.
    """
    required = {"Open", "High", "Low", "Close", "Volume"}
    if df is None or not required.issubset(df.columns):
        return None

    closes = df["Close"].astype(float)
    highs = df["High"].astype(float)
    lows = df["Low"].astype(float)
    volume = df["Volume"].astype(float)

    rsi_14 = TechnicalAnalysisService._rsi(closes, period=14)
    _macd_line, _signal_line, macd_hist = TechnicalAnalysisService._macd(closes)
    sma20 = TechnicalAnalysisService._sma(closes, window=20)
    sma50 = TechnicalAnalysisService._sma(closes, window=50)

    log_returns = np.log(closes / closes.shift(1))
    volatility_20d = log_returns.rolling(20).std() * np.sqrt(252) * 100

    volume_avg_20d = volume.rolling(20).mean()
    volume_ratio = volume / volume_avg_20d.replace(0, np.nan)

    features = pd.DataFrame({
        "return_1d": closes.pct_change(1) * 100,
        "return_5d": closes.pct_change(5) * 100,
        "return_10d": closes.pct_change(10) * 100,
        "rsi_14": rsi_14,
        "macd_hist": macd_hist,
        "volatility_20d": volatility_20d,
        "volume_ratio": volume_ratio,
        "dist_from_sma20_pct": (closes - sma20) / sma20.replace(0, np.nan) * 100,
        "dist_from_sma50_pct": (closes - sma50) / sma50.replace(0, np.nan) * 100,
    }, index=df.index)

    return features[FEATURE_NAMES]


def build_labels(closes: pd.Series, horizon_days: int) -> pd.Series:
    """
    Binary label: 1 if Close `horizon_days` trading days AHEAD of each row
    is higher than that row's Close, else 0. The last `horizon_days` rows
    can't have a real label yet (the future close doesn't exist in this
    data) and come back as NaN -- callers must drop those, never guess
    them, to avoid a lookahead bug.
    """
    future_close = closes.shift(-horizon_days)
    return (future_close > closes).astype(float).where(future_close.notna())


def _model_path(symbol: str, horizon_days: int) -> str:
    return os.path.join(MODELS_DIR, f"{symbol.upper()}_{horizon_days}d.joblib")


def train_and_backtest(symbol: str, horizon_days: int = DEFAULT_HORIZON_DAYS, period: str = "2y") -> Dict:
    """
    Fetches real OHLCV history, builds features/labels, fits a
    GradientBoostingClassifier on a chronologically-EARLIER slice, and
    evaluates it on a chronologically-LATER holdout slice it never saw
    (a real out-of-sample backtest, not shuffled k-fold CV, so no future
    information leaks into training). Persists the model + a full
    metadata row (including whether it passed the honesty gate) to the
    registry regardless of outcome, so a failed attempt is still visible
    for debugging -- but predict() only ever serves a `validated=True`
    model.

    Returns a dict describing the outcome (see module docstring for the
    honesty gate this applies).
    """
    symbol = (symbol or "").upper().strip()
    if not symbol:
        return {"available": False, "message": "代號唔可以係空"}

    try:
        df = fetch_ohlc_history(symbol, period=period, interval="1d")
    except Exception as e:
        return {"available": False, "message": f"攞唔到 {symbol} 嘅歷史數據：{e}"}

    if df is None or len(df) < MIN_OBSERVATIONS:
        return {"available": False, "message": f"{symbol} 嘅真實歷史數據唔夠（需要至少 {MIN_OBSERVATIONS} 個交易日）"}

    features = build_features(df)
    if features is None:
        return {"available": False, "message": f"{symbol} 嘅OHLCV數據欄位唔完整"}

    labels = build_labels(df["Close"].astype(float), horizon_days)

    combined = features.copy()
    combined["label"] = labels
    combined = combined.dropna()  # drops warm-up rows (rolling windows) AND the un-labelable tail

    if len(combined) < MIN_OBSERVATIONS // 2:
        return {"available": False, "message": f"{symbol} 清理缺失值後樣本唔夠（剩 {len(combined)} 個）"}

    split_idx = int(len(combined) * (1 - HOLDOUT_FRACTION))
    train_df = combined.iloc[:split_idx]
    holdout_df = combined.iloc[split_idx:]
    # Independent (non-overlapping) evaluation subsample -- see the
    # MIN_HOLDOUT_SAMPLES comment above for why this matters.
    holdout_eval_df = holdout_df.iloc[::horizon_days]

    if len(holdout_eval_df) < MIN_HOLDOUT_SAMPLES:
        return {
            "available": False,
            "message": f"{symbol} 獨立樣本外測試點唔夠（{len(holdout_eval_df)} < {MIN_HOLDOUT_SAMPLES}，需要更長歷史）",
        }

    X_train, y_train = train_df[FEATURE_NAMES], train_df["label"]
    X_holdout, y_holdout = holdout_eval_df[FEATURE_NAMES], holdout_eval_df["label"]

    model = GradientBoostingClassifier(
        n_estimators=100, max_depth=3, learning_rate=0.05, random_state=42,
    )
    model.fit(X_train, y_train)

    holdout_predictions = model.predict(X_holdout)
    n_holdout = len(y_holdout)
    n_correct = int((holdout_predictions == y_holdout.values).sum())
    holdout_accuracy = n_correct / n_holdout

    # Naive baseline: always guess the majority class seen in TRAINING
    # data (computed from train, not holdout, to keep this an honest
    # apples-to-apples out-of-sample comparison).
    majority_class = 1.0 if y_train.mean() >= 0.5 else 0.0
    baseline_accuracy = float((y_holdout.values == majority_class).mean())

    # One-sided binomial test: is n_correct out of n_holdout significantly
    # MORE than what the majority-class baseline rate would predict by
    # chance alone? See SIGNIFICANCE_ALPHA comment above.
    p_value = binomtest(n_correct, n_holdout, max(baseline_accuracy, 0.5), alternative="greater").pvalue
    validated = bool(p_value < SIGNIFICANCE_ALPHA and holdout_accuracy > baseline_accuracy)

    model_path = _model_path(symbol, horizon_days)
    joblib.dump(model, model_path)

    conn = _get_db()
    try:
        conn.execute(
            """INSERT INTO direction_model_registry
               (symbol, horizon_days, model_path, trained_at, n_train_samples,
                n_holdout_samples, holdout_accuracy_pct, baseline_accuracy_pct, p_value, validated)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(symbol, horizon_days) DO UPDATE SET
                 model_path=excluded.model_path, trained_at=excluded.trained_at,
                 n_train_samples=excluded.n_train_samples, n_holdout_samples=excluded.n_holdout_samples,
                 holdout_accuracy_pct=excluded.holdout_accuracy_pct,
                 baseline_accuracy_pct=excluded.baseline_accuracy_pct, p_value=excluded.p_value,
                 validated=excluded.validated""",
            (
                symbol, horizon_days, model_path, datetime.now(timezone.utc).isoformat(),
                len(train_df), n_holdout, round(holdout_accuracy * 100, 2),
                round(baseline_accuracy * 100, 2), round(p_value, 4), int(validated),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "available": True,
        "symbol": symbol,
        "horizon_days": horizon_days,
        "n_train_samples": len(train_df),
        "n_holdout_samples": n_holdout,
        "holdout_accuracy_pct": round(holdout_accuracy * 100, 2),
        "baseline_accuracy_pct": round(baseline_accuracy * 100, 2),
        "p_value": round(p_value, 4),
        "validated": validated,
        "message": (
            f"驗證通過：獨立樣本外準確率 {holdout_accuracy*100:.1f}%（基準 {baseline_accuracy*100:.1f}%，"
            f"p={p_value:.3f} < {SIGNIFICANCE_ALPHA}）"
            if validated else
            f"未通過驗證：獨立樣本外準確率 {holdout_accuracy*100:.1f}%（基準 {baseline_accuracy*100:.1f}%，"
            f"p={p_value:.3f}），未達統計顯著水平，唔會提供俾用戶"
        ),
    }


def predict(symbol: str, horizon_days: int = DEFAULT_HORIZON_DAYS) -> Dict:
    """
    Returns:
        {"available": True, "up_probability_pct": float, "horizon_days": int,
         "holdout_accuracy_pct": float, "trained_at": iso_str, "method": "...",
         "note": "..."}
        {"available": False, "message": "..."} -- no model trained yet, the
            trained model failed its backtest gate, or it's gone stale
            (see MODEL_MAX_AGE_DAYS) -- callers must NOT fabricate a
            probability in any of these cases.
    """
    symbol = (symbol or "").upper().strip()
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT * FROM direction_model_registry WHERE symbol = ? AND horizon_days = ?",
            (symbol, horizon_days),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return {"available": False, "message": f"{symbol} 仲未訓練過方向機率模型"}
    if not row["validated"]:
        return {"available": False, "message": f"{symbol} 嘅模型未通過backtest驗證（樣本外準確率 {row['holdout_accuracy_pct']}%），暫時唔提供"}

    trained_at = datetime.fromisoformat(row["trained_at"])
    age_days = (datetime.now(timezone.utc) - trained_at).days
    if age_days > MODEL_MAX_AGE_DAYS:
        return {"available": False, "message": f"{symbol} 嘅模型已經 {age_days} 日冇重新訓練，已經過期，需要重新執行 scripts/train_direction_models.py"}

    if not os.path.exists(row["model_path"]):
        return {"available": False, "message": f"{symbol} 嘅模型檔案遺失，需要重新訓練"}

    try:
        df = fetch_ohlc_history(symbol, period="6mo", interval="1d")
        features = build_features(df)
        latest = features.dropna().iloc[[-1]]
    except Exception as e:
        return {"available": False, "message": f"攞唔到 {symbol} 最新數據嚟計算特徵：{e}"}

    if latest.empty:
        return {"available": False, "message": f"{symbol} 最新特徵計算唔到（數據唔夠）"}

    try:
        model = joblib.load(row["model_path"])
        up_probability = float(model.predict_proba(latest[FEATURE_NAMES])[0][1])
    except Exception as e:
        return {"available": False, "message": f"模型載入／推論失敗：{e}"}

    return {
        "available": True,
        "up_probability_pct": round(up_probability * 100, 1),
        "horizon_days": horizon_days,
        "holdout_accuracy_pct": row["holdout_accuracy_pct"],
        "trained_at": row["trained_at"],
        "method": "gradient_boosting_classifier (scikit-learn)",
        "note": (
            f"基於過去{horizon_days}個交易日真實OHLCV數據特徵訓練，"
            f"樣本外backtest準確率{row['holdout_accuracy_pct']}%（基準{row['baseline_accuracy_pct']}%）。"
            "並非精確預測，僅反映歷史統計傾向，不構成投資建議。"
        ),
    }


def get_direction_probability(symbol: str, horizon_days: int = DEFAULT_HORIZON_DAYS) -> Dict:
    """Public entry point -- thin, stable name for other modules to call
    without needing to know about the registry/model-file details."""
    return predict(symbol, horizon_days=horizon_days)
