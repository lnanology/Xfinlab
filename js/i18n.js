const I18N = {
  currentLang: localStorage.getItem('xfinlab_lang') || null,
  translations: {},

  async init() {
    try {
      const lang = this.currentLang;
      const url = lang
        ? `http://127.0.0.1:8002/api/i18n/${lang}`
        : `http://127.0.0.1:8002/api/i18n/detect`;
      const res = await fetch(url);
      const data = await res.json();
      this.currentLang = data.language;
      this.translations = data.translations;
      localStorage.setItem('xfinlab_lang', this.currentLang);
      this.apply();
      this.addLanguageSwitcher(data.supported_languages);
    } catch(e) {}
  },

  t(key) { return this.translations[key] || key; },

  apply() {
    document.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.getAttribute('data-i18n');
      if (this.translations[key]) el.textContent = this.translations[key];
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
      const key = el.getAttribute('data-i18n-placeholder');
      if (this.translations[key]) el.placeholder = this.translations[key];
    });
  },

  setLang(lang) {
    localStorage.setItem('xfinlab_lang', lang);
    location.reload();
  },

  addLanguageSwitcher(supportedLangs) {
    if (document.getElementById('langSwitcher')) return;

    const switcher = document.createElement('div');
    switcher.id = 'langSwitcher';
    switcher.style.cssText = 'position:fixed;bottom:80px;right:24px;z-index:998;';

    const btn = document.createElement('button');
    btn.style.cssText = 'background:#0d1525;border:1px solid #1e2d45;color:#e2e8f0;padding:8px 14px;border-radius:8px;cursor:pointer;font-size:0.82rem;white-space:nowrap;';
    btn.textContent = '🌐 ' + (supportedLangs[this.currentLang] || 'Language');

    const panel = document.createElement('div');
    panel.style.cssText = 'display:none;position:absolute;bottom:44px;right:0;background:#0d1525;border:1px solid #1e2d45;border-radius:10px;width:220px;overflow:hidden;box-shadow:0 8px 24px rgba(0,0,0,0.4);';

    // 搜尋框
    const searchWrap = document.createElement('div');
    searchWrap.style.cssText = 'padding:10px;border-bottom:1px solid #1e2d45;';
    const searchInput = document.createElement('input');
    searchInput.placeholder = '🔍 Search language...';
    searchInput.style.cssText = 'width:100%;background:#080c14;border:1px solid #1e2d45;color:#e2e8f0;padding:7px 10px;border-radius:6px;font-size:0.78rem;font-family:inherit;box-sizing:border-box;';
    searchWrap.appendChild(searchInput);
    panel.appendChild(searchWrap);

    // 語言列表（可滾動）
    const list = document.createElement('div');
    list.style.cssText = 'max-height:240px;overflow-y:auto;';

    const entries = Object.entries(supportedLangs);

    const renderList = (filter = '') => {
      list.innerHTML = '';
      const filtered = filter
        ? entries.filter(([code, name]) =>
            name.toLowerCase().includes(filter.toLowerCase()) ||
            code.toLowerCase().includes(filter.toLowerCase()))
        : entries;

      filtered.forEach(([code, name]) => {
        const item = document.createElement('div');
        const isActive = code === this.currentLang;
        item.style.cssText = `padding:9px 14px;cursor:pointer;font-size:0.82rem;color:${isActive ? '#00d4ff' : '#e2e8f0'};background:${isActive ? 'rgba(0,212,255,0.08)' : 'transparent'};display:flex;justify-content:space-between;align-items:center;`;
        item.innerHTML = `<span>${name}</span>${isActive ? '<span style="font-size:0.65rem;color:#00d4ff">✓</span>' : ''}`;
        item.onmouseenter = () => { if (!isActive) item.style.background = '#111d30'; };
        item.onmouseleave = () => { if (!isActive) item.style.background = 'transparent'; };
        item.onclick = () => I18N.setLang(code);
        list.appendChild(item);
      });

      if (filtered.length === 0) {
        list.innerHTML = '<div style="padding:12px;color:#64748b;font-size:0.8rem;text-align:center">No results</div>';
      }
    };

    renderList();
    searchInput.addEventListener('input', () => renderList(searchInput.value));
    panel.appendChild(list);

    btn.onclick = (e) => {
      e.stopPropagation();
      panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
      if (panel.style.display === 'block') {
        setTimeout(() => searchInput.focus(), 50);
      }
    };

    document.addEventListener('click', e => {
      if (!switcher.contains(e.target)) panel.style.display = 'none';
    });

    switcher.appendChild(panel);
    switcher.appendChild(btn);
    document.body.appendChild(switcher);
  }
};

document.addEventListener('DOMContentLoaded', () => I18N.init());
