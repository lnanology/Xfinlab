// 2026-08-08 fix: modal used hardcoded Chinese text regardless of UI
// language, a stale $19/mo price (pricing.html has shown $18 since task
// #440), and hardcoded dark-only hex colors that looked broken in the
// site's light-theme default (task #161). Now uses the shared _t(key,
// fallback) i18n pattern (matches js/ai-loading.js) and CSS variables.
if(typeof _t==="undefined"){var _t=function(k,f){return (typeof I18N!=="undefined"&&I18N.translations&&I18N.translations[k])||f}}
async function handleApiCall(t){try{return await t()}catch(t){if(429===t.status||t.message&&t.message.includes("quota"))throw showQuotaModal(),t;throw t}}function showQuotaModal(){const t=document.getElementById("quotaModal");t&&t.remove();const o=document.createElement("div");o.id="quotaModal",o.style.cssText="position:fixed;inset:0;background:rgba(0,0,0,0.8);z-index:9999;display:flex;align-items:center;justify-content:center";const title=_t("quota_modal_title","Today's Quota Used Up"),body=_t("quota_modal_body","Upgrade to Pro for unlimited analyses, AI research reports, portfolio tracking and more."),upgradeBtn=_t("quota_modal_upgrade_btn","Upgrade to Pro — $18/mo"),retryBtn=_t("quota_modal_retry_btn","Try again tomorrow (Free plan)");o.innerHTML=`
    <div style="background:var(--bg-card);border:1px solid var(--border-color);border-radius:16px;padding:40px;max-width:420px;width:90%;text-align:center">
      <div style="font-size:2.5rem;margin-bottom:16px">🚀</div>
      <h2 style="color:var(--text-primary);margin-bottom:8px">${title}</h2>
      <p style="color:var(--text-muted);font-size:0.9rem;margin-bottom:24px;line-height:1.6">
        ${body}
      </p>
      <a href="pricing.html" style="display:block;background:var(--accent-blue);color:#000;padding:12px;border-radius:8px;font-weight:700;text-decoration:none;margin-bottom:12px">
        ${upgradeBtn}
      </a>
      <button onclick="document.getElementById('quotaModal').remove()" style="background:transparent;border:1px solid var(--border-color);color:var(--text-muted);padding:10px;border-radius:8px;width:100%;cursor:pointer">
        ${retryBtn}
      </button>
    </div>
  `,document.body.appendChild(o)}const originalFetch=window.fetch;window.fetch=async function(...t){const o=await originalFetch(...t);if(429===o.status){const t=await o.clone().json().catch(()=>({}));"quota_exceeded"===t.detail?.error&&showQuotaModal()}return o};