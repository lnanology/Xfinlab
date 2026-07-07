const Onboarding = {
  steps: [
    {title:"Welcome to XFINLAB 🚀",desc:"AI-powered investment intelligence. Let's get you started in 3 quick steps.",action:"Get Started",target:null},
    {title:"Step 1: Analyze Your First Stock 📊",desc:"Type any stock ticker (e.g. AAPL, NVDA) and click Analyze for instant AI insights.",action:"Try It Now",target:"#heroTicker"},
    {title:"Step 2: Join Free Telegram Signals 📡",desc:"Get daily AI stock analysis delivered to Telegram — completely free.",action:"Join Channel",target:"#tgWidget button"},
    {title:"Step 3: You're All Set! 🎉",desc:"You've earned 3 bonus analyses! Start exploring AI-powered investment tools.",action:"Start Investing",target:null}
  ],
  currentStep:0,
  token:null,
  async init(){
    this.token=localStorage.getItem('xfinlab_token');
    if(localStorage.getItem('xfinlab_onboarding_done'))return;
    setTimeout(()=>this.show(),1500);
  },
  show(){
    this.currentStep=0;
    const overlay=document.createElement('div');
    overlay.id='onboardingOverlay';
    overlay.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,0.75);z-index:9999;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(4px);';
    const modal=document.createElement('div');
    modal.id='onboardingModal';
    modal.style.cssText='background:#0d1525;border:1px solid #1e2d45;border-radius:16px;padding:36px;max-width:420px;width:90%;position:relative;';
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
    this.renderStep(modal);
  },
  renderStep(modal){
    const step=this.steps[this.currentStep];
    const total=this.steps.length;
    const isLast=this.currentStep===total-1;
    const dots=Array.from({length:total},(_,i)=>`<div style="width:8px;height:8px;border-radius:50%;background:${i===this.currentStep?'#00d4ff':'#1e2d45'};"></div>`).join('');
    modal.innerHTML=`
      <button onclick="Onboarding.dismiss()" style="position:absolute;top:16px;right:16px;background:none;border:none;color:#64748b;cursor:pointer;font-size:1.2rem;">✕</button>
      <div style="display:flex;gap:6px;justify-content:center;margin-bottom:24px;">${dots}</div>
      <div style="text-align:center;margin-bottom:24px;">
        <div style="font-size:1.3rem;font-weight:700;color:#e2e8f0;margin-bottom:10px;">${step.title}</div>
        <div style="font-size:0.875rem;color:#94a3b8;line-height:1.6;">${step.desc}</div>
      </div>
      ${isLast?'<div style="background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.3);border-radius:8px;padding:12px;text-align:center;margin-bottom:20px;"><div style="color:#10b981;font-weight:600;font-size:0.875rem;">+3 Bonus Analyses Unlocked!</div></div>':''}
      <button onclick="Onboarding.nextStep()" style="width:100%;background:#00d4ff;color:#000;border:none;padding:13px;border-radius:8px;font-weight:700;font-size:0.9rem;cursor:pointer;margin-bottom:10px;">${step.action}</button>
      ${!isLast?'<button onclick="Onboarding.dismiss()" style="width:100%;background:transparent;border:none;color:#64748b;font-size:0.8rem;cursor:pointer;padding:4px;">Skip for now</button>':''}
    `;
  },
  async nextStep(){
    if(this.currentStep===1){const el=document.querySelector('#heroTicker,#symbolInput,.ticker-input');if(el)el.focus();}
    if(this.currentStep===2){const el=document.querySelector('#tgWidget button');if(el)el.click();}
    if(this.token){try{await fetch('https://web-production-86882.up.railway.app/api/onboarding/complete-step/'+(this.currentStep+1)+'?token='+this.token,{method:'POST'});}catch(e){}}
    if(this.currentStep<this.steps.length-1){this.currentStep++;const m=document.getElementById('onboardingModal');if(m)this.renderStep(m);}
    else this.dismiss();
  },
  dismiss(){
    localStorage.setItem('xfinlab_onboarding_done','1');
    const el=document.getElementById('onboardingOverlay');
    if(el){el.style.opacity='0';el.style.transition='opacity 0.3s';setTimeout(()=>el.remove(),300);}
  },
  reset(){localStorage.removeItem('xfinlab_onboarding_done');this.show();}
};
document.addEventListener('DOMContentLoaded',()=>Onboarding.init());
