!function(){
function _t(k,f){return (typeof I18N!=="undefined"&&I18N.translations&&I18N.translations[k])||f}
var e=[
  {icon:"📊",key:"ai_loading_step_market",label:"Reading Market..."},
  {icon:"📰",key:"ai_loading_step_news",label:"Reading News..."},
  {icon:"📈",key:"ai_loading_step_charts",label:"Scanning Charts..."},
  {icon:"🧠",key:"ai_loading_step_research",label:"Building Research..."},
  {icon:"🎯",key:"ai_loading_step_score",label:"Calculating Research Score..."},
  {icon:"📄",key:"ai_loading_step_report",label:"Generating Final Report..."}
],a=0,t=null,n=0,i=!1,l=null,o=null,cvStop=null,isPaid=!1;
// 2026-08-10 (task #763, AJ: replace the plain step-card loading UI with a
// nicer plan-gated animation). Plan is read once at first-build time from
// localStorage.xfinlab_user.plan -- same source js/points-badge.js already
// reads from. Any plan other than "free" (basic/pro/proplus/professional/
// enterprise) counts as paid; if the user upgrades mid-session the overlay
// keeps whatever it was built with until next page load, same tradeoff the
// existing `i` build-once guard already accepted for other overlay content.
function getPlan(){try{return (JSON.parse(localStorage.getItem("xfinlab_user")||"{}").plan||"free").toLowerCase()}catch(x){return "free"}}
function c(){l&&l.querySelectorAll(".xfl-step").forEach(function(e){var a=parseInt(e.getAttribute("data-i"),10);e.classList.toggle("active",a===n),e.classList.toggle("done",a<n)});u()}
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
// Canvas 2D "quantum brain" animation for paid tiers (basic/pro/proplus+):
// a handful of drifting particles with proximity lines (constellation
// look) plus a pulsing core in the middle, meant to read as "the AI is
// actively thinking" rather than a static spinner. Kept intentionally
// small/cheap (200x140 canvas, 14 particles) since it runs the whole time
// the loading overlay is visible.
function startCanvasAnim(canvas){
  var ctx=canvas.getContext("2d");
  if(!ctx)return null;
  var w=canvas.width,h=canvas.height;
  var accent=(getComputedStyle(document.documentElement).getPropertyValue("--accent-blue")||"#2563EB").trim()||"#2563EB";
  var rgb=function(hex){var m=/^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);return m?parseInt(m[1],16)+","+parseInt(m[2],16)+","+parseInt(m[3],16):"37,99,235"}(accent);
  var particles=[];
  for(var i=0;i<14;i++)particles.push({x:Math.random()*w,y:Math.random()*h,vx:(Math.random()-0.5)*0.5,vy:(Math.random()-0.5)*0.5});
  var raf=null,stopped=!1;
  function frame(){
    if(stopped)return;
    ctx.clearRect(0,0,w,h);
    particles.forEach(function(p){
      p.x+=p.vx;p.y+=p.vy;
      if(p.x<0||p.x>w)p.vx*=-1;
      if(p.y<0||p.y>h)p.vy*=-1;
    });
    ctx.lineWidth=1;
    for(var i=0;i<particles.length;i++)for(var j=i+1;j<particles.length;j++){
      var dx=particles[i].x-particles[j].x,dy=particles[i].y-particles[j].y,dist=Math.sqrt(dx*dx+dy*dy);
      if(dist<50){
        ctx.strokeStyle="rgba("+rgb+","+((1-dist/50)*0.45).toFixed(2)+")";
        ctx.beginPath();ctx.moveTo(particles[i].x,particles[i].y);ctx.lineTo(particles[j].x,particles[j].y);ctx.stroke();
      }
    }
    particles.forEach(function(p){
      ctx.fillStyle="rgb("+rgb+")";
      ctx.beginPath();ctx.arc(p.x,p.y,2,0,Math.PI*2);ctx.fill();
    });
    var pulse=8+Math.sin(Date.now()/450)*3;
    ctx.fillStyle="rgba("+rgb+",0.22)";
    ctx.beginPath();ctx.arc(w/2,h/2,pulse+11,0,Math.PI*2);ctx.fill();
    ctx.fillStyle="rgb("+rgb+")";
    ctx.beginPath();ctx.arc(w/2,h/2,4,0,Math.PI*2);ctx.fill();
    raf=requestAnimationFrame(frame);
  }
  frame();
  return function(){stopped=!0;raf&&cancelAnimationFrame(raf)};
}
window.startAiLoading=function s(){try{if("loading"===document.readyState)return void document.addEventListener("DOMContentLoaded",s,{once:!0});!function(){if(!i){i=!0;isPaid="free"!==getPlan();var st=document.createElement("style");st.textContent='#xfl-ai-loading-overlay{position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;background:rgba(17,17,17,0.45);backdrop-filter:blur(3px);opacity:0;transition:opacity .2s ease;pointer-events:none}#xfl-ai-loading-overlay.show{opacity:1;pointer-events:auto}#xfl-ai-loading-card{background:var(--bg-card,#fff);border-radius:16px;padding:1.75rem 2rem;width:min(560px,92vw);box-shadow:0 20px 60px rgba(0,0,0,0.25);font-family:"Inter",sans-serif;text-align:center}#xfl-ai-loading-card .xfl-head{font-size:0.8rem;font-weight:600;letter-spacing:.02em;color:var(--accent-blue,#2563EB);margin-bottom:.9rem;display:flex;align-items:center;justify-content:center;gap:.4rem}#xfl-ai-loading-card .xfl-head .xfl-dot{width:7px;height:7px;border-radius:50%;background:var(--accent-blue,#2563EB);animation:xfl-pulse 1.1s ease-in-out infinite}.xfl-anim-wrap{position:relative;width:100%;height:140px;display:flex;align-items:center;justify-content:center;margin-bottom:.9rem}.xfl-quantum-canvas{width:200px;height:140px}.xfl-pulse-rings{position:relative;width:64px;height:64px}.xfl-pulse-rings span{position:absolute;inset:0;border-radius:50%;border:2px solid var(--accent-blue,#2563EB);opacity:0;animation:xfl-ring 2.1s ease-out infinite}.xfl-pulse-rings span:nth-child(2){animation-delay:.7s}.xfl-pulse-rings span:nth-child(3){animation-delay:1.4s}.xfl-pulse-rings .xfl-pulse-core{position:absolute;left:50%;top:50%;width:14px;height:14px;margin:-7px 0 0 -7px;border-radius:50%;background:var(--accent-blue,#2563EB)}.xfl-steps-row{display:flex;flex-wrap:wrap;gap:6px;justify-content:center}.xfl-step{display:flex;align-items:center;gap:.3rem;padding:.32rem .6rem;border-radius:999px;background:var(--bg-secondary,#f1f5f9);font-size:0.7rem;color:var(--text-muted,#666);opacity:.5;transition:opacity .2s ease,background .2s ease,color .2s ease;white-space:nowrap}.xfl-step.active{opacity:1;background:rgba(37,99,235,0.12);color:var(--accent-blue,#2563EB);font-weight:600}.xfl-step.done{opacity:.8;color:var(--text-secondary,#333)}.xfl-step .xfl-icon{font-size:0.95em}.xfl-step .xfl-check{color:var(--accent-green,#16A34A);font-size:0.75em;opacity:0}.xfl-step.done .xfl-check{opacity:1}@keyframes xfl-pulse{0%,100%{opacity:1}50%{opacity:.3}}@keyframes xfl-ring{0%{transform:scale(0.4);opacity:.6}100%{transform:scale(1.6);opacity:0}}';document.head.appendChild(st);var ov=document.createElement("div");ov.id="xfl-ai-loading-overlay";var animHtml=isPaid?'<canvas class="xfl-quantum-canvas" width="200" height="140"></canvas>':'<div class="xfl-pulse-rings"><span></span><span></span><span></span><span class="xfl-pulse-core"></span></div>';var stepsHtml=e.map(function(e,a){return'<div class="xfl-step" data-i="'+a+'"><span class="xfl-icon">'+e.icon+'</span><span class="xfl-label">'+e.label+'</span><span class="xfl-check">✓</span></div>'}).join("");ov.innerHTML='<div id="xfl-ai-loading-card"><div class="xfl-head"><span class="xfl-dot"></span><span class="xfl-head-text">AI 正在分析緊真實市場數據</span></div><div class="xfl-anim-wrap">'+animHtml+'</div><div class="xfl-steps-row">'+stepsHtml+"</div></div>",document.body.appendChild(ov),l=ov}}(),u(),a++,o&&(clearTimeout(o),o=null),1===a&&(n=0,c(),l.classList.add("show"),t=setInterval(r,1100),isPaid&&!cvStop&&function(){var cv=l.querySelector(".xfl-quantum-canvas");cv&&(cvStop=startCanvasAnim(cv))}())}catch(e){}},window.stopAiLoading=function(){try{0===(a=Math.max(0,a-1))&&l&&(l.classList.remove("show"),t&&(clearInterval(t),t=null),cvStop&&(cvStop(),cvStop=null),o=setTimeout(function(){n=0},250))}catch(e){}}
document.addEventListener("i18nApplied",u)
}();
