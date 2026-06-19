// Library page — Netflix-style browsing
// Self-contained: provides its own svg() helper since /static/script.js
// is not loaded on this page.

const API = window.location.origin;
let token = localStorage.getItem('token');
let currentUser = JSON.parse(localStorage.getItem('user') || 'null');
let watchlistIds = new Set();
let libRows = [];
let libGenres = [];
let heroEntry = null;

if (!token) { window.location.href = '/login'; throw new Error('redirect'); }

const _svgPaths = {
  'play': '<polygon points="6,4 20,12 6,20" fill="currentColor"/>',
  'info-circle': '<circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M12 8v4M12 16h.01" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  'plus': '<path d="M12 4v16M4 12h16" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
  'check': '<path d="M5 13l4 4L19 7" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
  'search': '<circle cx="11" cy="11" r="7" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M21 21l-5-5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  'spinner': '<path d="M12 2a10 10 0 0110 10" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/>',
  'times': '<path d="M6 18L18 6M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
  'download': '<path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
  'chevron-right': '<path d="M9 5l7 7-7 7" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
  'chevron-left': '<path d="M15 19l-7-7 7-7" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
  'film': '<path d="M4 3h16a2 2 0 012 2v14a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2zm3 2h2v2H7V5zm4 0h2v2h-2V5zm4 0h2v2h-2V5zM3 9h2v2H3V9zm4 0h2v2H7V9zm4 0h2v2h-2V9zm4 0h2v2h-2V9zM3 13h2v2H3v-2zm4 0h2v2H7v-2zm4 0h2v2h-2v-2zm4 0h2v2h-2v-2z" stroke="currentColor" stroke-width="1.5" fill="none"/>',
  'star': '<path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" fill="currentColor"/>',
  'heart': '<path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z" stroke="currentColor" stroke-width="1.8" fill="none"/>',
  'folder': '<path d="M2 6a2 2 0 012-2h4l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" stroke="currentColor" stroke-width="1.5" fill="none"/>',
  'user': '<circle cx="12" cy="8" r="4" fill="currentColor"/><path d="M4 20c0-4 4-7 8-7s8 3 8 7" stroke="currentColor" stroke-width="1.5" fill="none"/>',
};

function svg(name, size = 16) {
  const path = _svgPaths[name];
  if (!path) return `<svg width="${size}" height="${size}" viewBox="0 0 24 24"></svg>`;
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">${path}</svg>`;
}

function initIcons() {
  document.querySelectorAll('[data-icon]').forEach(el => {
    const name = el.dataset.icon;
    const size = el.dataset.iconSize ? parseInt(el.dataset.iconSize) : 16;
    el.innerHTML = svg(name, size);
  });
  document.querySelectorAll('[class*="icon-"]').forEach(el => {
    if (el.querySelector('svg')) return;
    const name = el.textContent.trim();
    if (!name || name.includes('/')) return;
    const cls = el.className;
    const size = cls.includes('icon-sm') ? 16 : cls.includes('icon-lg') ? 24 : 16;
    el.innerHTML = svg(name, size);
  });
}

// ── API helpers ──
async function api(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` };
  try {
    const r = await fetch(API + path, { ...opts, headers: { ...headers, ...(opts.headers || {}) } });
    if (!r.ok) {
      let msg = `HTTP ${r.status}`;
      try { const d = await r.json(); msg = d.detail || d.message || msg; } catch {}
      throw new Error(msg);
    }
    return await r.json();
  } catch (e) {
    if (e && e.message && e.message.includes('401')) {
      // token rejected — back to login
      localStorage.removeItem('token');
      window.location.href = '/login';
    }
    throw e;
  }
}

function toast(msg, type = 'info', duration = 3500) {
  const container = document.getElementById('toastContainer');
  if (!container) return;
  const t = document.createElement('div');
  t.className = `toast toast-${type}`;
  t.innerHTML = `<span class="toast-icon">${svg(type === 'error' ? 'times' : type === 'success' ? 'check' : 'info-circle', 14)}</span><span class="toast-msg">${msg}</span>`;
  container.appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; t.style.transform = 'translateX(60px)'; t.style.transition = 'all 0.3s'; setTimeout(() => t.remove(), 300); }, duration);
}

// ── Poster rendering with fallback chain ──
function posterUrl(item, size = 'w300') {
  if (item.cover_url) return item.cover_url;
  if (item.poster_url) return item.poster_url;
  if (item.imdb_code) return `/api/covers/${item.imdb_code}.jpg`;
  return '';
}

function backdropUrl(item) {
  if (item.backdrop_url) return item.backdrop_url;
  // For backdrops, don't fall back to the small cover image (looks bad stretched).
  // Return a dark gradient placeholder so the hero still looks good.
  if (item.cover_url && item.cover_url.includes('tmdb') && item.cover_url.includes('original')) {
    return item.cover_url;
  }
  return '';
}

function placeholderPoster() {
  return 'data:image/svg+xml;base64,' + btoa('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 300"><rect width="200" height="300" fill="#1a1a24"/><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="#444" font-family="sans-serif" font-size="14">No poster</text></svg>');
}

function escapeHtml(s) {
  if (!s) return '';
  return s.replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
}

// ── Card renderers ──
function makeCard(item) {
  const card = document.createElement('div');
  card.className = 'lib-card';
  card.dataset.id = item.id || item.tmdb_id || '';
  card.dataset.imdb = item.imdb_code || '';
  card.dataset.title = item.title || '';
  card.dataset.tmdb = item.tmdb_id || '';

  const poster = posterUrl(item) || placeholderPoster();
  const title = escapeHtml(item.title || 'Untitled');
  const year = item.year || '';
  const rating = item.imdb_rating || item.rating || '';
  const genres = (item.genres || []).slice(0, 3).join(' • ');

  card.innerHTML = `
    <div class="lib-card-poster">
      <img loading="lazy" src="${poster}" alt="${title}" onerror="this.onerror=null;this.src='${placeholderPoster()}'">
      <div class="lib-card-overlay">
        <button class="lib-card-play" title="Play">${svg('play')}</button>
        <button class="lib-card-add ${watchlistIds.has(parseInt(item.id)) ? 'is-added' : ''}" title="Watchlist">${svg(watchlistIds.has(parseInt(item.id)) ? 'check' : 'plus')}</button>
      </div>
      ${rating ? `<div class="lib-card-rating">${svg('star')}${rating}</div>` : ''}
    </div>
    <div class="lib-card-info">
      <div class="lib-card-title">${title}</div>
      <div class="lib-card-meta">${[year, genres].filter(Boolean).join(' • ')}</div>
    </div>
  `;
  // Wire up actions
  card.setAttribute('tabindex', '0');
  card.addEventListener('click', (e) => {
    if (e.target.closest('.lib-card-add')) {
      e.stopPropagation();
      toggleWatchlist(item);
    } else {
      openDetail(item);
    }
  });
  return card;
}

function makeContinueCard(item) {
  const card = document.createElement('div');
  card.className = 'lib-continue-card';
  const pct = item.progress_pct || 0;
  card.innerHTML = `
    <div class="lib-continue-thumb">
      ${svg('play')}
      <div class="lib-continue-bar"><div class="lib-continue-fill" style="width:${pct}%"></div></div>
    </div>
    <div class="lib-continue-info">
      <div class="lib-continue-title">${escapeHtml(item.name)}</div>
      <div class="lib-continue-meta">${pct > 0 ? Math.round(pct) + '% watched' : 'Continue'}</div>
    </div>
  `;
  card.addEventListener('click', () => {
    const ext = (item.name || '').split('.').pop().toLowerCase();
    const isTranscode = !['mp4', 'webm', 'ogv'].includes(ext);
    const url = isTranscode
      ? `/api/stream?path=${encodeURIComponent(item.path)}&transcode=true&t=${item.position || 0}`
      : `/api/stream?path=${encodeURIComponent(item.path)}&t=${item.position || 0}`;
    window.location.href = `/player?url=${encodeURIComponent(url)}&title=${encodeURIComponent(item.name)}&t=${item.position || 0}`;
  });
  return card;
}

function makeRow(row) {
  const wrap = document.createElement('div');
  wrap.className = 'lib-row';
  if (row.type === 'continue') {
    const h = document.createElement('h2');
    h.className = 'lib-row-title';
    h.textContent = row.title;
    wrap.appendChild(h);
    const scroller = document.createElement('div');
    scroller.className = 'lib-row-scroller lib-row-continue';
    row.items.forEach(it => scroller.appendChild(makeContinueCard(it)));
    wrap.appendChild(scroller);
    requestAnimationFrame(() => {
      if (scroller.scrollWidth > scroller.clientWidth + 10) wrap.classList.add('has-overflow');
    });
  } else if (row.type === 'hero') {
    // Hero is rendered separately
    return null;
  } else {
    const h = document.createElement('h2');
    h.className = 'lib-row-title';
    h.textContent = row.title;
    wrap.appendChild(h);
    const scroller = document.createElement('div');
    scroller.className = 'lib-row-scroller';
    row.items.forEach(it => scroller.appendChild(makeCard(it)));
    const left = document.createElement('button');
    left.className = 'lib-scroll-btn lib-scroll-left';
    left.innerHTML = svg('chevron-left', 24);
    left.setAttribute('data-icon', 'chevron-left');
    left.setAttribute('data-icon-size', '24');
    left.addEventListener('click', () => scroller.scrollBy({ left: -scroller.clientWidth * 0.8, behavior: 'smooth' }));
    const right = document.createElement('button');
    right.className = 'lib-scroll-btn lib-scroll-right';
    right.innerHTML = svg('chevron-right', 24);
    right.setAttribute('data-icon', 'chevron-right');
    right.setAttribute('data-icon-size', '24');
    right.addEventListener('click', () => scroller.scrollBy({ left: scroller.clientWidth * 0.8, behavior: 'smooth' }));
    wrap.appendChild(left);
    wrap.appendChild(right);
    wrap.appendChild(scroller);
    // Detect overflow for scroll hint gradient
    requestAnimationFrame(() => {
      if (scroller.scrollWidth > scroller.clientWidth + 10) {
        wrap.classList.add('has-overflow');
      }
    });
  }
  return wrap;
}

function showSkeletons(count = 6) {
  const container = document.getElementById('libRows');
  if (!container) return;
  const skel = r => `<div class="lib-row"><h2 class="lib-row-title" style="background:var(--glass-bg);border-radius:4px;width:${Math.random()*100+100}px;height:20px;margin-bottom:10px;opacity:0.5"></h2><div class="lib-row-scroller">${Array(r).fill('<div class="lib-card"><div class="lib-card-poster" style="background:linear-gradient(135deg,var(--glass-bg),rgba(255,255,255,0.05));animation:skeleton-pulse 1.5s infinite"><div class="lib-card-info" style="padding:8px 0"><div class="lib-card-title" style="background:var(--glass-bg);border-radius:3px;height:14px;width:80%;margin-bottom:4px"></div><div style="background:var(--glass-bg);border-radius:3px;height:12px;width:50%"></div></div></div></div>').join('')}</div></div>`;
  container.innerHTML = skel(count) + skel(count);
}

function renderRows(rows) {
  const container = document.getElementById('libRows');
  if (!container) return;
  container.innerHTML = '';
  if (!rows || !rows.length) {
    container.innerHTML = '<div class="lib-empty"><p>No items in library yet.</p><p>Add entries from the catalog to populate the library.</p></div>';
    return;
  }
  rows.forEach(row => {
    if (row.type === 'hero') {
      return;
    }
    const el = makeRow(row);
    if (el) container.appendChild(el);
  });
}

function renderHero(entry) {
  if (!entry) {
    document.getElementById('libHero').style.display = 'none';
    return;
  }
  document.getElementById('libHero').style.display = '';
  const bUrl = backdropUrl(entry);
  if (bUrl) {
    document.getElementById('libHeroBg').style.backgroundImage = `url(${bUrl})`;
    let link = document.getElementById('libHeroPreload');
    if (!link) {
      link = document.createElement('link');
      link.rel = 'preload';
      link.id = 'libHeroPreload';
      link.as = 'image';
      link.href = bUrl;
      document.head.appendChild(link);
    } else {
      link.href = bUrl;
    }
  } else {
    const heroBg = document.getElementById('libHeroBg');
    heroBg.style.backgroundImage = '';
    const link = document.getElementById('libHeroPreload');
    if (link) link.remove();
    const poster = posterUrl(entry);
    if (poster) {
      heroBg.style.background = 'linear-gradient(135deg, #1a1a2e, #16213e)';
      const img = new Image();
      img.crossOrigin = 'anonymous';
      img.src = poster;
      img.onload = () => {
        try {
          const c = document.createElement('canvas');
          c.width = 100; c.height = 100;
          const ctx = c.getContext('2d');
          ctx.drawImage(img, 0, 0, 100, 100);
          const d = ctx.getImageData(0, 0, 100, 100).data;
          const bins = {};
          for (let i = 0; i < d.length; i += 16) {
            const r = Math.round(d[i]/32)*32, g = Math.round(d[i+1]/32)*32, b = Math.round(d[i+2]/32)*32;
            const key = r+','+g+','+b;
            bins[key] = (bins[key]||0) + d[i+3];
          }
          const sorted = Object.entries(bins).sort((a,b)=>b[1]-a[1]).slice(0,2);
          if (sorted.length >= 2) {
            const c1 = sorted[0][0].split(',').map(Number);
            const c2 = sorted[1][0].split(',').map(Number);
            heroBg.style.background = `linear-gradient(135deg, rgb(${c1}), rgb(${c2}))`;
          }
        } catch(_) {}
      };
    }
  }
  document.getElementById('libHeroTitle').textContent = entry.title || '';
  document.getElementById('libHeroTagline').textContent = entry.tagline || '';
  document.getElementById('libHeroOverview').textContent = entry.overview || '';
  const rating = entry.imdb_rating || '';
  const matchPct = rating ? Math.round(parseFloat(rating) * 10) : '';
  document.getElementById('libHeroMatch').textContent = matchPct ? `${matchPct}% Match` : '';
  document.getElementById('libHeroRating').textContent = rating ? `${rating} ★` : '';
  document.getElementById('libHeroYear').textContent = entry.year || '';
  const runtime = entry.runtime_min || 0;
  document.getElementById('libHeroRuntime').textContent = runtime ? `${Math.floor(runtime / 60)}h ${runtime % 60}m` : '';

  document.getElementById('libHeroPlay').onclick = () => playEntry(entry);
  document.getElementById('libHeroInfo').onclick = () => openDetail(entry);
  document.getElementById('libHeroWatchlist').onclick = () => toggleWatchlist(entry);
  heroEntry = entry;
}

function renderGenres(genres) {
  const section = document.getElementById('libGenresSection');
  const grid = document.getElementById('libGenreGrid');
  if (!genres || !genres.length) { section.style.display = 'none'; return; }
  section.style.display = '';
  grid.innerHTML = '';
  // Take top 12
  genres.slice(0, 12).forEach(g => {
    const tile = document.createElement('a');
    tile.className = 'lib-genre-tile';
    tile.href = '#';
    tile.dataset.genre = g.name;
    tile.innerHTML = `<span>${escapeHtml(g.name)}</span><span class="lib-genre-count">${g.count}</span>`;
    tile.addEventListener('click', (e) => {
      e.preventDefault();
      openGenre(g.name);
    });
    grid.appendChild(tile);
  });
}

async function openGenre(name) {
  try {
    const data = await api(`/api/library/genre/${encodeURIComponent(name)}?per_page=30`);
    const wrap = document.createElement('div');
    wrap.className = 'lib-row';
    wrap.innerHTML = `<button class="lib-btn lib-btn-ghost lib-back-btn" id="libGenreBack">${svg('chevron-left', 14)} Back</button><h2 class="lib-row-title">${escapeHtml(name)}</h2><div class="lib-row-scroller"></div>`;
    const scroller = wrap.querySelector('.lib-row-scroller');
    (data.items || []).forEach(it => scroller.appendChild(makeCard(it)));
    const main = document.getElementById('libMain');
    main.style.display = 'none';
    document.body.appendChild(wrap);
    wrap.classList.add('lib-genre-page');
    document.getElementById('libGenreBack').addEventListener('click', () => {
      wrap.remove();
      main.style.display = '';
    });
  } catch (e) {
    toast('Failed to load genre: ' + e.message, 'error');
  }
}

// ── Detail modal ──
async function openDetail(item) {
  const modal = document.getElementById('libModal');
  const body = document.getElementById('libModalBody');
  modal.style.display = '';
  body.innerHTML = '<div class="lib-loader">' + svg('spinner', 24) + '<p>Loading...</p></div>';
  initIcons();

  let detail = null;
  if (item.id) {
    try { detail = (await api(`/api/library/detail/${item.id}`)).entry; } catch {}
  } else if (item.tmdb_id) {
    // TMDB items don't have a local catalog id — use as-is
    detail = item;
  }
  if (!detail) detail = item;

  const backdrop = backdropUrl(detail);
  const poster = posterUrl(detail);
  const title = escapeHtml(detail.title || 'Untitled');
  const year = detail.year || '';
  const rating = detail.imdb_rating || detail.rating || '';
  const overview = escapeHtml(detail.overview || '');
  const genres = (detail.genres || []).map(g => `<span class="lib-genre-chip">${escapeHtml(g)}</span>`).join('');
  const cast = (detail.cast || []).slice(0, 8);
  const castHtml = cast.length
    ? `<div class="lib-detail-cast-row">${cast.map(c => `
        <div class="lib-cast-card">
          <div class="lib-cast-avatar">${c.profile_url ? `<img src="${c.profile_url}" alt="${escapeHtml(c.name)}" loading="lazy">` : svg('user')}</div>
          <div class="lib-cast-name">${escapeHtml(c.name)}</div>
          <div class="lib-cast-character">${escapeHtml(c.character || '')}</div>
        </div>`).join('')}</div>`
    : '';
  const director = detail.director ? `<div class="lib-detail-director">Director: <b>${escapeHtml(detail.director)}</b></div>` : '';
  const runtime = detail.runtime_min ? `<span>${Math.floor(detail.runtime_min / 60)}h ${detail.runtime_min % 60}m</span>` : '';
  const inWatchlist = watchlistIds.has(parseInt(detail.id));

  const related = detail.related || [];
  const relatedHtml = related.length
    ? `<div class="lib-detail-related"><h3>More Like This</h3><div class="lib-row-scroller">${related.map(it => makeCardHtml(it)).join('')}</div></div>`
    : '';
  const tmdbRecs = detail.tmdb_recommendations || [];
  const tmdbHtml = tmdbRecs.length
    ? `<div class="lib-detail-related"><h3>TMDB Recommendations</h3><div class="lib-row-scroller">${tmdbRecs.map(makeTmdbHtml).join('')}</div></div>`
    : '';

  body.innerHTML = `
    <div class="lib-detail">
      <div class="lib-detail-hero" ${backdrop ? `style="background-image: linear-gradient(to bottom, transparent 30%, rgba(8,8,14,0.9) 100%), url(${backdrop});"` : ''}>
        <div class="lib-detail-poster">
          ${poster ? `<img src="${poster}" alt="${title}" onerror="this.onerror=null;this.src='${placeholderPoster()}'">` : ''}
        </div>
        <div class="lib-detail-header">
          <h2 class="lib-detail-title">${title}</h2>
          <div class="lib-detail-meta">
            ${rating ? `<span class="lib-detail-rating">${rating} ★</span>` : ''}
            ${year ? `<span>${year}</span>` : ''}
            ${runtime}
            ${detail.tagline ? `<span class="lib-detail-tagline">${escapeHtml(detail.tagline)}</span>` : ''}
          </div>
          <div class="lib-detail-buttons">
            <button class="lib-btn lib-btn-primary" id="libDetailPlay">${svg('play')} Play</button>
            <button class="lib-btn lib-btn-ghost" id="libDetailAdd">${svg(inWatchlist ? 'check' : 'plus')} ${inWatchlist ? 'In Watchlist' : 'Watchlist'}</button>
            <button class="lib-btn lib-btn-primary" id="libDetailAddToQueue">${svg('download')} Add to Queue</button>
          </div>
        </div>
      </div>
      <div class="lib-detail-body">
        <div class="lib-detail-genres">${genres}</div>
        <p class="lib-detail-overview">${overview || 'No description available.'}</p>
        ${director}
        ${castHtml ? `<div class="lib-detail-cast"><h3>Cast</h3>${castHtml}</div>` : ''}
        ${relatedHtml}
        ${tmdbHtml}
      </div>
    </div>
  `;
  initIcons();

  const playBtn = document.getElementById('libDetailPlay');
  if (playBtn) playBtn.onclick = () => playEntry(detail);
  const addBtn = document.getElementById('libDetailAdd');
  if (addBtn) addBtn.onclick = () => toggleWatchlist(detail);
  const queueBtn = document.getElementById('libDetailAddToQueue');
  if (queueBtn) queueBtn.onclick = () => openAddToQueue(detail);

  // Wire up related/tmdb card clicks
  body.querySelectorAll('.lib-card').forEach(el => {
    el.addEventListener('click', () => {
      const id = parseInt(el.dataset.id);
      if (id) {
        openDetail({ id });
      }
    });
  });
}

function makeCardHtml(item) {
  const poster = posterUrl(item) || placeholderPoster();
  return `<div class="lib-card" data-id="${item.id || ''}" data-imdb="${item.imdb_code || ''}">
    <div class="lib-card-poster">
      <img loading="lazy" src="${poster}" alt="${escapeHtml(item.title || '')}" onerror="this.onerror=null;this.src='${placeholderPoster()}'">
    </div>
    <div class="lib-card-info">
      <div class="lib-card-title">${escapeHtml(item.title || '')}</div>
      <div class="lib-card-meta">${[item.year, (item.genres || [])[0]].filter(Boolean).join(' • ')}</div>
    </div>
  </div>`;
}

function makeTmdbHtml(item) {
  return `<div class="lib-card" data-tmdb="${item.tmdb_id || ''}">
    <div class="lib-card-poster">
      <img loading="lazy" src="${item.poster_url || placeholderPoster()}" alt="${escapeHtml(item.title || '')}" onerror="this.onerror=null;this.src='${placeholderPoster()}'">
      <div class="lib-card-tmdb-badge">TMDB</div>
    </div>
    <div class="lib-card-info">
      <div class="lib-card-title">${escapeHtml(item.title || '')}</div>
      <div class="lib-card-meta">${[item.year, item.rating ? item.rating + ' ★' : ''].filter(Boolean).join(' • ')}</div>
    </div>
  </div>`;
}

function closeDetail() {
  const modal = document.getElementById('libModal');
  if (modal) modal.style.display = 'none';
}

async function toggleWatchlist(item) {
  if (!item || !item.id) {
    toast('Cannot add to watchlist', 'error');
    return;
  }
  const id = parseInt(item.id);
  const inList = watchlistIds.has(id);
  try {
    if (inList) {
      await api(`/api/library/watchlist/${id}`, { method: 'DELETE' });
      watchlistIds.delete(id);
      toast(`Removed from watchlist`, 'info');
    } else {
      await api(`/api/library/watchlist/${id}`, { method: 'POST' });
      watchlistIds.add(id);
      toast(`Added to watchlist`, 'success');
    }
    // Refresh icons
    document.querySelectorAll(`[data-id="${id}"] .lib-card-add`).forEach(b => {
      b.classList.toggle('is-added', watchlistIds.has(id));
      b.innerHTML = svg(watchlistIds.has(id) ? 'check' : 'plus', 14);
    });
  } catch (e) {
    toast('Watchlist failed: ' + e.message, 'error');
  }
}

async function playEntry(item) {
  // For catalog entries, we need to know the actual file path on disk.
  // Catalog entries may have season_info, softsub_links, etc. but no direct file path.
  // The simplest play path: if the entry maps to a local file via title match in /api/browse,
  // use that. Otherwise show download links.
  try {
    // Search the file system for a matching file by title
    const res = await api(`/api/browse/`);
    const files = res.items || [];
    const titleKeywords = (item.title || '').toLowerCase().split(' ').slice(0, 3).join(' ');
    const file = files.find(e => !e.is_dir && (e.name || '').toLowerCase().includes(titleKeywords));
    if (file) {
        const ext = (file.name || '').split('.').pop().toLowerCase();
        const isTranscode = !['mp4', 'webm', 'ogv'].includes(ext);
        const url = isTranscode
          ? `/api/stream?path=${encodeURIComponent(file.path)}&transcode=true`
          : `/api/stream?path=${encodeURIComponent(file.path)}`;
        window.location.href = `/player?url=${encodeURIComponent(url)}&title=${encodeURIComponent(file.name)}&path=${encodeURIComponent(file.path)}`;
        return;
      }
  } catch (e) {
    // Continue to fallback
  }
  // Fallback: open Add to Queue modal
  if (item.id) {
    openAddToQueue({ id: item.id, imdb_code: item.imdb_code, title: item.title });
  } else {
    toast('No playable file found for this title. Add it to your media root first.', 'info');
  }
}

// ── Search ──
let searchTimer = null;
function onSearchInput() {
  const q = document.getElementById('libSearch').value.trim();
  clearTimeout(searchTimer);
  if (q.length < 2) {
    document.getElementById('libSearchResults').style.display = 'none';
    return;
  }
  searchTimer = setTimeout(() => doSearch(q), 250);
}

async function doSearch(q) {
  try {
    const data = await api(`/api/library/search?q=${encodeURIComponent(q)}&limit=15`);
    const box = document.getElementById('libSearchResults');
    if (!data.results || !data.results.length) {
      box.innerHTML = '<div class="lib-search-empty">No results</div>';
      box.style.display = '';
      return;
    }
    box.innerHTML = data.results.map(it => `
      <div class="lib-search-item" data-id="${it.id}">
        <div class="lib-search-poster"><img loading="lazy" src="${posterUrl(it)}" onerror="this.onerror=null;this.src='${placeholderPoster()}'"></div>
        <div class="lib-search-info">
          <div class="lib-search-title">${escapeHtml(it.title)}</div>
          <div class="lib-search-meta">${[it.year, (it.genres || []).slice(0, 2).join(', ')].filter(Boolean).join(' • ')}</div>
        </div>
      </div>
    `).join('');
    box.style.display = '';
    box.querySelectorAll('.lib-search-item').forEach(el => {
      el.addEventListener('click', () => {
        const id = parseInt(el.dataset.id);
        const item = data.results.find(r => r.id === id);
        if (item) openDetail(item);
        box.style.display = 'none';
        document.getElementById('libSearch').value = '';
      });
    });
  } catch (e) {
    console.warn('Search failed', e);
  }
}

// ── Init ──
async function init() {
  initIcons();

  // Wire modal close
  const modal = document.getElementById('libModal');
  const closeBtn = document.getElementById('libModalClose');
  const backdrop = document.getElementById('libModalBackdrop');
  if (closeBtn) closeBtn.onclick = closeDetail;
  if (backdrop) backdrop.onclick = closeDetail;
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeDetail();
  });

  // Search input
  const searchEl = document.getElementById('libSearch');
  if (searchEl) {
    searchEl.addEventListener('input', onSearchInput);
    searchEl.addEventListener('blur', () => {
      setTimeout(() => {
        const box = document.getElementById('libSearchResults');
        if (box) box.style.display = 'none';
      }, 200);
    });
  }

  // User menu
  const userBtn = document.getElementById('userMenuBtn');
  const userDrop = document.getElementById('userDropdown');
  if (userBtn && userDrop) {
    userBtn.onclick = (e) => { e.stopPropagation(); userDrop.classList.toggle('show'); };
    document.addEventListener('click', () => userDrop.classList.remove('show'));
  }
  if (currentUser) {
    const header = document.getElementById('userDropdownHeader');
    if (header) header.textContent = currentUser.display_name || currentUser.username || 'User';
    document.getElementById('userMenuBtn').textContent = (currentUser.display_name || currentUser.username || 'U').charAt(0).toUpperCase();
  }
  const logoutBtn = document.getElementById('logoutBtn');
  if (logoutBtn) {
    logoutBtn.onclick = () => {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    };
  }

  // Load watchlist IDs
  try {
    const fav = await api('/api/favorites/ids');
    (fav.ids || []).forEach(id => watchlistIds.add(id));
  } catch (e) {
    // User might be logged out, fall back to library watchlist
    try {
      const wl = await api('/api/library/watchlist');
      (wl.items || []).forEach(it => { if (it.catalog_id) watchlistIds.add(it.catalog_id); });
    } catch {}
  }

  // Show skeleton while loading
  showSkeletons(5);

  // Load rows
  try {
    const data = await api('/api/library/rows');
    libRows = data.rows || [];
    const hero = libRows.find(r => r.type === 'hero');
    if (hero) renderHero(hero.entry);
    renderRows(libRows.filter(r => r.type !== 'hero'));
  } catch (e) {
    document.getElementById('libRows').innerHTML = '<div class="lib-empty"><p>Failed to load library.</p><p>' + escapeHtml(e.message) + '</p></div>';
  }

  // Load genres
  try {
    const g = await api('/api/library/genres');
    libGenres = g.genres || [];
    renderGenres(libGenres);
  } catch {}

  // Keyboard navigation: arrows to focus cards, Enter to open
  document.addEventListener('keydown', (e) => {
    if (document.getElementById('libModal').style.display !== 'none') return;
    if (document.activeElement && ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) return;
    const cards = document.querySelectorAll('.lib-card');
    if (!cards.length) return;
    const focused = document.activeElement;
    let idx = Array.from(cards).indexOf(focused);
    if (e.key === 'ArrowRight') {
      e.preventDefault();
      idx = idx < 0 ? 0 : Math.min(idx + 1, cards.length - 1);
      cards[idx].focus();
      cards[idx].scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      idx = idx < 0 ? 0 : Math.max(idx - 1, 0);
      cards[idx].focus();
      cards[idx].scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
    } else if (e.key === 'Enter' && idx >= 0) {
      cards[idx].click();
    }
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// Add to Queue Modal
// ═══════════════════════════════════════════════════════════════════════════
let _addToQueueState = null;

async function openAddToQueue(item) {
  if (!item || !item.id) {
    toast('Cannot add to queue: missing catalog id', 'error');
    return;
  }
  // Close detail modal if open
  const detailModal = document.getElementById('libModal');
  if (detailModal) detailModal.style.display = 'none';

  // Show a loading modal first
  showAddToQueueModal({ loading: true, title: item.title || '' });

  try {
    const data = await api(`/api/library/queue-options/${item.id}`);
    if (!data.success) throw new Error(data.detail || 'No options available');
    showAddToQueueModal({ data });
  } catch (e) {
    closeAddToQueueModal();
    toast('Failed to load download options: ' + e.message, 'error');
  }
}

function showAddToQueueModal({ loading = false, data = null, title = '' }) {
  let modal = document.getElementById('libQueueModal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'libQueueModal';
    modal.className = 'lib-modal';
    document.body.appendChild(modal);
  }
  modal.style.display = '';

  if (loading) {
    modal.innerHTML = `
      <div class="lib-modal-backdrop" id="libQueueBackdrop"></div>
      <div class="lib-modal-content lib-queue-modal-content">
        <button class="lib-modal-close" id="libQueueClose">×</button>
        <div class="lib-queue-loading">${svg('spinner', 32)}<p>Loading download options…</p></div>
      </div>
    `;
    document.getElementById('libQueueClose').onclick = closeAddToQueueModal;
    document.getElementById('libQueueBackdrop').onclick = closeAddToQueueModal;
    return;
  }

  // Build selection state
  _addToQueueState = {
    data,
    selectedSubtitleType: null,
    selectedOption: null,
    selectedSeason: null,
    selectedEpisodes: new Set(),  // empty = all
    episodes: [],
    loadingEpisodes: false,
  };

  // Pre-select first subtitle type and first option
  if (data.subtitle_types.length > 0) {
    _addToQueueState.selectedSubtitleType = data.subtitle_types[0].key;
    if (data.subtitle_types[0].options.length > 0) {
      _addToQueueState.selectedOption = data.subtitle_types[0].options[0];
    }
  }
  // Pre-select first season
  const seasonKeys = Object.keys(data.seasons);
  if (seasonKeys.length > 0) {
    _addToQueueState.selectedSeason = seasonKeys[0];
  }

  renderAddToQueueModal();
}

function renderAddToQueueModal() {
  const modal = document.getElementById('libQueueModal');
  if (!modal || !_addToQueueState) return;
  const { data, selectedSubtitleType, selectedOption, selectedSeason, episodes, loadingEpisodes } = _addToQueueState;

  const st = data.subtitle_types.find(s => s.key === selectedSubtitleType);
  const options = st ? st.options : [];

  const subtitleButtons = data.subtitle_types.map(s => `
    <button class="lib-queue-chip ${s.key === selectedSubtitleType ? 'active' : ''}" data-subtype="${s.key}">${escapeHtml(s.label)} (${s.options.length})</button>
  `).join('');

  const optionButtons = options.map((o, i) => `
    <button class="lib-queue-option ${selectedOption && selectedOption.url === o.url ? 'active' : ''}" data-opt-idx="${i}">
      <span class="lib-queue-option-label">${escapeHtml(o.label)}</span>
      ${o.size ? `<span class="lib-queue-option-size">${escapeHtml(o.size)}</span>` : ''}
    </button>
  `).join('');

  const seasonKeys = Object.keys(data.seasons);
  const seasonButtons = data.is_series ? `
    <div class="lib-queue-section">
      <label class="lib-queue-label">Season</label>
      <div class="lib-queue-chips">
        ${seasonKeys.map(sk => `<button class="lib-queue-chip ${sk === selectedSeason ? 'active' : ''}" data-season="${escapeHtml(sk)}">${escapeHtml(sk)} ${data.seasons[sk].episode_count ? `(${data.seasons[sk].episode_count})` : ''}</button>`).join('')}
      </div>
    </div>
  ` : '';

  const episodeSection = data.is_series ? `
    <div class="lib-queue-section">
      <label class="lib-queue-label">Episodes ${selectedSeason && episodes.length > 0 ? `<button class="lib-queue-link-btn" id="libQueueSelectAll">${_addToQueueState.selectedEpisodes.size === episodes.length ? 'Deselect All' : 'Select All'}</button>` : ''}</label>
      ${loadingEpisodes ? `<div class="lib-queue-loading">${svg('spinner', 16)}<p>Loading episodes…</p></div>` :
        episodes.length > 0 ? `<div class="lib-queue-episodes" id="libQueueEpisodes">${episodes.map((ep, i) => `
          <label class="lib-queue-episode ${_addToQueueState.selectedEpisodes.has(i) ? 'active' : ''}" data-ep-idx="${i}">
            <input type="checkbox" ${_addToQueueState.selectedEpisodes.has(i) ? 'checked' : ''}>
            <span class="lib-queue-ep-name">${escapeHtml(ep.name)}</span>
            ${ep.size ? `<span class="lib-queue-ep-size">${escapeHtml(ep.size)}</span>` : ''}
          </label>
        `).join('')}</div>` :
        (selectedSeason && data.seasons[selectedSeason] && data.seasons[selectedSeason].url ? `<p class="lib-queue-hint">All episodes will be downloaded from this season.</p>` : `<p class="lib-queue-empty">No episode preview available.</p>`)}
    </div>
  ` : '';

  const noOptions = data.subtitle_types.length === 0 || options.length === 0;
  const downloadHint = noOptions ? `<p class="lib-queue-hint">No download links found in the catalog. You can add the title to your watchlist and try again later.</p>` : '';

  modal.innerHTML = `
    <div class="lib-modal-backdrop" id="libQueueBackdrop"></div>
    <div class="lib-modal-content lib-queue-modal-content">
      <button class="lib-modal-close" id="libQueueClose">×</button>
      <div class="lib-queue-header">
        <h2 class="lib-queue-title">${svg('download')} Add to Queue</h2>
        <p class="lib-queue-subtitle">${escapeHtml(data.title)}${data.year ? ` (${escapeHtml(data.year)})` : ''}</p>
      </div>
      <div class="lib-queue-body">
        ${data.subtitle_types.length > 0 ? `
          <div class="lib-queue-section">
            <label class="lib-queue-label">Subtitle Type</label>
            <div class="lib-queue-chips" id="libQueueSubtypes">${subtitleButtons}</div>
          </div>
        ` : ''}
        ${options.length > 0 ? `
          <div class="lib-queue-section">
            <label class="lib-queue-label">Quality / Source</label>
            <div class="lib-queue-options" id="libQueueOptions">${optionButtons}</div>
          </div>
        ` : ''}
        ${seasonButtons}
        ${episodeSection}
        ${downloadHint}
      </div>
      <div class="lib-queue-footer">
        <button class="lib-btn lib-btn-ghost" id="libQueueCancel">Cancel</button>
        <button class="lib-btn lib-btn-primary" id="libQueueSubmit" ${noOptions ? 'disabled' : ''}>
          ${svg('download')} Add to Queue & Go to Downloads
        </button>
      </div>
    </div>
  `;

  // Wire events
  document.getElementById('libQueueClose').onclick = closeAddToQueueModal;
  document.getElementById('libQueueBackdrop').onclick = closeAddToQueueModal;
  document.getElementById('libQueueCancel').onclick = closeAddToQueueModal;
  document.getElementById('libQueueSubmit').onclick = submitAddToQueue;
  if (data.subtitle_types.length > 0) {
    document.querySelectorAll('#libQueueSubtypes .lib-queue-chip').forEach(b => {
      b.onclick = () => {
        _addToQueueState.selectedSubtitleType = b.dataset.subtype;
        const st = _addToQueueState.data.subtitle_types.find(s => s.key === _addToQueueState.selectedSubtitleType);
        _addToQueueState.selectedOption = st && st.options[0] ? st.options[0] : null;
        renderAddToQueueModal();
      };
    });
  }
  document.querySelectorAll('#libQueueOptions .lib-queue-option').forEach(b => {
    b.onclick = () => {
      const idx = parseInt(b.dataset.optIdx);
      _addToQueueState.selectedOption = options[idx];
      renderAddToQueueModal();
    };
  });
  if (data.is_series) {
    document.querySelectorAll('[data-season]').forEach(b => {
      b.onclick = () => {
        _addToQueueState.selectedSeason = b.dataset.season;
        _addToQueueState.episodes = [];
        _addToQueueState.selectedEpisodes = new Set();
        renderAddToQueueModal();
        loadSeasonEpisodes(data.id, data.seasons[b.dataset.season].url);
      };
    });
    document.querySelectorAll('#libQueueEpisodes .lib-queue-episode').forEach(el => {
      el.onclick = (e) => {
        e.preventDefault();
        const idx = parseInt(el.dataset.epIdx);
        if (_addToQueueState.selectedEpisodes.has(idx)) _addToQueueState.selectedEpisodes.delete(idx);
        else _addToQueueState.selectedEpisodes.add(idx);
        renderAddToQueueModal();
      };
    });
    const selAll = document.getElementById('libQueueSelectAll');
    if (selAll) selAll.onclick = (e) => {
      e.preventDefault();
      if (_addToQueueState.selectedEpisodes.size === _addToQueueState.episodes.length) {
        _addToQueueState.selectedEpisodes.clear();
      } else {
        _addToQueueState.selectedEpisodes = new Set(_addToQueueState.episodes.map((_, i) => i));
      }
      renderAddToQueueModal();
    };
  }
}

async function loadSeasonEpisodes(catalogId, seasonUrl) {
  if (!seasonUrl) return;
  _addToQueueState.loadingEpisodes = true;
  renderAddToQueueModal();
  try {
    const data = await api(`/api/library/season-episodes?url=${encodeURIComponent(seasonUrl)}`);
    if (data.success) {
      _addToQueueState.episodes = data.episodes || [];
      // Pre-select all by default
      _addToQueueState.selectedEpisodes = new Set(_addToQueueState.episodes.map((_, i) => i));
    } else {
      _addToQueueState.episodes = [];
    }
  } catch (e) {
    _addToQueueState.episodes = [];
    toast('Failed to load episodes: ' + e.message, 'error');
  } finally {
    _addToQueueState.loadingEpisodes = false;
    renderAddToQueueModal();
  }
}

async function submitAddToQueue() {
  if (!_addToQueueState) return;
  const { data, selectedOption, selectedSeason, selectedEpisodes, episodes } = _addToQueueState;
  if (!selectedOption) {
    toast('Please select a quality', 'error');
    return;
  }
  const submitBtn = document.getElementById('libQueueSubmit');
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerHTML = svg('spinner', 14) + ' Adding…';
  }

  try {
    if (data.is_series && selectedSeason) {
      // Series: queue the season or specific episodes
      const seasonInfo = data.seasons[selectedSeason];
      const params = new URLSearchParams({
        catalog_id: String(data.id),
        url: seasonInfo.url,
        quality_label: selectedOption.label,
        is_season: 'true',
        season_name: selectedSeason,
      });
      const result = await api('/api/downloads?' + params.toString(), { method: 'POST' });
      if (result.success) {
        const count = result.count || (result.tasks ? result.tasks.length : 1);
        toast(`Added ${count} episode(s) to queue!`, 'success');
        closeAddToQueueModal();
        setTimeout(() => { window.location.href = '/downloads'; }, 800);
      } else {
        toast('Failed to add: ' + (result.detail || 'Unknown error'), 'error');
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = svg('download') + ' Add to Queue & Go to Downloads';
        }
      }
    } else {
      // Movie: queue the single URL
      const params = new URLSearchParams({
        catalog_id: String(data.id),
        url: selectedOption.url,
        quality_label: selectedOption.label,
      });
      const result = await api('/api/downloads?' + params.toString(), { method: 'POST' });
      if (result.success) {
        toast(`Added "${data.title}" to queue!`, 'success');
        closeAddToQueueModal();
        setTimeout(() => { window.location.href = '/downloads'; }, 800);
      } else {
        toast('Failed to add: ' + (result.detail || 'Unknown error'), 'error');
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = svg('download') + ' Add to Queue & Go to Downloads';
        }
      }
    }
  } catch (e) {
    toast('Network error: ' + e.message, 'error');
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML = svg('download') + ' Add to Queue & Go to Downloads';
    }
  }
}

function closeAddToQueueModal() {
  const modal = document.getElementById('libQueueModal');
  if (modal) modal.style.display = 'none';
  _addToQueueState = null;
}

document.addEventListener('DOMContentLoaded', init);
