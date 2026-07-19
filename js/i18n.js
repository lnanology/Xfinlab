const I18N = {
  currentLang: localStorage.getItem('xfinlab_lang') || null,
  translations: {},
  PRIORITY_LANGS: ['en', 'es', 'de', 'fr', 'pt', 'ja', 'zh-TW', 'zh-CN', 'zh-HK', 'ko', 'ru', 'ar', 'hi', 'id', 'tr'],

  async init() {
    try {
      const lang = this.currentLang;
      let data;

      if (lang) {
        // User has an explicit saved choice (picked from the switcher, or
        // resolved once before) -- always honour it, never re-guess.
        const res = await fetch(`https://api.xfinlab.com/api/i18n/${lang}`);
        data = await res.json();
      } else {
        // 2026-07-19 fix: first-visit language used to be decided purely
        // by IP geolocation (ipapi.co lookup via /i18n/detect) -- so a
        // Hong Kong user browsing over a US VPN, or anyone travelling,
        // got the "wrong" language even though their browser/OS was
        // correctly set to their real preferred language. Now we ask the
        // BROWSER what the user actually chose in their own settings
        // (navigator.languages) first, and only fall back to the IP
        // guess if none of the browser's preferred languages are in our
        // supported list. /i18n/detect is still called once here purely
        // to get `supported_languages` + `country` (the latter feeds
        // js/autocomplete.js's country-prioritized trending stocks --
        // unrelated to UI language, left untouched).
        const detectRes = await fetch(`https://api.xfinlab.com/api/i18n/detect`);
        const detectData = await detectRes.json();

        const browserLang = this.matchBrowserLanguage(detectData.supported_languages);
        if (browserLang && browserLang !== detectData.language) {
          const res = await fetch(`https://api.xfinlab.com/api/i18n/${browserLang}`);
          data = await res.json();
        } else {
          data = detectData;
        }
        if (detectData.country) data.country = detectData.country;
      }

      this.currentLang = data.language;
      this.translations = data.translations;
      localStorage.setItem('xfinlab_lang', this.currentLang);
      if (data.country) localStorage.setItem('xfinlab_country', data.country);
      this.apply();
      this.addLanguageSwitcher(data.supported_languages);
    } catch(e) {}
  },

  // Matches navigator.languages (the user's own browser/OS language
  // preference, in their preferred order) against our supported language
  // codes. Tries exact code match, then case-insensitive, then base-
  // language match (e.g. "en-GB" -> "en", "pt-BR" -> "pt", "zh" -> first
  // "zh-*" variant). Returns null if nothing matches, so the caller can
  // fall back to the IP-based guess.
  matchBrowserLanguage(supportedLangs) {
    if (!supportedLangs) return null;
    const prefs = (navigator.languages && navigator.languages.length)
      ? navigator.languages
      : [navigator.language].filter(Boolean);

    for (const raw of prefs) {
      if (!raw) continue;
      if (supportedLangs[raw]) return raw;
      const exact = Object.keys(supportedLangs).find(c => c.toLowerCase() === raw.toLowerCase());
      if (exact) return exact;
      const base = raw.split('-')[0].toLowerCase();
      if (supportedLangs[base]) return base;
      const baseMatch = Object.keys(supportedLangs).find(c => c.split('-')[0].toLowerCase() === base);
      if (baseMatch) return baseMatch;
    }
    return null;
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
    // Lets pages react to translations becoming available for content that
    // isn't a static [data-i18n] node (e.g. JS-templated strings like
    // pricing.html's per-tier token-quota lines).
    document.dispatchEvent(new CustomEvent('i18nApplied'));
  },

  setLang(lang) {
    localStorage.setItem('xfinlab_lang', lang);
    location.reload();
  },

  addLanguageSwitcher(supportedLangs) {
    if (document.getElementById('langSwitcher')) return;

    const switcher = document.createElement('div');
    switcher.id = 'langSwitcher';
    // Right-side floating stack (bottom-up): TG Signals widget (24) ->
    // Daily Signals badge (80, js/free-signals-badge.js) -> language
    // switcher (136, here) -> share widget (192, js/share-widget.js).
    // Was bottom:80 before, which sat exactly on top of the Daily
    // Signals badge -- bumped up to clear it.
    switcher.style.cssText = 'position:fixed;bottom:136px;right:24px;z-index:9998;';

    const btn = document.createElement('button');
    btn.style.cssText = 'background:var(--bg-card,#FFFFFF);border:1px solid var(--border-color,#000000);color:var(--text-primary,#000000);padding:8px 14px;border-radius:8px;cursor:pointer;font-size:0.82rem;white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,0.15);';
    btn.textContent = '🌐 ' + (supportedLangs[this.currentLang] || 'Language');

    const panel = document.createElement('div');
    panel.style.cssText = 'display:none;position:absolute;bottom:44px;right:0;background:var(--bg-card,#FFFFFF);border:1px solid var(--border-color,#000000);border-radius:10px;width:210px;box-shadow:0 8px 24px rgba(0,0,0,0.2);overflow:hidden;';

    // Header
    const header = document.createElement('div');
    header.style.cssText = 'padding:10px 14px 6px;border-bottom:1px solid var(--border-color,#000000);';
    header.innerHTML = '<div style="font-size:0.68rem;font-weight:600;letter-spacing:0.1em;text-transform:uppercase;color:var(--text-muted,#666666);margin-bottom:6px;">Language</div>';

    // 搜尋框
    const searchInput = document.createElement('input');
    searchInput.placeholder = '🔍 Search all 46 languages...';
    searchInput.style.cssText = 'width:100%;background:var(--bg-primary,#FFFFFF);border:1px solid var(--border-color,#000000);color:var(--text-primary,#000000);padding:6px 10px;border-radius:6px;font-size:0.78rem;font-family:inherit;box-sizing:border-box;outline:none;';
    header.appendChild(searchInput);
    panel.appendChild(header);

    // 語言列表（固定高度可滾動）
    const list = document.createElement('div');
    list.style.cssText = 'height:280px;overflow-y:auto;overscroll-behavior:contain;';

    // 自定義 scrollbar
    const style = document.createElement('style');
    style.textContent = '#langSwitcher div::-webkit-scrollbar{width:4px}#langSwitcher div::-webkit-scrollbar-track{background:var(--bg-card,#FFFFFF)}#langSwitcher div::-webkit-scrollbar-thumb{background:var(--border-color,#000000);border-radius:99px}';
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
        list.innerHTML = '<div style="padding:16px;color:var(--text-muted,#666666);font-size:0.8rem;text-align:center;">No results</div>';
        return;
      }

      entries.forEach(entry => {
        if (entry === null) {
          // 分隔線
          const sep = document.createElement('div');
          sep.style.cssText = 'height:1px;background:var(--border-color,#000000);margin:4px 0;';
          list.appendChild(sep);
          return;
        }

        const [code, name] = entry;
        const isActive = code === this.currentLang;
        const item = document.createElement('div');
        item.style.cssText = `padding:9px 14px;cursor:pointer;font-size:0.82rem;display:flex;justify-content:space-between;align-items:center;transition:background 0.1s;color:${isActive ? 'var(--accent-blue,#2563EB)' : 'var(--text-primary,#000000)'};background:${isActive ? 'rgba(37,99,235,0.08)' : 'transparent'};`;
        item.innerHTML = `<span>${name}</span>${isActive ? '<span style="color:var(--accent-blue,#2563EB);font-size:0.75rem;font-weight:700;">✓</span>' : ''}`;
        item.onmouseenter = () => { if (!isActive) item.style.background = 'var(--bg-secondary,#F8FAFC)'; };
        item.onmouseleave = () => { item.style.background = isActive ? 'rgba(37,99,235,0.08)' : 'transparent'; };
        item.onclick = () => I18N.setLang(code);
        list.appendChild(item);
      });
    };

    renderList();
    searchInput.addEventListener('input', () => renderList(searchInput.value));
    panel.appendChild(list);

    // Footer
    const footer = document.createElement('div');
    footer.style.cssText = 'padding:6px 14px;border-top:1px solid var(--border-color,#000000);font-size:0.68rem;color:var(--text-muted,#666666);text-align:center;';
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
