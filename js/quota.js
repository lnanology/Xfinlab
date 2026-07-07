
// Quota exceeded handler
async function handleApiCall(fetchFn) {
  try {
    return await fetchFn();
  } catch(e) {
    if (e.status === 429 || (e.message && e.message.includes('quota'))) {
      showQuotaModal();
      throw e;
    }
    throw e;
  }
}

function showQuotaModal() {
  const existing = document.getElementById('quotaModal');
  if (existing) existing.remove();

  const modal = document.createElement('div');
  modal.id = 'quotaModal';
  modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.8);z-index:9999;display:flex;align-items:center;justify-content:center';
  modal.innerHTML = `
    <div style="background:#0d1525;border:1px solid #1e2d45;border-radius:16px;padding:40px;max-width:420px;width:90%;text-align:center">
      <div style="font-size:2.5rem;margin-bottom:16px">🚀</div>
      <h2 style="color:#e2e8f0;margin-bottom:8px">今日額度已用完</h2>
      <p style="color:#64748b;font-size:0.9rem;margin-bottom:24px;line-height:1.6">
        升級到 Pro 計劃，享受無限次數分析、AI 研究報告、組合追蹤等功能。
      </p>
      <a href="pricing.html" style="display:block;background:#00d4ff;color:#000;padding:12px;border-radius:8px;font-weight:700;text-decoration:none;margin-bottom:12px">
        升級 Pro — $19/月
      </a>
      <button onclick="document.getElementById('quotaModal').remove()" style="background:transparent;border:1px solid #1e2d45;color:#64748b;padding:10px;border-radius:8px;width:100%;cursor:pointer">
        明天再試（免費版）
      </button>
    </div>
  `;
  document.body.appendChild(modal);
}

// Override fetch to handle 429
const originalFetch = window.fetch;
window.fetch = async function(...args) {
  const response = await originalFetch(...args);
  if (response.status === 429) {
    const data = await response.clone().json().catch(() => ({}));
    if (data.detail?.error === 'quota_exceeded') {
      showQuotaModal();
    }
  }
  return response;
};
