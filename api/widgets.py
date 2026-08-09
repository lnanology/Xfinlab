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
from services.widget_branding_service import get_branding_for_embed

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


@router.get("/widgets/branding")
def widget_branding(key: str = None):
    """2026-08-09 (white-label Tier A): public lookup embed.js calls when
    a data-xfl-key attribute is present on the script tag. Always 200s
    with {"available": False} for a missing/free/invalid key -- never an
    error, since a failed branding lookup must degrade to today's
    default XFINLAB-branded rendering, not a broken widget. See
    services/widget_branding_service.py for the Pro/Enterprise tiering
    and re-verification-at-read-time contract."""
    return get_branding_for_embed(key)


_EMBED_JS = r"""
(function() {
  var s = document.currentScript;
  if (!s) return;
  var widget = s.getAttribute('data-xfl-widget') || 'sentiment-index';
  var theme = s.getAttribute('data-xfl-theme') || 'light';
  var brandKey = s.getAttribute('data-xfl-key') || null;
  var API = 'https://api.xfinlab.com/api/widgets';
  var isDark = theme === 'dark';
  var colors = isDark
    ? {bg:'#0d1525', border:'#1e2d45', text:'#e2e8f0', muted:'#64748b', accent:'#00d4ff'}
    : {bg:'#ffffff', border:'#e2e8f0', text:'#111827', muted:'#6b7280', accent:'#2563eb'};
  // 2026-08-09 (white-label Tier A): overwritten in place if a valid
  // Pro/Enterprise data-xfl-key resolves real branding below -- stays
  // exactly the default XFINLAB palette/badge for every embed that
  // omits data-xfl-key (i.e. every existing embed today, zero
  // regression) or whose key isn't Pro/Enterprise.
  var brand = {available: false};

  var wrap = document.createElement('div');
  wrap.style.cssText = 'font-family:Arial,Helvetica,sans-serif;max-width:340px;border:1px solid ' + colors.border + ';border-radius:12px;padding:16px;background:' + colors.bg + ';color:' + colors.text + ';box-sizing:border-box';
  wrap.innerHTML = '<div style="font-size:0.75rem;color:' + colors.muted + '">Loading widget...</div>';
  s.parentNode.insertBefore(wrap, s.nextSibling);

  function badge() {
    // badge_mode: 'hidden' (Enterprise only) -> no badge at all;
    // 'cobrand' (Pro+) -> "Powered by XFINLAB × {brand_name}"; anything
    // else (no key, free tier, or lookup failed) -> today's plain
    // "Powered by XFINLAB", unchanged.
    if (brand.available && brand.badge_mode === 'hidden') return null;
    var a = document.createElement('a');
    a.href = 'https://www.xfinlab.com';
    a.target = '_blank';
    a.rel = 'noopener';
    a.textContent = (brand.available && brand.badge_mode === 'cobrand' && brand.brand_name)
      ? ('Powered by XFINLAB × ' + brand.brand_name)
      : 'Powered by XFINLAB';
    a.style.cssText = 'display:block;margin-top:10px;font-size:0.68rem;color:' + colors.accent + ';text-decoration:none;text-align:right';
    return a;
  }

  function appendBadge(el) {
    var b = badge();
    if (b) el.appendChild(b);
  }

  function logoEl() {
    if (!brand.available || !brand.logo_url) return null;
    var img = document.createElement('img');
    img.src = brand.logo_url;
    img.alt = brand.brand_name || 'logo';
    img.style.cssText = 'max-height:20px;max-width:120px;display:block;margin-bottom:6px';
    return img;
  }

  function dirColor(direction) {
    if (direction === 'Bullish') return '#22c55e';
    if (direction === 'Bearish') return '#ef4444';
    return colors.muted;
  }

  function titleText(defaultText) {
    return (brand.available && brand.brand_name) ? (brand.brand_name + ' · ' + defaultText) : defaultText;
  }

  function renderSentiment(data) {
    wrap.innerHTML = '';
    var logo = logoEl();
    if (logo) wrap.appendChild(logo);
    if (!data || !data.available) {
      var errEl = document.createElement('div');
      errEl.style.cssText = 'font-size:0.78rem;color:' + colors.muted;
      errEl.textContent = 'Market Sentiment Index unavailable right now.';
      wrap.appendChild(errEl);
      appendBadge(wrap);
      return;
    }
    var title = document.createElement('div');
    title.textContent = titleText('Market Sentiment Index');
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
    appendBadge(wrap);
  }

  function renderHeatmap(data) {
    wrap.innerHTML = '';
    var logo = logoEl();
    if (logo) wrap.appendChild(logo);
    if (!data || !data.available) {
      var errEl = document.createElement('div');
      errEl.style.cssText = 'font-size:0.78rem;color:' + colors.muted;
      errEl.textContent = 'Signal Heatmap unavailable right now.';
      wrap.appendChild(errEl);
      appendBadge(wrap);
      return;
    }
    var title = document.createElement('div');
    title.textContent = titleText('Signal Strength Heatmap') + ' · ' + data.date;
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
    appendBadge(wrap);
  }

  function renderError() {
    wrap.innerHTML = '<div style="font-size:0.78rem;color:' + colors.muted + '">Widget failed to load.</div>';
    appendBadge(wrap);
  }

  var endpoint = widget === 'heatmap' ? (API + '/heatmap') : (API + '/sentiment-index');
  var brandingFetch = brandKey
    ? fetch(API + '/branding?key=' + encodeURIComponent(brandKey)).then(function(r) { return r.json(); }).catch(function() { return {available: false}; })
    : Promise.resolve({available: false});

  Promise.all([fetch(endpoint).then(function(r) { return r.json(); }), brandingFetch]).then(function(results) {
    var data = results[0];
    brand = results[1] || {available: false};
    if (brand.available && brand.accent_color) colors.accent = brand.accent_color;
    if (widget === 'heatmap') { renderHeatmap(data); } else { renderSentiment(data); }
  }).catch(renderError);
})();
"""


@router.get("/widgets/embed.js")
def widget_embed_js():
    return Response(content=_EMBED_JS, media_type="application/javascript")
