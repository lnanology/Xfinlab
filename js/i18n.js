const I18N = {
  currentLang: localStorage.getItem('xfinlab_lang') || null,
  translations: {},

  // 優先顯示語言
  PRIORITY_LANGS: ['en', 'es', 'de', 'fr', 'pt', 'ja', 'zh-TW', 'zh-CN'],

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
    panel.style.cssText = 'display:none;position:absolute;bottom:44px;right:0;background:#0d1525;border:1px solid #1e2d45;border-radius:10px;width:200px;overflow:hidden;box-shadow:0 8px 24px rgba(0,0,0,0.4);';

    // 搜尋框
    const searchWrap = document.createElement('div');
    searchWrap.style.cssText = 'padding:8px;border-bottom:1px solid #1e2d45;';
    const searchInput = document.createElement('input');
    searchInput.placeholder = '🔍 Search...';
    searchInput.style.cssText = 'width:100%;background:#080c14;border:1px solid #1e2d45;color:#e2e8f0;padding:6px 10px;border-radius:6px;font-size:0.78rem;font-family:inherit;box-sizing:border-box;outline:none;';
    searchWrap.appendChild(searchInput);
    panel.appendChild(searchWrap);

    // 語言列表
    const list = document.createElement('div');
    list.style.cssText = 'max-height:220px;overflow-y:auto;';

    const allEntries = Object.entries(supportedLangs);

    const renderList = (filter = '') => {
      list.innerHTML = '';

      let entries;
      if (filter) {
        // 搜尋模式：顯示所有匹配
        entries = allEntries.filter(([code, name]) =>
          name.toLowerCase().includes(filter.toLowerCase()) ||
          code.toLowerCase().includes(filter.toLowerCase())
        );
      } else {
        // 預設：只顯示8個優先語言
        const priority = this.PRIORITY_LANGS;
        const priorityEntries = priority
          .filter(code => supportedLangs[code])
          .map(code => [code, supportedLangs[code]]);

        // 如果目前語言唔係優先清單，加在頂部
        const curInPriority = priority.includes(this.currentLang);
        if (!curInPriority && this.currentLang && supportedLangs[this.currentLang]) {
          priorityEntries.unshift([this.currentLang, supportedLangs[this.currentLang]]);
        }
        entries = priorityEntries.slice(0, 8);

        // 加提示
        const hint = document.createElement('div');
        hint.style.cssText = 'padding:6px 14px;font-size:0.68rem;color:#64748b;border-bottom:1px solid #1e2d45;';
        hint.textContent = `Search to see all ${allEntries.length} languages`;
        list.appendChild(hint);
      }

      if (entries.length === 0) {
        const empty = document.createElement('div');
        empty.style.cssText = 'padding:12px;color:#64748b;font-size:0.8rem;text-align:center;';
        empty.textContent = 'No results';
        list.appendChild(empty);
        return;
      }

      entries.forEach(([code, name]) => {
        const isActive = code === this.currentLang;
        const item = document.createElement('div');
        item.style.cssText = `padding:9px 14px;cursor:pointer;font-size:0.82rem;color:${isActive ? '#00d4ff' : '#e2e8f0'};background:${isActive ? 'rgba(0,212,255,0.08)' : 'transparent'};display:flex;justify-content:space-between;align-items:center;`;
        item.innerHTML = `<span>${name}</span>${isActive ? '<span style="color:#00d4ff;font-size:0.7rem">✓</span>' : ''}`;
        item.onmouseenter = () => { if (!isActive) item.style.background = '#111d30'; };
        item.onmouseleave = () => { if (!isActive) item.style.background = isActive ? 'rgba(0,212,255,0.08)' : 'transparent'; };
        item.onclick = () => I18N.setLang(code);
        list.appendChild(item);
      });
    };

    renderList();
    searchInput.addEventListener('input', () => renderList(searchInput.value));
    panel.appendChild(list);

    btn.onclick = (e) => {
      e.stopPropagation();
      const isOpen = panel.style.display === 'block';
      panel.style.display = isOpen ? 'none' : 'block';
      if (!isOpen) {
        searchInput.value = '';
        renderList();
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
