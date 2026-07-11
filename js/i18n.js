const I18N = {
  currentLang: localStorage.getItem('xfinlab_lang') || null,
  translations: {},
  PRIORITY_LANGS: ['en', 'es', 'de', 'fr', 'pt', 'ja', 'zh-TW', 'zh-CN', 'zh-HK', 'ko', 'ru', 'ar', 'hi', 'id', 'tr'],

  async init() {
    try {
      const lang = this.currentLang;
      const url = lang ? `https://api.xfinlab.com/api/i18n/${lang}` : `https://api.xfinlab.com/api/i18n/detect`;
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
    switcher.style.cssText = 'position:fixed;bottom:80px;right:24px;z-index:9998;';

    const btn = document.createElement('button');
    btn.style.cssText = 'background:#0d1525;border:1px solid #1e2d45;color:#e2e8f0;padding:8px 14px;border-radius:8px;cursor:pointer;font-size:0.82rem;white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,0.3);';
    btn.textContent = '🌐 ' + (supportedLangs[this.currentLang] || 'Language');

    const panel = document.createElement('div');
    panel.style.cssText = 'display:none;position:absolute;bottom:44px;right:0;background:#0d1525;border:1px solid #1e2d45;border-radius:10px;width:210px;box-shadow:0 8px 24px rgba(0,0,0,0.5);overflow:hidden;';

    // Header
    const header = document.createElement('div');
    header.style.cssText = 'padding:10px 14px 6px;border-bottom:1px solid #1e2d45;';
    header.innerHTML = '<div style="font-size:0.68rem;font-weight:600;letter-spacing:0.1em;text-transform:uppercase;color:#64748b;margin-bottom:6px;">Language</div>';

    // 搜尋框
    const searchInput = document.createElement('input');
    searchInput.placeholder = '🔍 Search all 46 languages...';
    searchInput.style.cssText = 'width:100%;background:#080c14;border:1px solid #1e2d45;color:#e2e8f0;padding:6px 10px;border-radius:6px;font-size:0.78rem;font-family:inherit;box-sizing:border-box;outline:none;';
    header.appendChild(searchInput);
    panel.appendChild(header);

    // 語言列表（固定高度可滾動）
    const list = document.createElement('div');
    list.style.cssText = 'height:280px;overflow-y:auto;overscroll-behavior:contain;';

    // 自定義 scrollbar
    const style = document.createElement('style');
    style.textContent = '#langSwitcher div::-webkit-scrollbar{width:4px}#langSwitcher div::-webkit-scrollbar-track{background:#0d1525}#langSwitcher div::-webkit-scrollbar-thumb{background:#1e2d45;border-radius:99px}';
    document.head.appendChild(style);

    const allEntries = Object.entries(supportedLangs);
    const priorityCodes = this.PRIORITY_LANGS;

    const renderList = (filter = '') => {
      list.innerHTML = '';

      let entries;
      if (filter.trim()) {
        entries = allEntries.filter(([code, name]) =>
          name.toLowerCase().includes(filter.toLowerCase()) ||
          code.toLowerCase().includes(filter.toLowerCase())
        );
      } else {
        // 優先語言在頂，其餘按字母排
        const priorityEntries = priorityCodes
          .filter(c => supportedLangs[c])
          .map(c => [c, supportedLangs[c]]);
        const restEntries = allEntries
          .filter(([c]) => !priorityCodes.includes(c))
          .sort((a, b) => a[1].localeCompare(b[1]));

        // 分隔線
        entries = [...priorityEntries, null, ...restEntries];
      }

      if (entries.length === 0) {
        list.innerHTML = '<div style="padding:16px;color:#64748b;font-size:0.8rem;text-align:center;">No results</div>';
        return;
      }

      entries.forEach(entry => {
        if (entry === null) {
          // 分隔線
          const sep = document.createElement('div');
          sep.style.cssText = 'height:1px;background:#1e2d45;margin:4px 0;';
          list.appendChild(sep);
          return;
        }

        const [code, name] = entry;
        const isActive = code === this.currentLang;
        const item = document.createElement('div');
        item.style.cssText = `padding:9px 14px;cursor:pointer;font-size:0.82rem;display:flex;justify-content:space-between;align-items:center;transition:background 0.1s;color:${isActive ? '#00d4ff' : '#e2e8f0'};background:${isActive ? 'rgba(0,212,255,0.08)' : 'transparent'};`;
        item.innerHTML = `<span>${name}</span>${isActive ? '<span style="color:#00d4ff;font-size:0.75rem;font-weight:700;">✓</span>' : ''}`;
        item.onmouseenter = () => { if (!isActive) item.style.background = '#111d30'; };
        item.onmouseleave = () => { item.style.background = isActive ? 'rgba(0,212,255,0.08)' : 'transparent'; };
        item.onclick = () => I18N.setLang(code);
        list.appendChild(item);
      });
    };

    renderList();
    searchInput.addEventListener('input', () => renderList(searchInput.value));
    panel.appendChild(list);

    // Footer
    const footer = document.createElement('div');
    footer.style.cssText = 'padding:6px 14px;border-top:1px solid #1e2d45;font-size:0.68rem;color:#64748b;text-align:center;';
    footer.textContent = `${allEntries.length} languages available`;
    panel.appendChild(footer);

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
