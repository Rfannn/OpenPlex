import { api } from './api.js';
import { toast } from './toast.js';
import { svg } from './svg.js';
import { registerRoute, initRouter, navigate } from './router.js';

let state = {
  sections: [],
  continueWatching: [],
  watchlist: [],
  user: null,
};

async function fetchUser() {
  try {
    const r = await api('/api/auth/me');
    state.user = await r.json();
  } catch {
    state.user = null;
  }
}

// --- Library API ---
const SECTION_ICONS = {
  Movies: 'film',
  Series: 'tv',
  Music: 'music',
  Images: 'image',
};

async function loadLibrary() {
  try {
    const r = await api('/api/library');
    const data = await r.json();
    if (data.success) {
      state.sections = data.sections || [];
      renderLibrary();
    }
  } catch (err) {
    toast('Failed to load library: ' + err.message, 'error');
  }
}

async function loadContinueWatching() {
  if (!state.user) return;
  try {
    const r = await api('/api/library/continue-watching');
    const data = await r.json();
    if (data.success) {
      state.continueWatching = data.items || [];
      renderContinueWatching();
    }
  } catch {}
}

async function loadWatchlist() {
  if (!state.user) return;
  try {
    const r = await api('/api/library/watchlist');
    const data = await r.json();
    if (data.success) {
      state.watchlist = data.items || [];
      renderWatchlist();
    }
  } catch {}
}

// --- Renderers ---
function renderLibrary() {
  const container = document.getElementById('library-content');
  if (!container) return;
  container.innerHTML = state.sections.map(section => `
    <section class="lib-section">
      <div class="lib-section-header">
        <h2>${svg(SECTION_ICONS[section.name] || 'film', 22)} ${section.name}</h2>
        <span class="lib-count">${section.items.length} items</span>
      </div>
      <div class="lib-row" data-section="${section.name}">
        ${section.items.map(item => renderCard(item)).join('')}
      </div>
    </section>
  `).join('');

  document.querySelectorAll('.lib-card').forEach(card => {
    card.addEventListener('click', () => {
      const path = card.dataset.path;
      if (path) {
        const isDir = card.dataset.type === 'directory';
        if (isDir) {
          navigate(`/library?path=${encodeURIComponent(path)}`);
        } else {
          window.open(path, '_blank');
        }
      }
    });
  });
}

function renderCard(item) {
  const isDir = item.type === 'directory';
  const title = item.name || 'Untitled';
  const thumb = item.thumbnail || '';
  return `
    <div class="lib-card" data-path="${item.path}" data-type="${item.type}" title="${title}">
      <div class="lib-card-poster">
        ${thumb ? `<img src="${thumb}" alt="${title}" loading="lazy" />` : `
          <div class="lib-card-placeholder">
            ${svg(isDir ? 'folder' : 'film', 48)}
          </div>
        `}
        ${isDir ? '<span class="lib-card-badge">Folder</span>' : ''}
      </div>
      <div class="lib-card-info">
        <span class="lib-card-title">${title}</span>
        ${item.subtitle ? `<span class="lib-card-sub">${item.subtitle}</span>` : ''}
      </div>
    </div>
  `;
}

function renderContinueWatching() {
  const container = document.getElementById('continue-watching');
  if (!container) return;
  if (!state.continueWatching.length) {
    container.style.display = 'none';
    return;
  }
  container.style.display = 'block';
  const inner = container.querySelector('.lib-row') || container;
  inner.innerHTML = state.continueWatching.map(item => `
    <div class="lib-card lib-card-cw" data-path="${item.path}">
      <div class="lib-card-poster">
        ${item.thumbnail ? `<img src="${item.thumbnail}" alt="${item.name}" loading="lazy" />` : `
          <div class="lib-card-placeholder">${svg('film', 48)}</div>
        `}
        <div class="lib-card-progress">
          <div class="lib-card-progress-bar" style="width:${item.progress_pct || 0}%"></div>
        </div>
      </div>
      <div class="lib-card-info">
        <span class="lib-card-title">${item.name}</span>
        <span class="lib-card-sub">${formatTime(item.position)} remaining</span>
      </div>
    </div>
  `).join('');
}

function renderWatchlist() {
  const container = document.getElementById('watchlist-content');
  if (!container) return;
  if (!state.watchlist.length) {
    container.innerHTML = '<div class="empty-state">Your watchlist is empty. Browse the catalog to add items.</div>';
    return;
  }
  container.innerHTML = `
    <div class="wl-filters">
      ${['all', 'want_to_watch', 'watching', 'completed', 'dropped'].map(status => `
        <button class="wl-filter" data-status="${status}">${status.replace(/_/g, ' ')}</button>
      `).join('')}
    </div>
    <div class="wl-grid">
      ${state.watchlist.map(item => renderWatchlistCard(item)).join('')}
    </div>
  `;
}

function renderWatchlistCard(item) {
  return `
    <div class="lib-card wl-card" data-id="${item.id}">
      <div class="lib-card-poster">
        ${item.poster_url ? `<img src="${item.poster_url}" alt="${item.title}" loading="lazy" />` : `
          <div class="lib-card-placeholder">${svg('film', 48)}</div>
        `}
        <span class="lib-card-status ${item.status}">${item.status?.replace(/_/g, ' ') || 'want to watch'}</span>
      </div>
      <div class="lib-card-info">
        <span class="lib-card-title">${item.title}</span>
        ${item.year ? `<span class="lib-card-sub">${item.year} · ${item.category || ''}</span>` : ''}
        ${item.imdb_score ? `<span class="lib-card-rating">${svg('star', 14)} ${item.imdb_score}</span>` : ''}
      </div>
    </div>
  `;
}

function formatTime(seconds) {
  if (!seconds) return '';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function renderNav() {
  const nav = document.getElementById('main-nav');
  if (!nav) return;
  const links = [
    { path: '/', label: 'Home', icon: 'film' },
    { path: '/library', label: 'Files', icon: 'folder' },
    { path: '/downloads', label: 'Downloads', icon: 'download' },
    { path: '/status', label: 'Status', icon: 'info' },
    { path: '/health', label: 'Health', icon: 'heart' },
  ];
  nav.innerHTML = links.map(l => `
    <a href="#${l.path}" class="nav-link" data-path="${l.path}">
      ${svg(l.icon, 18)} ${l.label}
    </a>
  `).join('');
}

// --- Home page ---
function renderHome() {
  const app = document.getElementById('app');
  app.innerHTML = `
    <nav id="main-nav" class="top-nav"></nav>
    <main class="lib-main">
      ${state.user ? `
        <section id="continue-watching" class="lib-section">
          <div class="lib-section-header">
            <h2>${svg('clock', 22)} Continue Watching</h2>
          </div>
          <div class="lib-row"></div>
        </section>
      ` : ''}
      <section class="lib-hero" id="lib-hero">
        <div class="lib-hero-content">
          <h1>OpenPlex</h1>
          <p>Browse your personal media library</p>
          <div class="lib-hero-actions">
            <button class="glass-btn primary" onclick="navigate('/library')">
              ${svg('folder', 18)} Browse Files
            </button>
            <button class="glass-btn" onclick="navigate('/downloads')">
              ${svg('download', 18)} Catalog
            </button>
          </div>
        </div>
      </section>
      <div id="library-content"></div>
      ${state.user ? `
        <section class="lib-section">
          <div class="lib-section-header">
            <h2>${svg('heart', 22)} My Watchlist</h2>
          </div>
          <div id="watchlist-content"></div>
        </section>
      ` : ''}
    </main>
  `;
  renderNav();
  loadLibrary();
  loadContinueWatching();
  loadWatchlist();
}

// --- Init ---
async function init() {
  await fetchUser();
  registerRoute('/', renderHome);
  registerRoute('/library', () => {
    window.location.href = '/library';
  });
  registerRoute('/downloads', () => {
    window.location.href = '/downloads';
  });
  registerRoute('/status', () => {
    window.location.href = '/status';
  });
  registerRoute('/health', () => {
    window.location.href = '/health';
  });
  registerRoute('*', renderHome);
  initRouter();
}

document.addEventListener('DOMContentLoaded', init);
