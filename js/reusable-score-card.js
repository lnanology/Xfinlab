// Reusable Score Card renderer
// Usage: add <div class="reusable-score-card" data-title="標題" data-fund="78" data-tech="65" data-news="82" data-risk="28" data-overall="73"></div>

document.addEventListener('DOMContentLoaded', ()=>{
  function scoreColorClass(score){
    if(score >= 75) return 'score-good';
    if(score >= 45) return 'score-mid';
    return 'score-bad';
  }

  function renderCard(el){
    const title = el.dataset.title || '綜合評分';
    const fund = Number(el.dataset.fund ?? 0);
    const tech = Number(el.dataset.tech ?? 0);
    const news = Number(el.dataset.news ?? 0);
    const risk = Number(el.dataset.risk ?? 0);
    const overall = Number(el.dataset.overall ?? Math.round((fund+tech+news - risk)/3));

    el.classList.add('score-card-component');
    el.innerHTML = `
      <div class="ssc-header"><div class="ssc-title">${title}</div><div class="ssc-overall ${scoreColorClass(overall)}">${overall}</div></div>
      <div class="ssc-grid">
        ${metricRow('基本面', fund)}
        ${metricRow('技術面', tech)}
        ${metricRow('新聞面', news)}
        ${metricRow('風險', 100 - risk, true)}
      </div>
    `;

    // set widths
    [ ['fund', fund], ['tech', tech], ['news', news], ['risk', 100 - risk] ].forEach(([k,v])=>{
      const fill = el.querySelector(`.ssc-${k} .ssc-fill`);
      if(fill) fill.style.width = Math.max(0, Math.min(100, v)) + '%';
      const val = el.querySelector(`.ssc-${k} .ssc-val`);
      if(val) val.textContent = v;
      const cls = scoreColorClass(v);
      const bar = el.querySelector(`.ssc-${k} .ssc-fill`);
      if(bar){ bar.classList.remove('score-good','score-mid','score-bad'); bar.classList.add(cls); }
    });

    // accessible aria
    el.querySelectorAll('.ssc-fill').forEach(f=>{
      f.setAttribute('role','progressbar');
      f.setAttribute('aria-valuemin','0');
      f.setAttribute('aria-valuemax','100');
      f.setAttribute('aria-valuenow', f.style.width.replace('%',''));
    });
  }

  function metricRow(label, value, reversed=false){
    // reversed true means higher is worse (used for risk)
    return `
      <div class="ssc-row ssc-${label==='基本面'? 'fund': label==='技術面'? 'tech': label==='新聞面'? 'news': 'risk'}">
        <div class="ssc-label">${label}</div>
        <div class="ssc-bar">
          <div class="ssc-fill" style="width:0%"></div>
        </div>
        <div class="ssc-val">0</div>
      </div>
    `;
  }

  document.querySelectorAll('.reusable-score-card').forEach(el=>{
    try{ renderCard(el); }catch(e){ console.error('score-card render', e); }
  });
});
