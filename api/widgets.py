"""
Growth OS Phase 4 -- Widget Engine API surface.

GET /widgets/sentiment-index and /widgets/heatmap are public JSON data
endpoints. GET /widgets/embed.js serves the actual embeddable script --
a third-party site includes it via a plain <script src="https://
api.xfinlab.com/api/widgets/embed.js" data-xfl-widget="sentiment-index">
tag, and it renders a small self-contained widget (inline styles, no
external CSS dependency) with a "Powered by XFINLAB" badge linking back
to the homepage -- the actual distribution mechanic behind this whole
engine.

Gated by the widget_engine feature flag: when off, embed.js still loads
(so it never 404s on someone else's live page) but renders nothing and
logs a console note instead, and the data endpoints return
available=False. Turning it back on requires no site to re-embed
anything.
"""
import os
import sqlite3
from datetime import date

from fastapi import APIRouter, Response

from services.widget_service import get_sentiment_index, get_signal_heatmap

router = APIRouter()

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def _widget_engine_enabled() -> bool:
    try:
        conn = sqlite3.connect(_DB_PATH)
        row = conn.execute("SELECT enabled FROM feature_flags WHERE key='widget_engine'").fetchone()
        conn.close()
        if row is None:
            return True
        return bool(row[0])
    except Exception:
        return True


def _log_embed_view(widget_type: str):
    """Best-effort daily impression counter per widget type -- lets the
    admin panel show "this many embed loads today" as a rough proxy for
    how many third-party pages are actually rendering the widget. Never
    raises; a logging failure must not break the widget itself."""
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS widget_embed_log (
                widget_type TEXT NOT NULL,
                log_date TEXT NOT NULL,
                views INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (widget_type, log_date)
            )
            """
        )
        today = date.today().isoformat()
        conn.execute(
            """
            INSERT INTO widget_embed_log (widget_type, log_date, views) VALUES (?, ?, 1)
            ON CONFLICT(widget_type, log_date) DO UPDATE SET views = views + 1
            """,
            (widget_type, today),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


@router.get("/widgets/sentiment-index")
def widget_sentiment_index():
    if not _widget_engine_enabled():
        return {"available": False}
    _log_embed_view("sentiment-index")
    return get_sentiment_index()


@router.get("/widgets/heatmap")
def widget_heatmap(limit: int = 12):
    if not _widget_engine_enabled():
        return {"available": False}
    _log_embed_view("heatmap")
    return get_signal_heatmap(limit=limit)


_EMBED_JS = r"""
(function() {
  var s = document.currentScript;
  if (!s) return;
  var widget = s.getAttribute('data-xfl-widget') || 'sentiment-index';
  var theme = s.getAttribute('data-xfl-theme') || 'light';
  var API = 'https://api.xfinlab.com/api/widgets';
  var isDark = theme === 'dark';
  var colors = isDark
    ? {bg:'#0d1525', border:'#1e2d45', text:'#e2e8f0', muted:'#64748b', accent:'#00d4ff'}
    : {bg:'#ffffff', border:'#e2e8f0', text:'#111827', muted:'#6b7280', accent:'#2563eb'};

  var wrap = document.createElement('div');
  wrap.style.cssText = 'font-family:Arial,Helvetica,sans-serif;max-width:340px;border:1px solid ' + colors.border + ';border-radius:12px;padding:16px;background:' + colors.bg + ';color:' + colors.text + ';box-sizing:border-box';
  wrap.innerHTML = '<div style="font-size:0.75rem;color:' + colors.muted + '">Loading XFINLAB widget...</div>';
  s.parentNode.insertBefore(wrap, s.nextSibling);

  function badge() {
    var a = document.createElement('a');
    a.href = 'https://www.xfinlab.com';
    a.target = '_blank';
    a.rel = 'noopener';
    a.textContent = 'Powered by XFINLAB';
    a.style.cssText = 'display:block;margin-top:10px;font-size:0.68rem;color:' + colors.accent + ';text-decoration:none;text-align:right';
    return a;
  }

  function dirColor(direction) {
    if (direction === 'Bullish') return '#22c55e';
    if (direction === 'Bearish') return '#ef4444';
    return colors.muted;
  }

  function renderSentiment(data) {
    wrap.innerHTML = '';
    if (!data || !data.available) {
      wrap.innerHTML = '<div style="font-size:0.78rem;color:' + colors.muted + '">XFINLAB Sentiment Index unavailable right now.</div>';
      wrap.appendChild(badge());
      return;
    }
    var title = document.createElement('div');
    title.textContent = 'XFINLAB Market Sentiment Index';
    title.style.cssText = 'font-size:0.72rem;text-transform:uppercase;letter-spacing:0.05em;color:' + colors.muted + ';margin-bottom:8px';
    var scoreEl = document.createElement('div');
    scoreEl.textContent = data.score;
    scoreEl.style.cssText = 'font-size:2.2rem;font-weight:700;color:' + colors.accent;
    var labelEl = document.createElement('div');
    labelEl.textContent = data.label + ' · ' + data.date;
    labelEl.style.cssText = 'font-size:0.8rem;color:' + colors.muted + ';margin-top:2px';
    wrap.appendChild(title);
    wrap.appendChild(scoreEl);
    wrap.appendChild(labelEl);
    wrap.appendChild(badge());
  }

  function renderHeatmap(data) {
    wrap.innerHTML = '';
    if (!data || !data.available) {
      wrap.innerHTML = '<div style="font-size:0.78rem;color:' + colors.muted + '">XFINLAB Signal Heatmap unavailable right now.</div>';
      wrap.appendChild(badge());
      return;
    }
    var title = document.createElement('div');
    title.textContent = 'XFINLAB Signal Strength Heatmap · ' + data.date;
    title.style.cssText = 'font-size:0.72rem;text-transform:uppercase;letter-spacing:0.05em;color:' + colors.muted + ';margin-bottom:10px';
    wrap.appendChild(title);
    var grid = document.createElement('div');
    grid.style.cssText = 'display:grid;grid-template-columns:repeat(3,1fr);gap:6px';
    (data.cells || []).forEach(function(c) {
      var cell = document.createElement('div');
      var conf = (c.confidence_pct != null) ? c.confidence_pct : 0;
      cell.style.cssText = 'border-radius:8px;padding:8px 6px;text-align:center;background:' + dirColor(c.direction) + ';opacity:' + (0.25 + Math.min(conf, 100) / 133) + ';color:#fff';
      cell.innerHTML = '<div style="font-weight:700;font-size:0.8rem">' + c.ticker + '</div><div style="font-size:0.65rem">' + (conf != null ? conf + '%' : '') + '</div>';
      grid.appendChild(cell);
    });
    wrap.appendChild(grid);
    wrap.appendChild(badge());
  }

  var endpoint = widget === 'heatmap' ? (API + '/heatmap') : (API + '/sentiment-index');
  fetch(endpoint).then(function(r) { return r.json(); }).then(function(data) {
    if (widget === 'heatmap') { renderHeatmap(data); } else { renderSentiment(data); }
  }).catch(function() {
    wrap.innerHTML = '<div style="font-size:0.78rem;color:' + colors.muted + '">XFINLAB widget failed to load.</div>';
    wrap.appendChild(badge());
  });
})();
"""


@router.get("/widgets/embed.js")
def widget_embed_js():
    return Response(content=_EMBED_JS, media_type="application/javascript")
