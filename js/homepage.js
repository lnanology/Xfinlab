(function () {
  const MARKETS = {
    tw: {
      label: '台灣',
      placeholder: '搜尋台股代號，例如 2330',
      symbols: ['2330', '0050', '2317', '2454', '2881'],
      assets: [
        { symbol: '2330', name: '台積電', change: '+1.24%', up: true },
        { symbol: '0050', name: '元大台灣50', change: '+0.68%', up: true },
        { symbol: '2317', name: '鴻海', change: '-0.32%', up: false },
        { symbol: '2454', name: '聯發科', change: '+2.10%', up: true }
      ]
    },
    hk: {
      label: '香港',
      placeholder: '搜尋港股代號，例如 700',
      symbols: ['700', '9988', '3690', '1810', '941'],
      assets: [
        { symbol: '700', name: '騰訊', change: '+0.82%', up: true },
        { symbol: '9988', name: '阿里巴巴', change: '+1.05%', up: true },
        { symbol: '3690', name: '美團', change: '-0.45%', up: false },
        { symbol: '1810', name: '小米', change: '+0.91%', up: true }
      ]
    },
    us: {
      label: '美國',
      placeholder: '搜尋美股代號，例如 NVDA',
      symbols: ['NVDA', 'TSLA', 'SPY', 'AAPL', 'MSFT'],
      assets: [
        { symbol: 'NVDA', name: 'NVIDIA', change: '+2.31%', up: true },
        { symbol: 'TSLA', name: 'Tesla', change: '-0.88%', up: false },
        { symbol: 'SPY', name: 'S&P 500 ETF', change: '+0.33%', up: true },
        { symbol: 'AAPL', name: 'Apple', change: '+1.24%', up: true }
      ]
    }
  };

  const GLOBAL_ASSETS = [
    { symbol: 'BTC', name: 'Bitcoin', change: '+2.31%', up: true },
    { symbol: 'ETH', name: 'Ethereum', change: '-1.12%', up: false },
    { symbol: 'XAU', name: 'Gold', change: '+0.21%', up: true },
    { symbol: 'EUR/USD', name: 'Euro / USD', change: '+0.08%', up: true },
    { symbol: 'HSI', name: '恒生指數', change: '+0.67%', up: true },
    { symbol: 'N225', name: '日經225', change: '+0.45%', up: true }
  ];

  const TOP_RESEARCHED = [
    { rank: 1, symbol: 'NVDA', meta: 'AI Market Research · 12,840 次', heat: 98 },
    { rank: 2, symbol: '700', meta: 'Event Intelligence · 9,210 次', heat: 91 },
    { rank: 3, symbol: '2330', meta: 'Chart Research · 8,540 次', heat: 87 },
    { rank: 4, symbol: 'TSLA', meta: 'Strategy Lab · 7,920 次', heat: 82 },
    { rank: 5, symbol: 'SPY', meta: 'Risk Radar · 6,430 次', heat: 76 },
    { rank: 6, symbol: '9988', meta: 'News Intelligence · 5,880 次', heat: 71 },
    { rank: 7, symbol: 'AAPL', meta: 'Company Compare · 5,210 次', heat: 68 },
    { rank: 8, symbol: 'BTC', meta: 'Fund Flow · 4,960 次', heat: 64 },
    { rank: 9, symbol: '0050', meta: 'Portfolio Research · 4,320 次', heat: 58 },
    { rank: 10, symbol: 'MSFT', meta: 'Decision Lab · 3,890 次', heat: 52 }
  ];

  let currentMarket = 'hk';

  function renderQuickSymbols() {
    const wrap = document.getElementById('quickSymbols');
    const input = document.getElementById('heroSearch');
    if (!wrap || !input) return;
    const m = MARKETS[currentMarket];
    input.placeholder = m.placeholder;
    wrap.innerHTML = m.symbols.map(function (s) {
      return '<button type="button" class="quick-chip" data-symbol="' + s + '">' + s + '</button>';
    }).join('');
    wrap.querySelectorAll('.quick-chip').forEach(function (btn) {
      btn.addEventListener('click', function () {
        input.value = btn.dataset.symbol;
        submitSearch();
      });
    });
  }

  function renderDiscovery(mode) {
    const grid = document.getElementById('discoveryGrid');
    if (!grid) return;
    const list = mode === 'global' ? GLOBAL_ASSETS : MARKETS[currentMarket].assets;
    grid.innerHTML = list.map(function (a) {
      return (
        '<a href="ai-analysis.html?symbol=' + encodeURIComponent(a.symbol) + '" class="asset-card">' +
        '<div class="asset-symbol">' + a.symbol + '</div>' +
        '<div class="asset-name">' + a.name + '</div>' +
        '<div class="asset-change ' + (a.up ? 'up' : 'down') + '">' + a.change + '</div>' +
        '</a>'
      );
    }).join('');
  }

  function renderTop10() {
    const list = document.getElementById('top10List');
    if (!list) return;
    list.innerHTML = TOP_RESEARCHED.map(function (item) {
      return (
        '<a href="ai-analysis.html?symbol=' + encodeURIComponent(item.symbol) + '" class="rank-item">' +
        '<span class="rank-num">' + item.rank + '</span>' +
        '<div class="rank-info"><div class="rank-symbol">' + item.symbol + '</div>' +
        '<div class="rank-meta">' + item.meta + '</div></div>' +
        '<div class="rank-bar"><div class="rank-fill" style="width:' + item.heat + '%"></div></div>' +
        '</a>'
      );
    }).join('');
  }

  function submitSearch() {
    const input = document.getElementById('heroSearch');
    const symbol = (input && input.value.trim()) || MARKETS[currentMarket].symbols[0];
    window.location.href = 'ai-analysis.html?symbol=' + encodeURIComponent(symbol) + '&market=' + currentMarket;
  }

  function initMarketTabs() {
    document.querySelectorAll('.market-tab').forEach(function (tab) {
      tab.addEventListener('click', function () {
        currentMarket = tab.dataset.market;
        document.querySelectorAll('.market-tab').forEach(function (t) {
          t.classList.toggle('active', t.dataset.market === currentMarket);
        });
        renderQuickSymbols();
        const activeDiscovery = document.querySelector('.discovery-tab.active');
        if (activeDiscovery && activeDiscovery.dataset.mode === 'local') {
          renderDiscovery('local');
        }
      });
    });
  }

  function initDiscoveryTabs() {
    document.querySelectorAll('.discovery-tab').forEach(function (tab) {
      tab.addEventListener('click', function () {
        document.querySelectorAll('.discovery-tab').forEach(function (t) {
          t.classList.toggle('active', t === tab);
        });
        renderDiscovery(tab.dataset.mode);
      });
    });
  }

  function initSearch() {
    const form = document.getElementById('heroSearchForm');
    if (form) {
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        submitSearch();
      });
    }
  }

  function initFaq() {
    document.querySelectorAll('.faq-q').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var item = btn.closest('.faq-item');
        var open = item.classList.contains('open');
        document.querySelectorAll('.faq-item').forEach(function (i) { i.classList.remove('open'); });
        if (!open) item.classList.add('open');
      });
    });
  }

  function initFadeUp() {
    document.querySelectorAll('.fade-up').forEach(function (el) {
      new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
          if (e.isIntersecting) e.target.classList.add('visible');
        });
      }, { threshold: 0.1 }).observe(el);
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    renderQuickSymbols();
    renderDiscovery('local');
    renderTop10();
    initMarketTabs();
    initDiscoveryTabs();
    initSearch();
    initFaq();
    initFadeUp();
  });

  window.handleWaitlistSubmit = function (e) {
    e.preventDefault();
    var msg = document.getElementById('form-msg');
    if (msg) {
      msg.style.color = 'var(--accent-blue)';
      msg.textContent = '✓ 已收到！我們會盡快聯絡你。';
    }
    var input = document.getElementById('email-input');
    if (input) input.value = '';
  };
})();
