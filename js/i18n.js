// XFINLAB i18n - Auto language detection
const I18N = {
  currentLang: localStorage.getItem('xfinlab_lang') || null,
  translations: {},

  async init() {
    try {
      // 先用 localStorage 嘅語言，冇就自動偵測
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
    } catch(e) {
      console.log('i18n init failed:', e);
    }
  },

  t(key) {
    return this.translations[key] || key;
  },

  apply() {
    // 自動翻譯有 data-i18n 屬性嘅元素
    document.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.getAttribute('data-i18n');
      if (this.translations[key]) {
        el.textContent = this.translations[key];
      }
    });

    // Placeholder
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
      const key = el.getAttribute('data-i18n-placeholder');
      if (this.translations[key]) {
        el.placeholder = this.translations[key];
      }
    });
  },

  setLang(lang) {
    localStorage.setItem('xfinlab_lang', lang);
    this.currentLang = lang;
    location.reload();
  },

  addLanguageSwitcher(supportedLangs) {
    const existing = document.getElementById('langSwitcher');
    if (existing) return;

    const switcher = document.createElement('div');
    switcher.id = 'langSwitcher';
    switcher.style.cssText = 'position:fixed;bottom:80px;right:24px;z-index:998;';

    const btn = document.createElement('button');
    btn.style.cssText = 'background:#0d1525;border:1px solid #1e2d45;color:#e2e8f0;padding:8px 14px;border-radius:8px;cursor:pointer;font-size:0.82rem;';
    btn.textContent = '🌐 ' + (supportedLangs[this.currentLang] || 'Language');

    const dropdown = document.createElement('div');
    dropdown.style.cssText = 'display:none;position:absolute;bottom:40px;right:0;background:#0d1525;border:1px solid #1e2d45;border-radius:8px;min-width:160px;overflow:hidden;';

    Object.entries(supportedLangs).forEach(([code, name]) => {
      const item = document.createElement('div');
      item.style.cssText = 'padding:10px 14px;cursor:pointer;font-size:0.82rem;color:#e2e8f0;';
      item.textContent = name;
      item.onmouseenter = () => item.style.background = '#111d30';
      item.onmouseleave = () => item.style.background = 'transparent';
      item.onclick = () => I18N.setLang(code);
      dropdown.appendChild(item);
    });

    btn.onclick = () => {
      dropdown.style.display = dropdown.style.display === 'none' ? 'block' : 'none';
    };

    document.addEventListener('click', e => {
      if (!switcher.contains(e.target)) dropdown.style.display = 'none';
    });

    switcher.appendChild(dropdown);
    switcher.appendChild(btn);
    document.body.appendChild(switcher);
  }
};

document.addEventListener('DOMContentLoaded', () => I18N.init());
