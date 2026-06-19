const API = window.location.origin;
let token = localStorage.getItem('token');
let currentUser = JSON.parse(localStorage.getItem('user') || 'null');
let catalogPage = 1;
let catalogQuery = '';
let hasMoreCatalog = true;
let refreshTimer = null;
let catalogAbortController = null;
let catalogObserver = null;
let dlSearchQuery = '';          // 2.5: search/filter in Downloads
let dlStatusFilter = '';         // status filter for downloads
let dlSortBy = 'created_at';     // 2.5: sort by field
let dlSortOrder = 'desc';        // 2.5: sort order
let _completedNotify = new Set(JSON.parse(localStorage.getItem('_completedNotify') || '[]')); // 2.3: track notified completed ids
function _saveCompletedNotify() { try { localStorage.setItem('_completedNotify', JSON.stringify([..._completedNotify])); } catch(_) {} }

if (!token) { window.location.href = '/login'; throw new Error('redirect'); }

function initIcons() {
  document.querySelectorAll('[class*="icon-"]').forEach(el => {
    const name = el.textContent.trim();
    const cls = el.className;
    const size = cls.includes('icon-sm') ? 16 : cls.includes('icon-lg') ? 32 : 20;
    el.outerHTML = svg(name, size);
  });
}
initIcons();

// Set tab icons after init
document.querySelectorAll('.dl-tab').forEach(tab => {
  const name = tab.dataset.tab === 'catalog' ? 'compass' : 'list';
  tab.innerHTML = svg(name, 14) + ' ' + tab.textContent.trim();
});

const $ = (id) => document.getElementById(id);
const catalogSearch = $('catalogSearch');
const catalogResults = $('catalogResults');
const downloadList = $('downloadList');
const refreshBtn = $('refreshCatalog');
const userMenuBtn = $('userMenuBtn');
const userDropdown = $('userDropdown');
const logoutBtn = $('logoutBtn');

if (currentUser) {
  userMenuBtn.textContent = (currentUser.display_name || currentUser.username)[0].toUpperCase();
  const header = document.getElementById('userDropdownHeader');
  if (header) header.textContent = currentUser.display_name || currentUser.username;
}
userMenuBtn.addEventListener('click', () => userDropdown.classList.toggle('show'));
document.addEventListener('click', (e) => { if (!e.target.closest('.user-menu')) userDropdown.classList.remove('show'); });
logoutBtn.addEventListener('click', () => { localStorage.removeItem('token'); localStorage.removeItem('user'); window.location.href = '/login'; });

async function api(path, opts = {}) {
  const headers = { ...opts.headers };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  try {
    const r = await fetch(API + path, { ...opts, headers });
    if (r.status === 401) { localStorage.removeItem('token'); window.location.href = '/login'; }
    return r;
  } catch (e) {
    if (e.name !== 'AbortError') console.warn('API fetch failed:', path, e);
    throw e;
  }
}

function svg(name, size = 16) {
  const paths = {
    'compass': '<path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm-5.5-2.5l7.51-3.49L17.5 6.5 9.99 9.99 6.5 17.5zm5.5-6.6c.61 0 1.1.49 1.1 1.1s-.49 1.1-1.1 1.1-1.1-.49-1.1-1.1.49-1.1 1.1-1.1z"/>',
    'list': '<path d="M4 6h16M4 12h16M4 18h16"/>',
    'search': '<path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>',
    'sync': '<path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>',
    'download': '<path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>',
    'info-circle': '<path d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>',
    'star': '<path d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"/>',
    'caption': '<path d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z"/>',
    'microphone': '<path d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"/>',
    'film': '<path d="M4 3a2 2 0 00-2 2v14a2 2 0 002 2h16a2 2 0 002-2V5a2 2 0 00-2-2H4zm3 2h2v2H7V5zm4 0h2v2h-2V5zm4 0h2v2h-2V5zM3 9h2v2H3V9zm4 0h2v2H7V9zm4 0h2v2h-2V9zm4 0h2v2h-2V9zM3 13h2v2H3v-2zm4 0h2v2H7v-2zm4 0h2v2h-2v-2zm4 0h2v2h-2v-2z"/>',
    'layers': '<path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>',
    'link': '<path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/>',
    'folder': '<path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>',
    'spinner': '<path d="M12 2a10 10 0 0110 10" stroke-dasharray="30 30" stroke-linecap="round"/>',
    'check-circle': '<path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>',
    'exclamation-circle': '<path d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>',
    'exclamation-triangle': '<path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"/>',
    'times': '<path d="M6 18L18 6M6 6l12 12"/>',
    'pause-circle': '<path d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z"/>',
    'trash': '<path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>',
    'sign-out': '<path d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"/>',
    'arrow-left': '<path d="M10 19l-7-7m0 0l7-7m-7 7h18"/>',
    'chevron-down': '<path d="M19 9l-7 7-7-7"/>',
    'sliders': '<path d="M21 4H3m18 8H3m18 8H3M6 2v4m6 6v4m6-6v4"/>',
    'heart': '<path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z"/>',
    'file': '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/>',
  };
  const d = paths[name] || paths['file'];
  return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`;
}

// Toast queue: keeps max 5 toasts visible, queues the rest.
const _toastQueue = [];
const _toastActive = new Set();
const TOAST_MAX_ACTIVE = 5;

function toast(msg, type = 'success', duration = 3500, actions = null) {
  const container = $('toastContainer');
  if (!container) return;
  _toastQueue.push({ msg, type, duration, actions });
  _drainToasts();
}

function _drainToasts() {
  const container = $('toastContainer');
  if (!container) return;
  while (_toastQueue.length > 0 && _toastActive.size < TOAST_MAX_ACTIVE) {
    const { msg, type, duration, actions } = _toastQueue.shift();
    _showToast(container, msg, type, duration, actions);
  }
}

function _showToast(container, msg, type, duration, actions) {
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  const icons = { success: 'check-circle', error: 'exclamation-circle', info: 'info-circle', warning: 'exclamation-triangle' };
  const iconSvg = svg(icons[type] || icons.info, 16);
  let html = `${iconSvg}<span class="toast-msg">${esc(msg)}</span>`;
  if (actions && Array.isArray(actions)) {
    html += '<span class="toast-actions">' + actions.map((a, i) =>
      `<button class="toast-action" data-action="${i}">${esc(a.label)}</button>`
    ).join('') + '</span>';
  }
  html += `<button class="toast-close" aria-label="Dismiss">×</button>`;
  t.innerHTML = html;
  // Wire up
  const remove = () => {
    if (!t.parentNode) return;
    t.style.opacity = '0';
    t.style.transform = 'translateX(60px)';
    t.style.transition = 'all 0.3s';
    setTimeout(() => {
      t.remove();
      _toastActive.delete(t);
      _drainToasts();
    }, 300);
  };
  t.querySelector('.toast-close').onclick = remove;
  if (actions) {
    t.querySelectorAll('.toast-action').forEach((btn, i) => {
      btn.onclick = () => {
        try { actions[i].handler && actions[i].handler(); } catch {}
        remove();
      };
    });
  }
  container.appendChild(t);
  _toastActive.add(t);
  // Default duration by type
  const dur = duration || (type === 'error' ? 6000 : type === 'success' ? 3500 : 4500);
  setTimeout(remove, dur);
}

function esc(str) { const d = document.createElement('div'); d.textContent = str; return d.innerHTML; }

function fmtBytes(b) {
  if (!b || b === 0) return '0 B';
  const s = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(b) / Math.log(1024));
  return `${(b / Math.pow(1024, i)).toFixed(1)} ${s[i]}`;
}

function fmtSpeed(bps) {
  if (!bps || bps === 0) return '';
  return fmtBytes(bps) + '/s';
}

function fmtTime(secs) {
  if (!secs || secs < 0 || !isFinite(secs)) return '';
  if (secs < 60) return '<1m';
  if (secs < 3600) return `${Math.floor(secs / 60)}m ${Math.floor(secs % 60)}s`;
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  return `${h}h ${m}m`;
}

// Tabs
document.querySelectorAll('.dl-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.dl-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('tabCatalog').style.display = tab.dataset.tab === 'catalog' ? 'block' : 'none';
    document.getElementById('tabActive').style.display = tab.dataset.tab === 'active-dl' ? 'block' : 'none';
    if (tab.dataset.tab === 'active-dl') loadDownloads();
    if (tab.dataset.tab === 'catalog') loadCatalog();
  });
});

// Catalog search with debounce
let searchTimeout;
const SEARCH_HISTORY_KEY = 'dl_search_history';
const MAX_HISTORY = 10;

function loadSearchHistory() {
  try { return JSON.parse(localStorage.getItem(SEARCH_HISTORY_KEY) || '[]'); } catch { return []; }
}

function saveSearchHistory(q) {
  if (!q || q.length < 2) return;
  let h = loadSearchHistory().filter(x => x !== q);
  h.unshift(q);
  if (h.length > MAX_HISTORY) h = h.slice(0, MAX_HISTORY);
  localStorage.setItem(SEARCH_HISTORY_KEY, JSON.stringify(h));
}

function showSearchHistory() {
  const h = loadSearchHistory();
  const el = document.getElementById('searchHistory');
  if (!el || h.length === 0) return;
  el.innerHTML = h.map(q => `<button class="dl-dropdown-item" data-q="${esc(q)}">${esc(q)}</button>`).join('');
  el.style.display = '';
  el.querySelectorAll('.dl-dropdown-item').forEach(btn => {
    btn.addEventListener('click', () => {
      catalogSearch.value = btn.dataset.q;
      el.style.display = 'none';
      catalogSearch.dispatchEvent(new Event('input'));
    });
  });
}

catalogSearch.addEventListener('focus', showSearchHistory);
catalogSearch.addEventListener('blur', () => setTimeout(() => {
  const el = document.getElementById('searchHistory');
  if (el) el.style.display = 'none';
}, 200));

catalogSearch.addEventListener('input', (e) => {
  clearTimeout(searchTimeout);
  if (catalogAbortController) catalogAbortController.abort();
  if (catalogObserver) { catalogObserver.disconnect(); catalogObserver = null; }
  catalogQuery = e.target.value;
  catalogPage = 1;
  hasMoreCatalog = true;
  catalogResults.innerHTML = '';
  document.getElementById('searchHistory').style.display = 'none';
  searchTimeout = setTimeout(() => {
    saveSearchHistory(catalogQuery);
    loadCatalog();
  }, 350);
});

// Filter bar
const filterVars = { type: '', yearMin: '', yearMax: '', ratingMin: 0, ratingMax: 10, sortBy: 'id', sortOrder: 'asc', favsOnly: false };

document.getElementById('toggleFiltersBtn')?.addEventListener('click', () => {
  const fb = document.getElementById('filterBar');
  fb.style.display = fb.style.display === 'none' ? '' : 'none';
});

['filterType', 'filterYearMin', 'filterYearMax', 'filterRatingMin', 'filterRatingMax', 'filterSortBy', 'filterSortOrder'].forEach(id => {
  document.getElementById(id)?.addEventListener('change', () => {
    if (catalogAbortController) catalogAbortController.abort();
    if (catalogObserver) { catalogObserver.disconnect(); catalogObserver = null; }
    catalogPage = 1;
    loadCatalog();
  });
});

document.getElementById('filterFavs')?.addEventListener('click', () => {
  filterVars.favsOnly = !filterVars.favsOnly;
  document.getElementById('filterFavs').classList.toggle('active');
  if (catalogAbortController) catalogAbortController.abort();
  if (catalogObserver) { catalogObserver.disconnect(); catalogObserver = null; }
  catalogPage = 1;
  loadCatalog();
});

async function loadCatalog() {
  if (catalogAbortController) catalogAbortController.abort();
  catalogAbortController = new AbortController();
  const signal = catalogAbortController.signal;

  if (catalogPage === 1) {
    catalogResults.innerHTML = `<div class="dl-empty">${svg('spinner', 32)}<h3>Loading catalog...</h3></div>`;
  }

  // Read filters
  const typeVal = document.getElementById('filterType')?.value || '';
  const yrMin = document.getElementById('filterYearMin')?.value || '';
  const yrMax = document.getElementById('filterYearMax')?.value || '';
  const rtMin = parseFloat(document.getElementById('filterRatingMin')?.value) || 0;
  const rtMax = parseFloat(document.getElementById('filterRatingMax')?.value) || 10;
  const sortBy = document.getElementById('filterSortBy')?.value || 'id';
  const sortOrder = document.getElementById('filterSortOrder')?.value || 'asc';
  const favsOnly = document.getElementById('filterFavs')?.classList.contains('active') || false;

  try {
    let respData;
    const params = new URLSearchParams();
    if (catalogQuery) {
      params.set('q', catalogQuery);
      respData = await (await api(`/api/catalog-search?${params}`, { signal })).json();
    } else if (favsOnly) {
      respData = await (await api('/api/favorites', { signal })).json();
      if (respData.success) respData = { success: true, entries: respData.entries, total: respData.entries.length, has_more: false };
    } else {
      params.set('page', catalogPage);
      params.set('per_page', '20');
      if (typeVal) params.set('type', typeVal);
      if (yrMin) params.set('year_min', yrMin);
      if (yrMax) params.set('year_max', yrMax);
      if (rtMin > 0) params.set('rating_min', rtMin);
      if (rtMax < 10) params.set('rating_max', rtMax);
      if (sortBy) params.set('sort_by', sortBy);
      if (sortOrder) params.set('sort_order', sortOrder);
      respData = await (await api(`/api/catalog?${params}`, { signal })).json();
    }
    if (!respData.success) throw new Error(respData.error || 'Failed to load');

    const entries = respData.entries || [];
    if (catalogPage === 1) catalogResults.innerHTML = '';

    if (entries.length === 0 && catalogPage === 1) {
      catalogResults.innerHTML = `<div class="dl-empty">${svg('compass', 32)}<h3>Nothing found</h3><p>Try refreshing the catalog from the archive, or adjust your search.</p></div>`;
      return;
    }

    const grid = catalogResults.querySelector('.dl-catalog-grid') || (() => {
      const g = document.createElement('div');
      g.className = 'dl-catalog-grid';
      catalogResults.appendChild(g);
      return g;
    })();

    entries.forEach(e => {
      const rating = e.imdb_rating ? `<span class="dl-badge rating">${svg('star', 10)} ${esc(e.imdb_rating)}</span>` : '';
      const typeBadge = e.title_type === 'series' ? 'type-series' : 'type-movie';
      const sourceBadge = e.source ? `<span class="dl-badge" style="background:var(--accent);color:#fff;font-size:0.65rem;text-transform:uppercase;">${esc(e.source)}</span>` : '';
      const links = [];
      if (e.softsub_count) links.push(`<span class="dl-badge softsub">${svg('caption', 10)} ${e.softsub_count}</span>`);
      if (e.dubbed_count) links.push(`<span class="dl-badge dubbed">${svg('microphone', 10)} ${e.dubbed_count}</span>`);
      if (e.nosub_count) links.push(`<span class="dl-badge nosub">${svg('film', 10)} ${e.nosub_count}</span>`);
      if (e.has_seasons) links.push(`<span class="dl-badge type-series">${svg('layers', 10)} Series</span>`);

      const card = document.createElement('div');
      card.className = 'dl-card';
      const coverHtml = e.cover_url
        ? `<img src="${esc(e.cover_url)}" alt="" loading="lazy" style="width:100%;height:100%;object-fit:cover;border-radius:6px;" onerror="this.style.display=\'none\'">`
        : `<div style="display:flex;align-items:center;justify-content:center;width:100%;height:100%;color:var(--text-muted);opacity:0.25;">${svg('film', 22)}</div>`;
      const isFav = (e.is_favorited || e.favorited);
      card.innerHTML = `
        <div style="display:flex;gap:12px;">
          <div class="dl-card-cover">${coverHtml}</div>
          <div style="flex:1;min-width:0;">
            <div class="dl-card-header">
              <div class="dl-card-title">${esc(e.title)} ${e.year ? `<span class="dl-card-year">(${esc(e.year)})</span>` : ''}</div>
              <span class="dl-badge ${typeBadge}">${e.title_type}</span>
            </div>
            <div class="dl-card-badges">${sourceBadge} ${rating} ${links.join('')}</div>
          </div>
        </div>
        <div class="dl-card-footer">
          <button class="btn btn-primary btn-sm show-details-btn" data-id="${e.id || ''}" data-source="${esc(e.source || '')}" data-imdb="${esc(e.imdb_code || e.imdb_id || '')}" data-title="${esc(e.title)}" style="width:100%;">
            ${svg('info-circle', 14)} View Qualities
          </button>
        </div>
        <button class="dl-card-fav${isFav ? ' favorited' : ''}" data-id="${e.id}">${svg('heart', 14)}</button>`;
      grid.appendChild(card);

      card.querySelector('.show-details-btn').addEventListener('click', () => {
        const btn = card.querySelector('.show-details-btn');
        const bid = btn.dataset.id;
        const bsrc = btn.dataset.source;
        const bimdb = btn.dataset.imdb;
        if (bid) {
          showCatalogDetail(parseInt(bid));
        } else if (bsrc && bimdb) {
          showCatalogDetail({source: bsrc, imdbCode: bimdb, title: e.title});
        }
      });
      card.querySelector('.dl-card-fav')?.addEventListener('click', async (ev) => {
        ev.stopPropagation();
        const btn = ev.currentTarget;
        const id = btn.dataset.id;
        const isFav = btn.classList.contains('favorited');
        try {
          if (isFav) {
            await api(`/api/favorites/${id}`, { method: 'DELETE' });
            btn.classList.remove('favorited');
          } else {
            await api(`/api/favorites/${id}`, { method: 'POST' });
            btn.classList.add('favorited');
          }
        } catch (_) { toast('Failed to update favorite', 'error'); }
      });
    });

    // Mark favorited cards
    if (catalogPage === 1) {
      try {
        const favResp = await api('/api/favorites/ids', { signal });
        const favData = await favResp.json();
        if (favData.success && favData.ids) {
          const favSet = new Set(favData.ids.map(Number));
          grid.querySelectorAll('.dl-card-fav').forEach(btn => {
            if (favSet.has(parseInt(btn.dataset.id))) btn.classList.add('favorited');
          });
        }
      } catch (_) {}
    }

    hasMoreCatalog = catalogQuery ? false : respData.has_more;
    document.getElementById('catalogSentinel')?.remove();
    if (catalogObserver) { catalogObserver.disconnect(); catalogObserver = null; }

    if (hasMoreCatalog) {
      const sentinel = document.createElement('div');
      sentinel.id = 'catalogSentinel';
      sentinel.style.cssText = 'height:1px;';
      catalogResults.appendChild(sentinel);
      catalogObserver = new IntersectionObserver(entries => {
        if (entries[0].isIntersecting) {
          catalogPage++;
          loadCatalog();
        }
      }, { rootMargin: '200px' });
      catalogObserver.observe(sentinel);
    }
  } catch (err) {
    if (err.name === 'AbortError') return;
    if (catalogPage === 1) {
      catalogResults.innerHTML = `<div class="dl-empty">${svg('exclamation-triangle', 32)}<h3>Error</h3><p>${esc(err.message)}</p></div>`;
    }
  }
}

async function showCatalogDetail(opts) {
  const id = typeof opts === 'number' ? opts : opts.id;
  const source = typeof opts === 'object' ? opts.source : '';
  const imdbCode = typeof opts === 'object' ? opts.imdbCode : '';
  const titleFallback = typeof opts === 'object' ? opts.title : '';
  let e;
  try {
    if (id) {
      const r = await api(`/api/catalog/${id}`);
      const d = await r.json();
      if (!d.success) return;
      e = d.entry;
    } else if (source && imdbCode) {
      const r = await api(`/api/external-detail?source=${encodeURIComponent(source)}&imdb_code=${encodeURIComponent(imdbCode)}&title=${encodeURIComponent(titleFallback)}`);
      const d = await r.json();
      if (!d.success) return;
      e = d.entry;
      e.id = 0;
    } else {
      return;
    }

    let html = `<div class="dl-detail-overlay" style="position:fixed;top:0;left:0;width:100%;height:100%;z-index:3000;background:rgba(0,0,0,0.85);backdrop-filter:blur(8px);overflow-y:auto;padding:20px;animation:fadeIn 0.2s ease;">
      <div style="max-width:600px;margin:40px auto;">
        <div class="dl-card" style="border-color:var(--glass-border-hover);padding:24px;">
          <div style="display:flex;gap:16px;margin-bottom:16px;">
            <div style="flex-shrink:0;width:100px;height:150px;border-radius:8px;overflow:hidden;background:var(--glass-bg);display:flex;align-items:center;justify-content:center;color:var(--text-muted);opacity:0.3;">${e.cover_url ? `<img src="${esc(e.cover_url)}" alt="" style="width:100%;height:100%;object-fit:cover;" onerror="this.style.display='none'">` : svg('film', 28)}</div>
            <div style="flex:1;min-width:0;">
              <div style="display:flex;justify-content:space-between;align-items:start;">
                <div>
                  <h3 style="font-size:1.15rem;font-weight:700;margin-bottom:4px;background:var(--accent-gradient);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;">${esc(e.title)} ${e.year ? `<span style="background:none;-webkit-text-fill-color:var(--text-muted);font-weight:400;">(${esc(e.year)})</span>` : ''}</h3>
                  <div style="display:flex;gap:8px;font-size:0.8rem;color:var(--text-muted);margin-top:6px;flex-wrap:wrap;">
                    <span class="dl-badge ${e.title_type === 'series' ? 'type-series' : 'type-movie'}">${e.title_type}</span>
                    ${e.imdb_rating ? `<span class="dl-badge rating">${svg('star', 10)} ${esc(e.imdb_rating)}</span>` : ''}
                    ${e.imdb_votes ? `<span class="dl-badge">${esc(e.imdb_votes)} votes</span>` : ''}
                  </div>
                </div>
                <button class="btn-icon close-detail" style="flex-shrink:0;width:36px;height:36px;font-size:1rem;">
                  ${svg('times', 16)}
                </button>
              </div>
            </div>
          </div>`;

    for (const [groupName, groupKey, badgeClass] of [['SoftSub', 'softsub_links', 'softsub'], ['Dubbed', 'dubbed_links', 'dubbed'], ['NoSub', 'nosub_links', 'nosub']]) {
      const links = e[groupKey] || [];
      if (links.length === 0) continue;
      html += `<div class="quality-group">
        <h4><span class="dl-badge ${badgeClass}" style="margin-right:6px;">${groupName}</span></h4>
        <div class="quality-list">`;
      links.forEach(link => {
        html += `<button class="quality-btn start-download" data-url="${esc(link.url)}" data-catalog-id="${e.id}" data-title="${esc(e.title)}" data-quality="${esc(link.label)}">
          ${svg('download', 12)} ${esc(link.label)} ${link.size ? `<span style="color:var(--text-muted);font-weight:400;">(${esc(link.size)})</span>` : ''}
        </button>`;
      });
      html += `</div></div>`;
    }

    if (e.has_seasons && e.season_info) {
      html += `<div class="quality-group" style="margin-top:18px;"><h4>${svg('layers', 14)} Seasons</h4>`;
      for (const [season, seasonLinks] of Object.entries(e.season_info)) {
        html += `<div class="season-group">
          <span class="season-label">${svg('folder', 12)} ${esc(season)}</span>
          <div class="quality-list">`;
        (seasonLinks || []).forEach(link => {
          const isSingleEp = /\.(mkv|mp4|avi|mov|webm)$/i.test(link.url);
          if (isSingleEp) {
            html += `<button class="quality-btn start-download" data-url="${esc(link.url)}" data-catalog-id="${e.id}" data-title="${esc(e.title)}" data-quality="${esc(link.label || season)}">
              ${svg('download', 12)} ${esc(link.label || season)} ${link.size ? `<span style="color:var(--text-muted);font-weight:400;">(${esc(link.size)})</span>` : ''}
            </button>`;
          } else {
            html += `<button class="quality-btn start-download" data-url="${esc(link.url)}" data-catalog-id="${e.id}" data-title="${esc(e.title)}" data-quality="${esc(link.label || season)}" data-season-page="${esc(link.url)}" data-season-label="${esc(season)}">
              ${svg('layers', 12)} ${esc(link.label || season)} ${link.size ? `<span style="color:var(--text-muted);font-weight:400;">(${esc(link.size)})</span>` : ''}
              <span style="margin-left:4px;font-size:0.7rem;opacity:0.7;">(all episodes)</span>
            </button>`;
          }
        });
        html += `</div></div>`;
      }
      html += `</div>`;
    }

    html += `</div></div></div>`;
    const wrapper = document.createElement('div');
    wrapper.innerHTML = html;
    const overlay = wrapper.firstElementChild;
    document.body.appendChild(overlay);

    overlay.querySelector('.close-detail')?.addEventListener('click', () => overlay.remove());
    overlay.addEventListener('click', (e) => {
      if (e.target === e.currentTarget) overlay.remove();
    });

    // Schedule/speed options bar
    const optDiv = document.createElement('div');
    optDiv.style.cssText = 'display:flex;gap:8px;margin-top:12px;padding:10px;background:var(--glass-bg);border-radius:10px;border:1px solid var(--glass-border);align-items:center;flex-wrap:wrap;';
    optDiv.innerHTML = `
      <label style="font-size:0.78rem;color:var(--text-muted);display:flex;align-items:center;gap:4px;flex-shrink:0;">${svg('sliders', 10)} Schedule:</label>
      <input type="datetime-local" id="schedulePicker" style="flex:1;min-width:160px;background:var(--bg);border:1px solid var(--glass-border);border-radius:20px;padding:6px 10px;font-size:0.78rem;color:var(--text);">
      <button id="clearScheduleBtn" class="btn btn-sm btn-ghost" style="font-size:0.7rem;display:none;">${svg('times', 10)} Clear</button>
      <label style="font-size:0.78rem;color:var(--text-muted);display:flex;align-items:center;gap:4px;flex-shrink:0;">
        ${svg('sliders', 10)} Speed:
        <select id="speedSelect" style="background:var(--bg);border:1px solid var(--glass-border);border-radius:20px;padding:4px 8px;font-size:0.75rem;color:var(--text);">
          <option value="0">Unlimited</option>
          <option value="51200">50 KB/s</option>
          <option value="102400">100 KB/s</option>
          <option value="512000">500 KB/s</option>
          <option value="1048576">1 MB/s</option>
          <option value="5242880">5 MB/s</option>
          <option value="10485760">10 MB/s</option>
        </select>
      </label>
    `;
    // Insert options before the close button
    const optSection = overlay.querySelector('.quality-group:last-of-type') || overlay.querySelector('h3');
    if (optSection && optSection.parentNode) {
      optSection.parentNode.insertBefore(optDiv, overlay.querySelector('.close-detail')?.closest('div')?.nextSibling || null);
    }

    overlay.querySelectorAll('.start-download').forEach(btn => {
      btn.addEventListener('click', async () => {
        // Season page link — show episode picker first
        if (btn.dataset.seasonPage) {
          showSeasonPicker(btn.dataset.seasonPage, btn.dataset.seasonLabel, btn.dataset.title, parseInt(btn.dataset.catalogId), btn.dataset.quality);
          return;
        }
        btn.disabled = true; btn.innerHTML = `${svg('spinner', 12)} Queuing...`;
        const scheduleVal = document.getElementById('schedulePicker')?.value || '';
        const speedVal = document.getElementById('speedSelect')?.value || '';
        try {
          const params = new URLSearchParams({
            url: btn.dataset.url,
            catalog_id: btn.dataset.catalogId,
            quality_label: btn.dataset.quality,
            is_season: 'false',
            season_name: ''
          });
          if (scheduleVal) params.set('scheduled_at', new Date(scheduleVal).toISOString());
          if (speedVal && speedVal !== '0') params.set('speed_limit', speedVal);
          if (btn.dataset.catalogId === '0' || !btn.dataset.catalogId) {
            params.set('title', btn.dataset.title || 'Unknown');
          }
          const r = await api('/api/downloads?' + params.toString(), { method: 'POST' });
          const d = await r.json();
          if (d.success) {
            toast(`1 file queued \u2014 ${btn.dataset.title}`, 'success');
            overlay.remove();
          } else {
            toast(d.detail || 'Failed to queue', 'error');
            btn.disabled = false; btn.innerHTML = `${svg('download', 12)} ${esc(btn.dataset.quality)}`;
          }
        } catch (err) {
          toast('Connection error \u2014 try again', 'error');
          btn.disabled = false; btn.innerHTML = `${svg('download', 12)} ${esc(btn.dataset.quality)}`;
        }
      });
    });
  } catch (err) {
    toast('Failed to load details', 'error');
  }
}

const _dlItemMap = new Map();
let _dlFirstLoad = true;

function _makeDlItemHtml(dl) {
  const activeStatuses = new Set(['downloading', 'active', 'waiting', 'queued']);
  const displayStatus = activeStatuses.has(dl.status) ? 'downloading' : dl.status;
  const pct = Math.round(dl.progress_pct || 0);
  const speed = dl.speed ? fmtSpeed(parseInt(dl.speed) || 0) : '';
  const total = dl.total_bytes ? fmtBytes(parseInt(dl.total_bytes) || 0) : '';
  const done = dl.downloaded_bytes ? fmtBytes(parseInt(dl.downloaded_bytes) || 0) : '';
  const speedNum = parseInt(dl.speed) || 0;
  const totalNum = parseInt(dl.total_bytes) || 0;
  const remaining = totalNum - (parseInt(dl.downloaded_bytes) || 0);
  const eta = speedNum > 0 ? fmtTime(remaining / speedNum) : '';
  let statusClass = 'status-downloading';
  let statusIcon = 'spinner';
  if (displayStatus === 'completed') { statusClass = 'status-completed'; statusIcon = 'check-circle'; }
  else if (displayStatus === 'error' || displayStatus === 'interrupted') { statusClass = 'status-error'; statusIcon = 'exclamation-circle'; }
  else if (displayStatus === 'paused') { statusClass = 'status-paused'; statusIcon = 'pause-circle'; }
  const speedLimitLabel = dl.speed_limit && parseInt(dl.speed_limit) > 0 ? fmtBytes(parseInt(dl.speed_limit)) + '/s' : '';
  const scheduleInfo = dl.scheduled_at ? `<span style="color:var(--text-muted);font-size:0.72rem;">Scheduled: ${new Date(dl.scheduled_at).toLocaleString()}</span>` : '';
  return {
    displayStatus, pct, speed, total, done, eta, statusClass, statusIcon, html: `
    <div class="dl-item" id="dl-item-${dl.id}" data-dl-id="${dl.id}">
    <div class="dl-item-top">
      ${dl.cover_url ? `<div class="dl-item-cover"><img src="${esc(dl.cover_url)}" alt="" style="width:48px;height:72px;object-fit:cover;border-radius:4px;flex-shrink:0;" onerror="this.style.display='none'"></div>` : ''}
      <div class="dl-item-info">
        <div class="dl-item-title">${esc(dl.title)}</div>
        <div class="dl-item-subtitle">${esc(dl.file_name)} ${dl.quality_label ? `<span style="color:var(--text-secondary);">\u00b7 ${esc(dl.quality_label)}</span>` : ''}</div>
        ${dl.retry_count > 0 ? `<span style="color:var(--text-muted);font-size:0.7rem;">Retry #${dl.retry_count}</span>` : ''}
        ${scheduleInfo}
      </div>
      <span class="dl-badge ${statusClass}">${svg(statusIcon, 12)} ${displayStatus}</span>
    </div>
    ${displayStatus === 'downloading' || displayStatus === 'paused' ? `
      <div class="dl-progress-wrap">
        <div class="dl-progress">
          <div class="dl-progress-bar ${displayStatus === 'completed' ? 'complete' : ''}" style="width:${pct}%"></div>
        </div>
        <div class="dl-progress-info">
          <span class="dl-progress-pct">${pct}%</span>
          <span>${done}/${total}</span>
          ${speed ? `<span>${speed}</span>` : ''}
          ${eta ? `<span>ETA: ${eta}</span>` : ''}
          ${speedLimitLabel ? `<span style="color:var(--text-muted);font-size:0.72rem;">Limit: ${speedLimitLabel}</span>` : ''}
        </div>
      </div>
    ` : displayStatus === 'completed' ? `
      <div class="dl-progress-wrap">
        <div class="dl-progress">
          <div class="dl-progress-bar complete" style="width:100%"></div>
        </div>
        <div class="dl-progress-info">
          <span style="color:var(--success);">${svg('check-circle', 12)} Complete</span>
          <span>${total}</span>
        </div>
      </div>
    ` : displayStatus === 'error' || displayStatus === 'interrupted' ? `
      <div class="dl-progress-wrap">
        <div class="dl-progress-info">
          <span style="color:var(--danger);">${esc(dl.error_message || 'Download failed')}</span>
        </div>
      </div>
    ` : displayStatus === 'queued' && dl.scheduled_at ? `
      <div class="dl-progress-wrap">
        <div class="dl-progress-info">
          <span style="color:var(--text-muted);">Scheduled for ${new Date(dl.scheduled_at).toLocaleString()}</span>
        </div>
      </div>
    ` : ''}
    ${displayStatus === 'downloading' ? `
      <div class="dl-actions">
        <button class="btn btn-secondary btn-sm pause-dl" data-id="${dl.id}">${svg('pause-circle', 12)} Pause</button>
        <button class="btn btn-secondary btn-sm speed-dl" data-id="${dl.id}" data-speed="${esc(dl.speed_limit || '0')}" style="font-size:0.7rem;">${svg('sliders', 10)} Speed</button>
        <button class="btn btn-danger btn-sm cancel-dl" data-id="${dl.id}">${svg('times', 12)} Cancel</button>
      </div>
    ` : displayStatus === 'paused' ? `
      <div class="dl-actions">
        <button class="btn btn-secondary btn-sm resume-dl" data-id="${dl.id}">${svg('download', 12)} Resume</button>
        <button class="btn btn-danger btn-sm cancel-dl" data-id="${dl.id}">${svg('times', 12)} Cancel</button>
      </div>
    ` : (displayStatus === 'error' || displayStatus === 'interrupted') ? `
      <div class="dl-actions">
        <button class="btn btn-secondary btn-sm restart-dl" data-id="${dl.id}">${svg('sync', 12)} Restart</button>
        <button class="btn btn-danger btn-sm remove-dl" data-id="${dl.id}">${svg('trash', 12)} Remove</button>
        <label style="font-size:0.75rem;color:var(--text-muted);display:flex;align-items:center;gap:4px;cursor:pointer;"><input type="checkbox" class="delete-file-cb" checked> Delete file</label>
      </div>
    ` : displayStatus === 'completed' ? `
      <div class="dl-actions">
        <button class="btn btn-secondary btn-sm open-dl" data-id="${dl.id}">${svg('folder-open', 12)} Open in Files</button>
        <button class="btn btn-secondary btn-sm play-dl" data-url="${esc(dl.dest_path || '')}" data-filename="${esc(dl.file_name || '')}" data-title="${esc(dl.title)}">${svg('play', 12)} Play</button>
        <button class="btn btn-secondary btn-sm restart-dl" data-id="${dl.id}">${svg('sync', 12)} Restart</button>
        <button class="btn btn-danger btn-sm remove-dl" data-id="${dl.id}">${svg('trash', 12)} Remove</button>
        <label style="font-size:0.75rem;color:var(--text-muted);display:flex;align-items:center;gap:4px;cursor:pointer;"><input type="checkbox" class="delete-file-cb" checked> Delete file</label>
      </div>
    ` : displayStatus === 'queued' ? `
      <div class="dl-actions">
        <button class="btn btn-danger btn-sm remove-dl" data-id="${dl.id}">${svg('trash', 12)} Remove</button>
      </div>
    ` : ''}
    </div>`
  };
}

function _attachDlEvents(item, dl) {
  item.querySelector('.pause-dl')?.addEventListener('click', async () => {
    try { await api(`/api/downloads/${dl.id}/pause`, { method: 'PUT' }); toast('Paused', 'info'); } catch (e) { toast('Failed to pause', 'error'); }
  });
  item.querySelector('.resume-dl')?.addEventListener('click', async () => {
    try { await api(`/api/downloads/${dl.id}/resume`, { method: 'PUT' }); toast('Resumed', 'info'); } catch (e) { toast('Failed to resume', 'error'); }
  });
  item.querySelector('.cancel-dl')?.addEventListener('click', async () => {
    if (!confirm('Cancel this download?')) return;
    const cb = item.querySelector('.delete-file-cb');
    const delFiles = cb ? cb.checked : false;
    try { await api(`/api/downloads/${dl.id}?delete_files=${delFiles}`, { method: 'DELETE' }); toast('Cancelled', 'info'); } catch (e) { toast('Failed', 'error'); }
  });
  item.querySelector('.remove-dl')?.addEventListener('click', async () => {
    const cb = item.querySelector('.delete-file-cb');
    const delFiles = cb ? cb.checked : false;
    if (!confirm(delFiles ? 'Remove and delete file?' : 'Remove from list?')) return;
    try { await api(`/api/downloads/${dl.id}?delete_files=${delFiles}`, { method: 'DELETE' }); toast('Removed', 'info'); } catch (e) { toast('Failed', 'error'); }
  });
  item.querySelector('.open-dl')?.addEventListener('click', () => {
    const path = dl.dest_path || '';
    const subpath = path.replace(/\\/g, '/').split('/').slice(0, -1).join('/');
    window.location.href = subpath ? '/?path=' + encodeURIComponent(subpath) : '/';
  });
  item.querySelector('.play-dl')?.addEventListener('click', () => {
    const url = item.querySelector('.play-dl')?.dataset.url;
    const filename = item.querySelector('.play-dl')?.dataset.filename;
    const title = item.querySelector('.play-dl')?.dataset.title;
    const filePath = filename ? (url ? url + '/' + filename : filename) : url;
    if (filePath && typeof Player !== 'undefined' && Player.play) {
      Player.play('/api/stream?path=' + encodeURIComponent(filePath), title, '');
    }
  });
  item.querySelector('.restart-dl')?.addEventListener('click', async () => {
    try {
      const r = await api(`/api/downloads/${dl.id}/restart`, { method: 'POST' });
      const d = await r.json();
      toast(d.success ? 'Restarted' : (d.detail || 'Failed'), d.success ? 'info' : 'error');
    } catch (e) { toast('Failed', 'error'); }
  });
  // Speed limit dialog
  item.querySelector('.speed-dl')?.addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    const currentSpeed = btn.dataset.speed || '0';
    const newSpeed = prompt('Speed limit (KB/s, 0 = unlimited):', currentSpeed === '0' ? '0' : Math.round(parseInt(currentSpeed) / 1024).toString());
    if (newSpeed === null) return;
    const speedBytes = (parseInt(newSpeed) || 0) * 1024;
    try {
      await api(`/api/downloads/${dl.id}/speed-limit?speed=${speedBytes}`, { method: 'PUT' });
      toast(speedBytes > 0 ? `Speed limited to ${newSpeed} KB/s` : 'Speed unlimited', 'info');
    } catch (e) { toast('Failed to set speed limit', 'error'); }
  });
}

async function loadDownloads() {
  try {
    const r = await api('/api/downloads');
    const d = await r.json();
    if (!d.success) throw new Error(d.error || 'Failed to load');

    if (d.downloads.length === 0) {
      downloadList.innerHTML = `<div class="dl-empty">${svg('download', 32)}<h3>No downloads yet</h3><p>Browse the catalog, pick a title, and queue your first download.</p></div>`;
      _dlItemMap.clear();
      return;
    }

    // 2.3: Check for newly completed downloads and notify
    d.downloads.forEach(dl => {
      if (dl.status === 'completed' && !_completedNotify.has(dl.id)) {
        _completedNotify.add(dl.id);
        _saveCompletedNotify();
        if ('Notification' in window && Notification.permission === 'granted') {
          new Notification('Download Complete', {
            body: `${dl.title} — ${dl.file_name}`,
            icon: '/static/icon-192.png',
          });
        }
        toast(`Download complete: ${dl.title}`, 'success', 5000);
      }
    });

    // 2.5: Filter + sort downloads list
    let filtered = d.downloads;
    if (dlSearchQuery) {
      const q = dlSearchQuery.toLowerCase();
      filtered = filtered.filter(x =>
        (x.title && x.title.toLowerCase().includes(q)) ||
        (x.file_name && x.file_name.toLowerCase().includes(q)) ||
        (x.quality_label && x.quality_label.toLowerCase().includes(q))
      );
    }
    // Sort
    filtered.sort((a, b) => {
      let va, vb;
      if (dlSortBy === 'title') { va = a.title || ''; vb = b.title || ''; return dlSortOrder === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va); }
      if (dlSortBy === 'progress') { va = a.progress_pct || 0; vb = b.progress_pct || 0; }
      if (dlSortBy === 'size') { va = parseInt(a.total_bytes) || 0; vb = parseInt(b.total_bytes) || 0; }
      // default: created_at
      va = a.created_at || ''; vb = b.created_at || '';
      return dlSortOrder === 'asc' ? (va > vb ? 1 : -1) : (va > vb ? -1 : 1);
    });

    // Update summary in-place
    const activeCount = filtered.filter(x => x.status === 'downloading' || x.status === 'active' || x.status === 'waiting' || x.status === 'queued').length;
    const pausedCount = filtered.filter(x => x.status === 'paused').length;
    const errorCount = filtered.filter(x => x.status === 'error' || x.status === 'interrupted').length;
    const totalBytes = filtered.reduce((s, x) => s + (parseInt(x.total_bytes) || 0), 0);
    let summary = downloadList.querySelector('.dl-summary');
    if (!summary) {
      summary = document.createElement('div');
      summary.className = 'dl-summary';
      downloadList.prepend(summary);
    }
    summary.style.cssText = 'display:flex;align-items:center;gap:8px;padding:8px 12px;margin-bottom:8px;flex-wrap:wrap;font-size:0.82rem;';
    summary.innerHTML = `
      <span style="color:var(--text-muted);">${filtered.length} downloads</span>
      <span style="color:var(--text-secondary);font-weight:500;">${totalBytes ? fmtBytes(totalBytes) : ''}</span>
      <span style="flex:1;"></span>
      ${errorCount > 0 ? `<button class="btn btn-sm btn-ghost retry-all-btn" style="font-size:0.78rem;color:var(--danger);">${svg('sync', 12)} Retry All (${errorCount})</button>` : ''}
      ${activeCount > 0 ? `<button class="btn btn-sm btn-ghost pause-all-btn" style="font-size:0.78rem;">${svg('pause-circle', 12)} Pause All (${activeCount})</button>` : ''}
      ${pausedCount > 0 ? `<button class="btn btn-sm btn-ghost resume-all-btn" style="font-size:0.78rem;">${svg('download', 12)} Resume All (${pausedCount})</button>` : ''}
      ${(activeCount > 0 || pausedCount > 0) ? `<button class="btn btn-sm btn-danger cancel-all-btn" style="font-size:0.78rem;">${svg('times', 12)} Cancel All</button>` : ''}
    `;
    summary.querySelector('.pause-all-btn')?.addEventListener('click', async () => { await api('/api/downloads/batch/pause', { method: 'POST' }); toast('Paused all', 'info'); });
    summary.querySelector('.resume-all-btn')?.addEventListener('click', async () => { await api('/api/downloads/batch/resume', { method: 'POST' }); toast('Resumed all', 'info'); });
    summary.querySelector('.cancel-all-btn')?.addEventListener('click', async () => {
      if (!confirm('Cancel ALL active/paused downloads?')) return;
      await api('/api/downloads/batch/cancel', { method: 'POST' }); toast('Cancelled all', 'info');
    });
    summary.querySelector('.retry-all-btn')?.addEventListener('click', async () => {
      const r = await api('/api/downloads/batch/retry', { method: 'POST' });
      const rd = await r.json();
      if (rd.success) toast(`Retrying ${rd.retried} failed downloads...`, 'info');
    });

    // Get or create search bar for downloads
    let dlSearchBar = downloadList.querySelector('.dl-search-bar');
    if (!dlSearchBar) {
      dlSearchBar = document.createElement('div');
      dlSearchBar.className = 'dl-search-bar';
      dlSearchBar.style.cssText = 'display:flex;gap:6px;margin:0 0 8px 0;align-items:center;';
      dlSearchBar.innerHTML = `
        <input type="search" id="dlSearchInput" placeholder="Filter downloads..." style="flex:1;background:var(--glass-bg);border:1px solid var(--glass-border);border-radius:40px;padding:6px 14px;font-size:0.82rem;color:var(--text);">
        <select id="dlSortBy" style="background:var(--glass-bg);border:1px solid var(--glass-border);border-radius:40px;padding:6px 10px;font-size:0.78rem;color:var(--text);">
          <option value="created_at" ${dlSortBy==='created_at'?'selected':''}>Date</option>
          <option value="title" ${dlSortBy==='title'?'selected':''}>Name</option>
          <option value="progress" ${dlSortBy==='progress'?'selected':''}>Progress</option>
          <option value="size" ${dlSortBy==='size'?'selected':''}>Size</option>
        </select>
        <select id="dlSortOrder" style="background:var(--glass-bg);border:1px solid var(--glass-border);border-radius:40px;padding:6px 10px;font-size:0.78rem;color:var(--text);">
          <option value="desc" ${dlSortOrder==='desc'?'selected':''}>Newest</option>
          <option value="asc" ${dlSortOrder==='asc'?'selected':''}>Oldest</option>
        </select>
      `;
      downloadList.insertBefore(dlSearchBar, downloadList.querySelector('.dl-list') || summary.nextSibling);
      const inp = dlSearchBar.querySelector('#dlSearchInput');
      inp.addEventListener('input', function() { dlSearchQuery = this.value; loadDownloads(); });
      dlSearchBar.querySelector('#dlSortBy').addEventListener('change', function() { dlSortBy = this.value; loadDownloads(); });
      dlSearchBar.querySelector('#dlSortOrder').addEventListener('change', function() { dlSortOrder = this.value; loadDownloads(); });
    }
    dlSearchBar.querySelector('#dlSearchInput').value = dlSearchQuery;

    // Get or create list container
    let list = downloadList.querySelector('.dl-list');
    if (!list) {
      list = document.createElement('div');
      list.className = 'dl-list';
      downloadList.appendChild(list);
    }

    const seen = new Set();
    filtered.forEach(dl => {
      seen.add(dl.id);
      let item = _dlItemMap.get(dl.id);
      const info = _makeDlItemHtml(dl);
      if (!item) {
        item = document.createElement('div');
        item.className = 'dl-item';
        item.dataset.dlId = dl.id;
        item.innerHTML = info.html;
        _attachDlEvents(item, dl);
        _dlItemMap.set(dl.id, item);
        list.appendChild(item);
      } else {
        // In-place update: replace progress + actions, keep header/cover
        const oldWrap = item.querySelector('.dl-progress-wrap');
        const oldActions = item.querySelector('.dl-actions');
        const oldBadge = item.querySelector('.dl-badge.status-downloading, .dl-badge.status-completed, .dl-badge.status-error, .dl-badge.status-paused');
        // Parse new HTML
        const tmp = document.createElement('div');
        tmp.innerHTML = info.html;
        const newWrap = tmp.querySelector('.dl-progress-wrap');
        const newActions = tmp.querySelector('.dl-actions');
        const newBadge = tmp.querySelector('.dl-badge');
        if (newBadge && oldBadge) oldBadge.outerHTML = newBadge.outerHTML;
        if (newWrap && oldWrap) oldWrap.replaceWith(newWrap);
        else if (newWrap && !oldWrap) item.insertBefore(newWrap, item.querySelector('.dl-actions'));
        else if (!newWrap && oldWrap) oldWrap.remove();
        if (newActions && oldActions) oldActions.replaceWith(newActions);
        else if (newActions && !oldActions) item.appendChild(newActions);
        else if (!newActions && oldActions) oldActions.remove();
        // Re-attach events
        _attachDlEvents(item, dl);
      }
    });

    // Remove stale items
    for (const [id, el] of _dlItemMap) {
      if (!seen.has(id)) {
        el.remove();
        _dlItemMap.delete(id);
      }
    }

    if (_dlFirstLoad) {
      _dlFirstLoad = false;
    }
  } catch (err) {
    if (_dlItemMap.size === 0) {
      downloadList.innerHTML = `<div class="dl-empty">${svg('exclamation-triangle', 32)}<h3>Error</h3><p>${esc(err.message)}</p></div>`;
    }
  }
}

async function showSeasonPicker(seasonUrl, seasonLabel, title, catalogId, qualityLabel) {
  try {
    const r = await api('/api/season-preview?url=' + encodeURIComponent(seasonUrl));
    const d = await r.json();
    if (!d.success || !d.files.length) {
      toast('No episodes found on that page', 'error');
      return;
    }

    const html = `<div class="dl-detail-overlay" style="position:fixed;top:0;left:0;width:100%;height:100%;z-index:3000;background:rgba(0,0,0,0.85);backdrop-filter:blur(8px);overflow-y:auto;padding:20px;animation:fadeIn 0.2s ease;">
      <div style="max-width:560px;margin:40px auto;">
        <div class="dl-card" style="border-color:var(--glass-border-hover);padding:20px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
            <h3 style="font-size:1rem;font-weight:700;background:var(--accent-gradient);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;">${esc(title)} \u2014 ${esc(seasonLabel)}</h3>
            <span style="color:var(--text-muted);font-size:0.8rem;">${d.count} episodes</span>
          </div>
          <div id="episodeList" style="max-height:380px;overflow-y:auto;margin-bottom:12px;"></div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;">
            <button id="dlAllEpisodes" class="btn btn-primary" style="flex:1;">
              ${svg('download', 14)} Download All (${d.count})
            </button>
            <button id="dlSelectedEpisodes" class="btn btn-secondary" style="flex:1;" disabled>
              ${svg('download', 14)} Download Selected (0)
            </button>
            <button class="btn btn-ghost close-picker" style="flex:0 0 auto;">${svg('times', 14)}</button>
          </div>
        </div>
      </div>
    </div>`;

    const wrapper = document.createElement('div');
    wrapper.innerHTML = html;
    const overlay = wrapper.firstElementChild;
    document.body.appendChild(overlay);

    const epList = document.getElementById('episodeList');
    d.files.forEach((f, i) => {
      const item = document.createElement('div');
      item.style.cssText = 'display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid var(--glass-border);';
      item.innerHTML = `
        <input type="checkbox" id="ep_${i}" value="${i}" style="accent-color:var(--accent);width:16px;height:16px;cursor:pointer;">
        <label for="ep_${i}" style="flex:1;cursor:pointer;font-size:0.88rem;">${esc(f.name)}</label>
        <span style="color:var(--text-muted);font-size:0.78rem;">${f.size || ''}</span>
      `;
      epList.appendChild(item);
    });

    const checkboxes = epList.querySelectorAll('input[type=checkbox]');
    const dlSelectedBtn = document.getElementById('dlSelectedEpisodes');
    const dlAllBtn = document.getElementById('dlAllEpisodes');

    function updateSelectedCount() {
      const checked = epList.querySelectorAll('input[type=checkbox]:checked').length;
      dlSelectedBtn.disabled = checked === 0;
      dlSelectedBtn.innerHTML = `${svg('download', 14)} Download Selected (${checked})`;
    }
    checkboxes.forEach(cb => cb.addEventListener('change', updateSelectedCount));

    overlay.querySelector('.close-picker')?.addEventListener('click', () => overlay.remove());
    overlay.addEventListener('click', (e) => { if (e.target === e.currentTarget) overlay.remove(); });

    dlAllBtn.addEventListener('click', async () => {
      dlAllBtn.disabled = true; dlSelectedBtn.disabled = true;
      try {
        const params = new URLSearchParams({
          url: seasonUrl,
          catalog_id: catalogId,
          quality_label: qualityLabel,
          is_season: 'true',
          season_name: seasonLabel
        });
        const r = await api('/api/downloads?' + params.toString(), { method: 'POST' });
        const d = await r.json();
        overlay.remove();
        if (d.success) {
          toast(`${d.count} episodes queued \u2014 ${title}`, 'success');
        } else {
          toast(d.detail || 'Failed to queue', 'error');
        }
      } catch (_) {
        overlay.remove();
        toast('Failed to queue episodes', 'error');
      }
    });

    dlSelectedBtn.addEventListener('click', async () => {
      const selected = [];
      checkboxes.forEach(cb => { if (cb.checked) selected.push(d.files[parseInt(cb.value)]); });
      if (selected.length === 0) return;
      dlAllBtn.disabled = true; dlSelectedBtn.disabled = true;
      let successCount = 0;
      const total = selected.length;
      for (const f of selected) {
        try {
          const params = new URLSearchParams({
            url: f.url,
            catalog_id: catalogId,
            quality_label: qualityLabel,
            is_season: 'false',
            season_name: ''
          });
          const r = await api('/api/downloads?' + params.toString(), { method: 'POST' });
          const d = await r.json();
          if (d.success) successCount++;
        } catch (_) {}
      }
      overlay.remove();
      toast(`${successCount}/${total} episodes queued \u2014 ${title}`, successCount > 0 ? 'success' : 'error');
    });
  } catch (err) {
    toast('Failed to load season episodes', 'error');
  }
}

refreshBtn.addEventListener('click', async () => {
  refreshBtn.disabled = true; refreshBtn.innerHTML = `${svg('spinner', 14)} Refreshing...`;
  try {
    const r = await api('/api/catalog/refresh', { method: 'POST' });
    const d = await r.json();
    if (d.success) {
      toast('Catalog refreshed successfully', 'success');
      catalogPage = 1;
      hasMoreCatalog = true;
      catalogQuery = '';
      catalogSearch.value = '';
      loadCatalog();
    } else {
      toast(d.detail || 'Refresh failed \u2014 check server logs', 'error');
    }
  } catch (err) {
    toast('Failed to connect to server', 'error');
  }
  refreshBtn.disabled = false; refreshBtn.innerHTML = `${svg('sync', 14)} Refresh`;
});

// Request notification permission on user interaction
document.addEventListener('click', () => {
  if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission();
  }
}, { once: true });

// SSE for real-time download progress
let _dlEventSource = null;
function connectDownloadSSE() {
  if (_dlEventSource) { _dlEventSource.close(); }
  if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null; }
  const token = localStorage.getItem('token');
  const url = API + '/api/downloads/sse' + (token ? '?token=' + encodeURIComponent(token) : '');
  _dlEventSource = new EventSource(url);
  _dlEventSource.addEventListener('progress', (e) => {
    try {
      const d = JSON.parse(e.data);
      if (d.downloads) { _renderDownloads(d.downloads); }
    } catch(_) {}
  });
  _dlEventSource.addEventListener('completed', (e) => {
    try {
      const d = JSON.parse(e.data);
      // Desktop notification (only when tab not focused)
      if (document.hidden && 'Notification' in window && Notification.permission === 'granted') {
        try { new Notification('Download Complete', { body: d.title, icon: '/static/icon-192.png', tag: 'dl-' + d.id }); } catch {}
      }
      // In-page toast with "Open" / "Play" actions
      const playUrl = d.file_name ? `/api/stream?path=${encodeURIComponent(d.dest_path ? d.dest_path + '/' + d.file_name : d.file_name)}&transcode=true` : null;
      const actions = [];
      if (playUrl) actions.push({ label: 'Play', handler: () => { window.location.href = '/player?url=' + encodeURIComponent(playUrl) + '&title=' + encodeURIComponent(d.title || d.file_name); } });
      if (d.id) actions.push({ label: 'Open', handler: () => { window.location.href = '/downloads'; } });
      toast('Download complete: ' + d.title, 'success', 6000, actions.length ? actions : null);
    } catch(_) {}
  });
  _dlEventSource.addEventListener('failed', (e) => {
    try {
      const d = JSON.parse(e.data);
      toast('Download failed: ' + d.title + (d.error ? ' — ' + d.error : ''), 'error', 8000);
    } catch(_) {}
  });
  _dlEventSource.onerror = () => {
    // Fall back to polling if SSE dies
    if (_dlEventSource) _dlEventSource.close();
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(() => {
      if (document.getElementById('tabActive').style.display !== 'none') loadDownloads();
    }, 4000);
  };
}
// Pre-seed _completedNotify so first SSE batch doesn't re-notify all completed downloads
(async function seedCompletedNotify() {
  try {
    const r = await api('/api/downloads');
    if (r.ok) {
      const data = await r.json();
      const list = Array.isArray(data) ? data : (data && Array.isArray(data.downloads) ? data.downloads : []);
      list.forEach(dl => { if (dl.status === 'completed') { _completedNotify.add(dl.id); _saveCompletedNotify(); } });
    }
  } catch(_) {}
  connectDownloadSSE();
})();

// Helper to render downloads from SSE data
function _renderDownloads(downloads) {
  if (downloads.length === 0) {
    downloadList.innerHTML = `<div class="dl-empty">${svg('download', 32)}<h3>No downloads yet</h3><p>Browse the catalog, pick a title, and queue your first download.</p></div>`;
    _dlItemMap.clear();
    return;
  }
  downloads.forEach(dl => {
    if (dl.status === 'completed' && !_completedNotify.has(dl.id)) {
      _completedNotify.add(dl.id);
      _saveCompletedNotify();
      if ('Notification' in window && Notification.permission === 'granted') {
        new Notification('Download Complete', { body: dl.title + ' — ' + dl.file_name, icon: '/static/icon-192.png' });
      }
      toast('Download complete: ' + dl.title, 'success', 5000);
    }
  });
  let filtered = downloads;
  if (dlSearchQuery) {
    const q = dlSearchQuery.toLowerCase();
    filtered = filtered.filter(x =>
      (x.title && x.title.toLowerCase().includes(q)) ||
      (x.file_name && x.file_name.toLowerCase().includes(q)) ||
      (x.quality_label && x.quality_label.toLowerCase().includes(q))
    );
  }
  filtered.sort((a, b) => {
    let va, vb;
    if (dlSortBy === 'title') { va = a.title || ''; vb = b.title || ''; return dlSortOrder === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va); }
    if (dlSortBy === 'progress') { va = a.progress_pct || 0; vb = b.progress_pct || 0; }
    if (dlSortBy === 'size') { va = parseInt(a.total_bytes) || 0; vb = parseInt(b.total_bytes) || 0; }
    va = a.created_at || ''; vb = b.created_at || '';
    return dlSortOrder === 'asc' ? (va > vb ? 1 : -1) : (va > vb ? -1 : 1);
  });
  const activeCount = filtered.filter(x => x.status === 'downloading' || x.status === 'active' || x.status === 'waiting' || x.status === 'queued').length;
  const pausedCount = filtered.filter(x => x.status === 'paused').length;
  let statHtml = `<span class="dl-stat">${filtered.length} total</span>`;
  if (activeCount) statHtml += `<span class="dl-stat dl-stat-active">${activeCount} active</span>`;
  if (pausedCount) statHtml += `<span class="dl-stat dl-stat-paused">${pausedCount} paused</span>`;
  const dlStats = document.getElementById('dlStats');
  if (dlStats) dlStats.innerHTML = statHtml;
  const list = document.getElementById('tabActive');
  if (!list) return;
  const items = list.querySelector('.dl-items') || (() => {
    const c = document.createElement('div'); c.className = 'dl-items'; list.appendChild(c); return c;
  })();
  items.innerHTML = filtered.map(dl => _makeDlItemHtml(dl).html).join('');
  filtered.forEach(dl => {
    const el = document.getElementById('dl-item-' + dl.id);
    if (el) _attachDlEvents(el, dl);
  });
}

// Enrichment indicator
let enrichBadge = null;
async function pollEnrichment() {
  try {
    const r = await api('/api/enrich/status');
    const d = await r.json();
    if (d.success && d.running) {
      if (!enrichBadge) {
        enrichBadge = document.createElement('span');
        enrichBadge.className = 'dl-enrich-badge';
        document.querySelector('.dl-toolbar')?.appendChild(enrichBadge);
      }
      enrichBadge.innerHTML = `${svg('spinner', 10)} Enriching ${d.done}/${d.total}...`;
    } else {
      if (enrichBadge) { enrichBadge.remove(); enrichBadge = null; }
      if (d.last_error) console.warn('Enrichment error:', d.last_error);
    }
  } catch (_) {}
}
setInterval(pollEnrichment, 5000);
pollEnrichment();

// ============ MANUAL DOWNLOAD ============

let manualDlModal = null;

document.getElementById('manualDownloadBtn')?.addEventListener('click', () => {
  if (manualDlModal) { manualDlModal.remove(); manualDlModal = null; }
  const overlay = document.createElement('div');
  overlay.className = 'dl-detail-overlay';
  overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;z-index:3000;background:rgba(0,0,0,0.85);backdrop-filter:blur(8px);overflow-y:auto;padding:20px;display:flex;align-items:center;justify-content:center;';
  overlay.innerHTML = `
    <div style="max-width:480px;width:100%;margin:auto;">
      <div class="dl-card" style="border-color:var(--glass-border-hover);padding:24px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
          <h3 style="font-size:1.05rem;font-weight:700;background:var(--accent-gradient);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;">${svg('link', 16)} Manual Download</h3>
          <button class="btn-icon close-modal" style="flex-shrink:0;width:36px;height:36px;">${svg('times', 16)}</button>
        </div>
        <div style="margin-bottom:14px;">
          <label style="display:block;font-size:0.82rem;color:var(--text-muted);margin-bottom:6px;">Paste a direct download link (MKV, MP4, etc.)</label>
          <input type="url" id="manualUrl" placeholder="https://example.com/video.mkv" style="width:100%;background:var(--bg);border:1px solid var(--glass-border);border-radius:10px;padding:10px 14px;font-size:0.88rem;color:var(--text);">
        </div>
        <div style="margin-bottom:14px;">
          <label style="display:block;font-size:0.82rem;color:var(--text-muted);margin-bottom:6px;">Title (optional)</label>
          <input type="text" id="manualTitle" placeholder="My Video" style="width:100%;background:var(--bg);border:1px solid var(--glass-border);border-radius:10px;padding:10px 14px;font-size:0.88rem;color:var(--text);">
        </div>
        <button id="submitManualDl" class="btn btn-primary" style="width:100%;">
          ${svg('download', 14)} Queue Download
        </button>
        <div id="manualDlResult" style="margin-top:10px;font-size:0.82rem;display:none;"></div>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  manualDlModal = overlay;

  overlay.querySelector('.close-modal')?.addEventListener('click', () => { overlay.remove(); manualDlModal = null; });
  overlay.addEventListener('click', (e) => { if (e.target === e.currentTarget) { overlay.remove(); manualDlModal = null; } });

  const submitBtn = overlay.querySelector('#submitManualDl');
  const urlInput = overlay.querySelector('#manualUrl');
  const titleInput = overlay.querySelector('#manualTitle');
  const resultDiv = overlay.querySelector('#manualDlResult');

  submitBtn.addEventListener('click', async () => {
    const url = urlInput.value.trim();
    const title = titleInput.value.trim() || 'Manual Download';
    if (!url) {
      resultDiv.style.display = 'block';
      resultDiv.style.color = 'var(--danger)';
      resultDiv.textContent = 'Please enter a URL';
      return;
    }
    submitBtn.disabled = true;
    submitBtn.innerHTML = `${svg('spinner', 14)} Queuing...`;
    resultDiv.style.display = 'none';
    try {
      const r = await api('/api/downloads/manual', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, title })
      });
      let d;
      try { d = await r.json(); } catch (_) { d = {}; }
      if (r.ok && d.success) {
        resultDiv.style.display = 'block';
        resultDiv.style.color = 'var(--success)';
        resultDiv.textContent = 'Queued successfully!';
        setTimeout(() => { if (manualDlModal) { manualDlModal.remove(); manualDlModal = null; } }, 1000);
        toast(`Queued: ${title}`, 'success');
        if (document.getElementById('tabActive').style.display !== 'none') loadDownloads();
      } else {
        let errMsg = 'Failed to queue';
        if (d.detail) errMsg = Array.isArray(d.detail) ? d.detail.map(x => x.msg || JSON.stringify(x)).join('; ') : d.detail;
        else if (d.error) errMsg = d.error;
        resultDiv.style.display = 'block';
        resultDiv.style.color = 'var(--danger)';
        resultDiv.textContent = errMsg;
        submitBtn.disabled = false;
        submitBtn.innerHTML = `${svg('download', 14)} Queue Download`;
      }
    } catch (err) {
      resultDiv.style.display = 'block';
      resultDiv.style.color = 'var(--danger)';
      resultDiv.textContent = 'Connection error';
      submitBtn.disabled = false;
      submitBtn.innerHTML = `${svg('download', 14)} Queue Download`;
    }
  });
});

// ============ DOWNLOADS TAB SEARCH/FILTER/SORT ============

document.getElementById('downloadSearch')?.addEventListener('input', function() {
  dlSearchQuery = this.value;
  loadDownloads();
});

document.getElementById('dlStatusFilter')?.addEventListener('change', function() {
  dlStatusFilter = this.value;
  loadDownloads();
});

document.getElementById('dlSortBy')?.addEventListener('change', function() {
  dlSortBy = this.value;
  loadDownloads();
});

document.getElementById('refreshDownloadsBtn')?.addEventListener('click', loadDownloads);

// Override loadDownloads to use search/stats endpoints and update stats bar
const _origLoadDownloads = loadDownloads;
loadDownloads = async function() {
  try {
    const r = await api('/api/downloads');
    const d = await r.json();
    if (!d.success) throw new Error(d.error || 'Failed to load');

    // Stats bar
    try {
      const sr = await api('/api/downloads/stats');
      const sd = await sr.json();
      if (sd.success) {
        const s = sd.stats;
        const statsBar = document.getElementById('dlStatsBar');
        if (statsBar) {
          let html = '';
          if (s.has_active) html += `<span style="color:var(--accent);font-weight:600;">${s.downloading} active</span>`;
          if (s.paused) html += `<span style="color:var(--text-secondary);">${s.paused} paused</span>`;
          if (s.completed) html += `<span style="color:var(--success);">${s.completed} done</span>`;
          if (s.failed) html += `<span style="color:var(--danger);">${s.failed} failed</span>`;
          if (s.queued) html += `<span style="color:var(--text-muted);">${s.queued} queued</span>`;
          if (s.total_bytes) html += `<span style="color:var(--text-muted);">${fmtBytes(s.total_bytes)} total</span>`;
          if (s.progress_pct > 0) html += `<span style="color:var(--accent);">${s.progress_pct}% overall</span>`;
          statsBar.innerHTML = html || '<span style="color:var(--text-muted);font-size:0.82rem;">No downloads yet</span>';
        }
      }
    } catch (_) {}

    // Filter + sort
    let filtered = d.downloads;
    if (dlSearchQuery) {
      const q = dlSearchQuery.toLowerCase();
      filtered = filtered.filter(x =>
        (x.title && x.title.toLowerCase().includes(q)) ||
        (x.file_name && x.file_name.toLowerCase().includes(q)) ||
        (x.quality_label && x.quality_label.toLowerCase().includes(q))
      );
    }
    if (dlStatusFilter) {
      const statuses = dlStatusFilter.split(',');
      filtered = filtered.filter(x => statuses.includes(x.status));
    }
    filtered.sort((a, b) => {
      let va, vb;
      if (dlSortBy === 'title') { va = a.title || ''; vb = b.title || ''; return dlSortOrder === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va); }
      if (dlSortBy === 'progress_pct') { va = a.progress_pct || 0; vb = b.progress_pct || 0; }
      if (dlSortBy === 'status') { va = a.status || ''; vb = b.status || ''; return dlSortOrder === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va); }
      va = a.created_at || ''; vb = b.created_at || '';
      return dlSortOrder === 'asc' ? (va > vb ? 1 : -1) : (va > vb ? -1 : 1);
    });

    if (filtered.length === 0) {
      downloadList.innerHTML = `<div class="dl-empty">${svg('download', 32)}<h3>No downloads yet</h3><p>Browse the catalog, pick a title, and queue your first download.</p></div>`;
      _dlItemMap.clear();
      return;
    }

    // Notify completed
    filtered.forEach(dl => {
      if (dl.status === 'completed' && !_completedNotify.has(dl.id)) {
        _completedNotify.add(dl.id);
        _saveCompletedNotify();
        if ('Notification' in window && Notification.permission === 'granted') {
          new Notification('Download Complete', { body: `${dl.title} — ${dl.file_name}`, icon: '/static/icon-192.png' });
        }
        toast(`Download complete: ${dl.title}`, 'success', 5000);
      }
    });

    // Summary bar
    const activeCount = filtered.filter(x => x.status === 'downloading' || x.status === 'active').length;
    const pausedCount = filtered.filter(x => x.status === 'paused').length;
    const errorCount = filtered.filter(x => x.status === 'error' || x.status === 'interrupted').length;
    const totalBytes = filtered.reduce((s, x) => s + (parseInt(x.total_bytes) || 0), 0);
    let summary = downloadList.querySelector('.dl-summary');
    if (!summary) {
      summary = document.createElement('div');
      summary.className = 'dl-summary';
      downloadList.prepend(summary);
    }
    summary.style.cssText = 'display:flex;align-items:center;gap:8px;padding:8px 12px;margin-bottom:8px;flex-wrap:wrap;font-size:0.82rem;';
    summary.innerHTML = `
      <span style="color:var(--text-muted);">${filtered.length} downloads</span>
      <span style="color:var(--text-secondary);font-weight:500;">${totalBytes ? fmtBytes(totalBytes) : ''}</span>
      <span style="flex:1;"></span>
      ${errorCount > 0 ? `<button class="btn btn-sm btn-ghost retry-all-btn" style="font-size:0.78rem;color:var(--danger);">${svg('sync', 12)} Retry All (${errorCount})</button>` : ''}
      ${activeCount > 0 ? `<button class="btn btn-sm btn-ghost pause-all-btn" style="font-size:0.78rem;">${svg('pause-circle', 12)} Pause All (${activeCount})</button>` : ''}
      ${pausedCount > 0 ? `<button class="btn btn-sm btn-ghost resume-all-btn" style="font-size:0.78rem;">${svg('download', 12)} Resume All (${pausedCount})</button>` : ''}
      ${(activeCount > 0 || pausedCount > 0) ? `<button class="btn btn-sm btn-danger cancel-all-btn" style="font-size:0.78rem;">${svg('times', 12)} Cancel All</button>` : ''}
    `;
    summary.querySelector('.pause-all-btn')?.addEventListener('click', async () => { await api('/api/downloads/batch/pause', { method: 'POST' }); toast('Paused all', 'info'); });
    summary.querySelector('.resume-all-btn')?.addEventListener('click', async () => { await api('/api/downloads/batch/resume', { method: 'POST' }); toast('Resumed all', 'info'); });
    summary.querySelector('.cancel-all-btn')?.addEventListener('click', async () => {
      if (!confirm('Cancel ALL active/paused downloads?')) return;
      await api('/api/downloads/batch/cancel', { method: 'POST' }); toast('Cancelled all', 'info');
    });
    summary.querySelector('.retry-all-btn')?.addEventListener('click', async () => {
      const r = await api('/api/downloads/batch/retry', { method: 'POST' });
      const rd = await r.json();
      if (rd.success) toast(`Retrying ${rd.retried} failed downloads...`, 'info');
    });

    // Render items
    const seen = new Set();
    filtered.forEach(dl => {
      seen.add(dl.id);
      let item = _dlItemMap.get(dl.id);
      const info = _makeDlItemHtml(dl);
      if (!item) {
        item = document.createElement('div');
        item.className = 'dl-item';
        item.dataset.dlId = dl.id;
        item.innerHTML = info.html;
        _attachDlEvents(item, dl);
        _dlItemMap.set(dl.id, item);
        downloadList.appendChild(item);
      } else {
        const oldWrap = item.querySelector('.dl-progress-wrap');
        const oldActions = item.querySelector('.dl-actions');
        const oldBadge = item.querySelector('.dl-badge.status-downloading, .dl-badge.status-completed, .dl-badge.status-error, .dl-badge.status-paused');
        const tmp = document.createElement('div');
        tmp.innerHTML = info.html;
        const newWrap = tmp.querySelector('.dl-progress-wrap');
        const newActions = tmp.querySelector('.dl-actions');
        const newBadge = tmp.querySelector('.dl-badge');
        if (newBadge && oldBadge) oldBadge.outerHTML = newBadge.outerHTML;
        if (newWrap && oldWrap) oldWrap.replaceWith(newWrap);
        else if (newWrap && !oldWrap) item.insertBefore(newWrap, item.querySelector('.dl-actions'));
        else if (!newWrap && oldWrap) oldWrap.remove();
        if (newActions && oldActions) oldActions.replaceWith(newActions);
        else if (newActions && !oldActions) item.appendChild(newActions);
        else if (!newActions && oldActions) oldActions.remove();
        _attachDlEvents(item, dl);
      }
    });

    // Remove stale items
    for (const [id, el] of _dlItemMap) {
      if (!seen.has(id)) {
        el.remove();
        _dlItemMap.delete(id);
      }
    }

    if (_dlFirstLoad) _dlFirstLoad = false;
  } catch (err) {
    if (_dlItemMap.size === 0) {
      downloadList.innerHTML = `<div class="dl-empty">${svg('exclamation-triangle', 32)}<h3>Error</h3><p>${esc(err.message)}</p></div>`;
    }
  }
};

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
  if (e.ctrlKey && e.key === 'k') {
    e.preventDefault();
    const searchInput = document.getElementById('downloadSearch');
    if (searchInput) searchInput.focus();
  }
  if (e.key === 'Escape') {
    if (manualDlModal) { manualDlModal.remove(); manualDlModal = null; }
  }
});

loadCatalog();
