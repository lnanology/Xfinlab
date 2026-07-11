const API_BASE = "https://api.xfinlab.com";

// Best-effort analytics tracking for every postApi() call across the 8
// pages that share this file (screener/ai-analysis/news/stress-lab/chat/
// news-denoise/compare/company-compare). Was previously only wired up on
// dashboard.html and chart-analysis.html, so the admin dashboard's
// today_analyses/trending stats missed most real usage. Uses the global
// window.trackEvent from js/nav.js if present; never blocks or throws.
function _trackApiCall(path, payload) {
  try {
    if (typeof window.trackEvent !== 'function') return;
    const ticker = (payload && (payload.ticker || payload.symbol || payload.query)) || null;
    window.trackEvent('search', { endpoint: path, ticker });
  } catch (e) {}
}

async function postApi(path, payload) {
  _trackApiCall(path, payload);
  const response = await fetch(API_BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`API 錯誤: ${response.status} ${text}`);
  }
  const data = await response.json();
  return { status: 'ok', data: data.data || data };
}

async function getApi(path) {
  _trackApiCall(path, null);
  const response = await fetch(API_BASE + path);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`API 錯誤: ${response.status} ${text}`);
  }
  const data = await response.json();
  return { status: 'ok', data: data.data || data };
}
