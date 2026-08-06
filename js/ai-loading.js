!function(){
function _t(k,f){return (typeof I18N!=="undefined"&&I18N.translations&&I18N.translations[k])||f}
var e=[
  {icon:"📊",key:"ai_loading_step_market",label:"Reading Market..."},
  {icon:"📰",key:"ai_loading_step_news",label:"Reading News..."},
  {icon:"📈",key:"ai_loading_step_charts",label:"Scanning Charts..."},
  {icon:"🧠",key:"ai_loading_step_research",label:"Building Research..."},
  {icon:"🎯",key:"ai_loading_step_score",label:"Calculating Research Score..."},
  {icon:"📄",key:"ai_loading_step_report",label:"Generating Final Report..."}
],a=0,t=null,n=0,i=!1,l=null,o=null;
function c(){l&&l.querySelectorAll(".xfl-step").forEach(function(e){var a=parseInt(e.getAttribute("data-i"),10);e.classList.toggle("active",a===n),e.classList.toggle("done",a<n)})}
function r(){n<e.length-1&&(n++,c())}
// 2026-08-06 fix ("AI 正在分析緊真實市場數據" stuck untranslated even in
// English UI): the overlay DOM used to be built ONCE (guarded by the `i`
// flag below) and _t() was called at that first-build time to bake the
// translated text directly into innerHTML. If startAiLoading() ran before
// js/i18n.js's async fetch had resolved (very common -- it's the first
// user action on the page), I18N.translations was still empty, so the
// hardcoded Chinese/English fallback text got baked in permanently -- the
// `i` guard means the overlay is never rebuilt, and this markup has no
// data-i18n attributes, so I18N.apply() never revisits it either. Fix:
// keep the "build DOM once" structure (still cheap), but re-read _t() and
// update the label textContent every time the overlay is shown, plus on
// the i18nApplied event if it's already visible when translations arrive.
function u(){
  if(!l)return;
  var h=l.querySelector(".xfl-head-text");
  if(h)h.textContent=_t("ai_loading_header","AI 正在分析緊真實市場數據");
  l.querySelectorAll(".xfl-step").forEach(function(el){
    var idx=parseInt(el.getAttribute("data-i"),10),d=e[idx],lb=el.querySelector(".xfl-label");
    if(lb&&d)lb.textContent=_t(d.key,d.label);
  });
}
window.startAiLoading=function s(){try{if("loading"===document.readyState)return void document.addEventListener("DOMContentLoaded",s,{once:!0});!function(){if(!i){i=!0;var a=document.createElement("style");a.textContent='#xfl-ai-loading-overlay{position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;background:rgba(17,17,17,0.45);backdrop-filter:blur(3px);opacity:0;transition:opacity .2s ease;pointer-events:none}#xfl-ai-loading-overlay.show{opacity:1;pointer-events:auto}#xfl-ai-loading-card{background:var(--bg-card,#fff);border-radius:16px;padding:1.75rem 2rem;width:min(360px,88vw);box-shadow:0 20px 60px rgba(0,0,0,0.25);font-family:"Inter",sans-serif}#xfl-ai-loading-card .xfl-head{font-size:0.8rem;font-weight:600;letter-spacing:.02em;color:var(--accent-blue,#2563EB);margin-bottom:1rem;display:flex;align-items:center;gap:.4rem}#xfl-ai-loading-card .xfl-head .xfl-dot{width:7px;height:7px;border-radius:50%;background:var(--accent-blue,#2563EB);animation:xfl-pulse 1.1s ease-in-out infinite}.xfl-step{display:flex;align-items:center;gap:.6rem;padding:.4rem 0;font-size:0.88rem;color:var(--text-muted,#666);transition:color .2s ease,opacity .2s ease;opacity:0.45}.xfl-step.active{color:var(--text-primary,#111);opacity:1;font-weight:500}.xfl-step.done{color:var(--text-secondary,#333);opacity:0.75}.xfl-step .xfl-icon{width:1.3em;text-align:center}.xfl-step .xfl-check{margin-left:auto;color:var(--accent-green,#16A34A);font-size:0.8rem;opacity:0}.xfl-step.done .xfl-check{opacity:1}@keyframes xfl-pulse{0%,100%{opacity:1}50%{opacity:.3}}',document.head.appendChild(a);var t=document.createElement("div");t.id="xfl-ai-loading-overlay";var n=e.map(function(e,a){return'<div class="xfl-step" data-i="'+a+'"><span class="xfl-icon">'+e.icon+'</span><span class="xfl-label">'+e.label+'</span><span class="xfl-check">✓</span></div>'}).join("");t.innerHTML='<div id="xfl-ai-loading-card"><div class="xfl-head"><span class="xfl-dot"></span><span class="xfl-head-text">AI 正在分析緊真實市場數據</span></div>'+n+"</div>",document.body.appendChild(t),l=t}}(),u(),a++,o&&(clearTimeout(o),o=null),1===a&&(n=0,c(),l.classList.add("show"),t=setInterval(r,1100))}catch(e){}},window.stopAiLoading=function(){try{0===(a=Math.max(0,a-1))&&l&&(l.classList.remove("show"),t&&(clearInterval(t),t=null),o=setTimeout(function(){n=0},250))}catch(e){}}
document.addEventListener("i18nApplied",u)
}();
