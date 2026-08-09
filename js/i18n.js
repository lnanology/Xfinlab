const I18N={currentLang:localStorage.getItem("xfinlab_lang")||null,translations:{},PRIORITY_LANGS:["en","es","de","fr","pt","ja","zh-TW","zh-CN","zh-HK","ko","ru","ar","hi","id","tr"],STATIC_LANGS:["de","es","pt","fr","it","fa","zh-CN","zh-TW","ja","ko","hi","ar","bn","ru","ur","id","pcm","mr"],detectUrlLang(){const e=location.pathname.match(/^\/([^\/]+)\/(index\.html|pricing\.html|free-signals\.html)$/);return e&&this.STATIC_LANGS.includes(e[1])?e[1]:null},currentFlagshipPage(){const e=location.pathname;if(e==="/"||e==="/index.html")return"index.html";if(e==="/pricing.html")return"pricing.html";if(e==="/free-signals.html")return"free-signals.html";const t=e.match(/^\/[^\/]+\/(index\.html|pricing\.html|free-signals\.html)$/);return t?t[1]:null},localizedFlagshipUrl(e){const t=this.currentFlagshipPage();return t?(e==="en"?t==="index.html"?"/":"/"+t:this.STATIC_LANGS.includes(e)?"/"+e+"/"+t:null):null},async init(){try{const u=this.detectUrlLang();if(u){this.currentLang=u,localStorage.setItem("xfinlab_lang",u)}const e=this.currentLang;let t;if(e){const n=await fetch(`https://api.xfinlab.com/api/i18n/${e}`);t=await n.json()}else{const e=await fetch("https://api.xfinlab.com/api/i18n/detect"),n=await e.json(),a=this.matchBrowserLanguage(n.supported_languages);if(a&&a!==n.language){const e=await fetch(`https://api.xfinlab.com/api/i18n/${a}`);t=await e.json()}else t=n;n.country&&(t.country=n.country)}this.currentLang=t.language,this.translations=t.translations,localStorage.setItem("xfinlab_lang",this.currentLang),t.country&&localStorage.setItem("xfinlab_country",t.country),this.apply(),this.addLanguageSwitcher(t.supported_languages)}catch(e){}},matchBrowserLanguage(e){if(!e)return null;const t=navigator.languages&&navigator.languages.length?navigator.languages:[navigator.language].filter(Boolean);for(const n of t){if(!n)continue;if(e[n])return n;const t=Object.keys(e).find(e=>e.toLowerCase()===n.toLowerCase());if(t)return t;const a=n.split("-")[0].toLowerCase();if(e[a])return a;const r=Object.keys(e).find(e=>e.split("-")[0].toLowerCase()===a);if(r)return r}return null},t(e){return this.translations[e]||e},apply(){document.querySelectorAll("[data-i18n]").forEach(e=>{const t=e.getAttribute("data-i18n");this.translations[t]&&(e.textContent=this.translations[t])}),document.querySelectorAll("[data-i18n-placeholder]").forEach(e=>{const t=e.getAttribute("data-i18n-placeholder");this.translations[t]&&(e.placeholder=this.translations[t])}),document.querySelectorAll("[data-i18n-aria-label]").forEach(e=>{const t=e.getAttribute("data-i18n-aria-label");this.translations[t]&&e.setAttribute("aria-label",this.translations[t])}),document.dispatchEvent(new CustomEvent("i18nApplied"))},setLang(e){localStorage.setItem("xfinlab_lang",e);const t=this.localizedFlagshipUrl(e);t?location.href=t:location.reload()},addLanguageSwitcher(e){if(document.getElementById("langSwitcher"))return;
// 2026-08-09 (AJ: "語言好似CMC咁按ICON顯示" -- centered full modal grid
// with flag emoji, instead of a small corner-anchored dropdown). The
// modal itself is appended to document.body, NOT inside #langSwitcher --
// js/mobile-widget-dock.js only reparents #langSwitcher (the trigger
// pill) into the shared bottom dock; a full-viewport centered modal
// doesn't need (and shouldn't get) the dock's "position panel above the
// bar" override that the old anchored dropdown relied on.
const FLAGS={en:"🇺🇸",es:"🇪🇸",fr:"🇫🇷",de:"🇩🇪",it:"🇮🇹",pt:"🇵🇹",ru:"🇷🇺",nl:"🇳🇱",pl:"🇵🇱",ro:"🇷🇴",uk:"🇺🇦",sr:"🇷🇸","zh-TW":"🇹🇼","zh-HK":"🇭🇰","zh-CN":"🇨🇳",ja:"🇯🇵",ko:"🇰🇷",hi:"🇮🇳",ar:"🇸🇦",id:"🇮🇩",th:"🇹🇭",vi:"🇻🇳",tr:"🇹🇷",fa:"🇮🇷",ur:"🇵🇰",bn:"🇧🇩",tl:"🇵🇭",ms:"🇲🇾",sw:"🇰🇪",ne:"🇳🇵",mr:"🇮🇳",te:"🇮🇳",ta:"🇮🇳",gu:"🇮🇳",pa:"🇮🇳",ml:"🇮🇳",kn:"🇮🇳",or:"🇮🇳",ps:"🇦🇫",ha:"🇳🇬",ku:"🏳️",si:"🇱🇰",uz:"🇺🇿",az:"🇦🇿",jv:"🇮🇩",su:"🇮🇩",pcm:"🇳🇬"};
const wrap=document.createElement("div");
wrap.id="langSwitcher";
wrap.style.cssText="position:fixed;bottom:136px;right:24px;z-index:9998;";
const trigger=document.createElement("button");
trigger.style.cssText="background:var(--bg-card,#FFFFFF);border:1px solid var(--border-color,#000000);color:var(--text-primary,#000000);padding:8px 14px;border-radius:8px;cursor:pointer;font-size:0.82rem;white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,0.15);";
trigger.textContent=(FLAGS[this.currentLang]||"🌐")+" "+(e[this.currentLang]||"Language");

const overlay=document.createElement("div");
overlay.style.cssText="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:99999;align-items:center;justify-content:center;padding:20px;box-sizing:border-box;";

const modal=document.createElement("div");
modal.style.cssText="background:var(--bg-card,#FFFFFF);border-radius:16px;width:min(560px,100%);max-height:min(640px,88vh);display:flex;flex-direction:column;overflow:hidden;box-shadow:0 24px 64px rgba(0,0,0,0.35);";

const head=document.createElement("div");
head.style.cssText="display:flex;align-items:center;justify-content:space-between;padding:18px 20px;border-bottom:1px solid var(--border-color,#000000);";
const title=document.createElement("div");
title.style.cssText="font-size:1.05rem;font-weight:700;color:var(--text-primary,#000000);";
title.textContent="Language";
const closeBtn=document.createElement("button");
closeBtn.setAttribute("aria-label","Close");
closeBtn.style.cssText="background:transparent;border:none;color:var(--text-muted,#666666);font-size:1.3rem;line-height:1;cursor:pointer;padding:4px 8px;";
closeBtn.textContent="✕";
head.appendChild(title);head.appendChild(closeBtn);

const searchWrap=document.createElement("div");
searchWrap.style.cssText="padding:14px 20px;border-bottom:1px solid var(--border-color,#000000);";
const input=document.createElement("input");
input.placeholder="🔍 Search all "+Object.keys(e).length+" languages...";
input.style.cssText="width:100%;background:var(--bg-primary,#FFFFFF);border:1px solid var(--border-color,#000000);color:var(--text-primary,#000000);padding:10px 12px;border-radius:8px;font-size:0.88rem;font-family:inherit;box-sizing:border-box;outline:none;";
searchWrap.appendChild(input);

const grid=document.createElement("div");
grid.style.cssText="padding:14px 16px;overflow-y:auto;display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:6px;flex:1;";

const foot=document.createElement("div");
foot.style.cssText="padding:8px 20px;border-top:1px solid var(--border-color,#000000);font-size:0.72rem;color:var(--text-muted,#666666);text-align:center;";

const entries=Object.entries(e),priority=this.PRIORITY_LANGS;
const render=(q="")=>{
  grid.innerHTML="";
  let list;
  if(q.trim()){
    list=entries.filter(([code,name])=>name.toLowerCase().includes(q.toLowerCase())||code.toLowerCase().includes(q.toLowerCase()));
  }else{
    list=[...priority.filter(c=>e[c]).map(c=>[c,e[c]]),...entries.filter(([c])=>!priority.includes(c)).sort((a,b)=>a[1].localeCompare(b[1]))];
  }
  if(list.length===0){
    grid.innerHTML='<div style="grid-column:1/-1;padding:24px;color:var(--text-muted,#666666);font-size:0.85rem;text-align:center;">No results</div>';
    foot.textContent="0 languages";
    return;
  }
  list.forEach(([code,name])=>{
    const active=code===this.currentLang;
    const cell=document.createElement("button");
    cell.style.cssText="display:flex;align-items:center;gap:8px;padding:10px 12px;border-radius:10px;cursor:pointer;font-size:0.85rem;text-align:left;border:1px solid "+(active?"var(--accent-blue,#D35400)":"transparent")+";background:"+(active?"rgba(211,84,0,0.08)":"transparent")+";color:"+(active?"var(--accent-blue,#D35400)":"var(--text-primary,#000000)")+";font-family:inherit;width:100%;box-sizing:border-box;";
    cell.innerHTML='<span style="font-size:1.1rem;flex-shrink:0;">'+(FLAGS[code]||"🏳️")+'</span><span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'+name+'</span>'+(active?'<span style="margin-left:auto;font-weight:700;">✓</span>':"");
    cell.onmouseenter=()=>{if(!active)cell.style.background="var(--bg-secondary,#F8FAFC)";};
    cell.onmouseleave=()=>{cell.style.background=active?"rgba(211,84,0,0.08)":"transparent";};
    cell.onclick=()=>I18N.setLang(code);
    grid.appendChild(cell);
  });
  foot.textContent=list.length+" of "+entries.length+" languages";
};
render();
input.addEventListener("input",()=>render(input.value));

modal.appendChild(head);modal.appendChild(searchWrap);modal.appendChild(grid);modal.appendChild(foot);
overlay.appendChild(modal);

const openModal=()=>{overlay.style.display="flex";input.value="";render();setTimeout(()=>input.focus(),50);};
const closeModal=()=>{overlay.style.display="none";};
trigger.onclick=e=>{e.stopPropagation();openModal();};
closeBtn.onclick=closeModal;
overlay.onclick=e=>{if(e.target===overlay)closeModal();};
document.addEventListener("keydown",e=>{if(e.key==="Escape")closeModal();});

wrap.appendChild(trigger);
document.body.appendChild(wrap);
document.body.appendChild(overlay);}};document.addEventListener("DOMContentLoaded",()=>I18N.init());