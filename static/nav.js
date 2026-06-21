// OpenPlex — Unified Navigation
const OpenPlexNav = {
  pages: [
    { href: '/', icon: 'folder', label: 'Files', id: 'files' },
    { href: '/library', icon: 'film', label: 'Library', id: 'library' },
    { href: '/downloads', icon: 'download', label: 'Downloads', id: 'downloads' },
    { href: '/chat', icon: 'comments', label: 'AI Chat', id: 'chat' },
  ],

  getUser() {
    try { return JSON.parse(localStorage.getItem('user') || 'null'); } catch { return null; }
  },

  isActive(pageId) {
    const p = window.location.pathname;
    if (pageId === 'files' && p === '/') return true;
    if (pageId === 'library' && p.startsWith('/library')) return true;
    if (pageId === 'downloads' && p.startsWith('/downloads')) return true;
    if (pageId === 'chat' && p.startsWith('/chat')) return true;
    return false;
  },

  render() {
    const user = this.getUser();
    const navLinks = this.pages.map(pg => {
      const a = this.isActive(pg.id) ? ' active' : '';
      return `<a href="${pg.href}" class="op-link${a}">
        <span class="op-link-icon">${this._svg(pg.icon)}</span>
        <span class="op-link-text">${pg.label}</span>
      </a>`;
    }).join('');

    const initial = user ? (user.display_name || user.username || '?')[0].toUpperCase() : '?';
    const name = user ? (user.display_name || user.username) : 'Guest';

    return `
    <header class="op-bar">
      <div class="op-bar-inner">
        <div class="op-left">
          <button class="op-back" id="opBack" style="display:none">${this._svg('arrow-left')}</button>
          <nav class="op-links">${navLinks}</nav>
        </div>
        <a href="/" class="op-logo">
          <span class="op-logo-glow"></span>
          <span class="op-logo-text">OpenPlex</span>
        </a>
        <div class="op-right">
          <button class="op-search-btn" id="opSearch" title="Search">${this._svg('search')}</button>
          <div class="op-user">
            <button class="op-avatar" id="opAvatar">${initial}</button>
            <div class="op-menu" id="opMenu">
              <div class="op-menu-head">${name}</div>
              <div class="op-menu-sep"></div>
              <a href="/profile" class="op-menu-item">${this._svg('user')} Profile</a>
              <a href="/upload" class="op-menu-item">${this._svg('upload')} Uploads</a>
              <a href="/status" class="op-menu-item">${this._svg('chart-bar')} Server</a>
              <div class="op-menu-sep"></div>
              <button class="op-menu-item" id="opLogout">${this._svg('sign-out')} Logout</button>
            </div>
          </div>
        </div>
      </div>
    </header>
    <nav class="op-tab">
      ${this.pages.map(pg => {
        const a = this.isActive(pg.id) ? ' active' : '';
        return `<a href="${pg.href}" class="op-tab-item${a}">
          <span class="op-tab-icon">${this._svg(pg.icon)}</span>
          <span class="op-tab-label">${pg.label}</span>
        </a>`;
      }).join('')}
    </nav>`;
  },

  inject() {
    document.querySelectorAll('.header, .lib-header, .chat-header, .bottom-nav, .header-content, .header-nav, .header-left, .lib-header-content, .lib-header-bg, .lib-brand').forEach(e => e.remove());
    const w = document.createElement('div');
    w.id = 'opNavWrap';
    w.innerHTML = this.render();
    document.body.insertBefore(w, document.body.firstChild);

    const back = document.getElementById('opBack');
    if (back && window.location.pathname !== '/') {
      back.style.display = 'flex';
      back.onclick = () => window.history.back();
    }

    const av = document.getElementById('opAvatar');
    const menu = document.getElementById('opMenu');
    if (av && menu) {
      av.onclick = (e) => { e.stopPropagation(); menu.classList.toggle('open'); };
      document.onclick = () => menu.classList.remove('open');
    }

    const lo = document.getElementById('opLogout');
    if (lo) lo.onclick = () => {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    };

    // Search overlay
    const searchBtn = document.getElementById('opSearch');
    if (searchBtn) {
      const overlay = document.createElement('div');
      overlay.className = 'op-search-overlay';
      overlay.id = 'opSearchOverlay';
      overlay.innerHTML = `
        <div class="op-search-backdrop"></div>
        <div class="op-search-box">
          <span class="op-search-icon">${this._svg('search')}</span>
          <input type="text" id="opSearchInput" placeholder="Search files, library, downloads..." autocomplete="off" autofocus>
          <kbd class="op-search-esc">ESC</kbd>
        </div>
        <div class="op-search-results" id="opSearchResults"></div>
      `;
      document.body.appendChild(overlay);

      searchBtn.onclick = () => {
        overlay.classList.add('open');
        setTimeout(() => document.getElementById('opSearchInput').focus(), 100);
      };
      overlay.querySelector('.op-search-backdrop').onclick = () => overlay.classList.remove('open');
      document.addEventListener('keydown', (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
          e.preventDefault();
          overlay.classList.add('open');
          setTimeout(() => document.getElementById('opSearchInput').focus(), 100);
        }
        if (e.key === 'Escape') overlay.classList.remove('open');
      });

      // Live search
      let searchTimer = null;
      document.getElementById('opSearchInput').addEventListener('input', (e) => {
        const q = e.target.value.trim();
        clearTimeout(searchTimer);
        if (q.length < 2) {
          document.getElementById('opSearchResults').innerHTML = '';
          return;
        }
        searchTimer = setTimeout(() => this._doSearch(q), 250);
      });
    }
  },

  async _doSearch(q) {
    const results = document.getElementById('opSearchResults');
    results.innerHTML = '<div class="op-search-loading">Searching...</div>';
    try {
      // Search library
      const libR = await fetch(`/api/library/search?q=${encodeURIComponent(q)}&limit=5`);
      const libD = await libR.json();
      // Search files
      const fileR = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
      const fileD = await fileR.json();

      let html = '';
      if (libD.results && libD.results.length) {
        html += '<div class="op-search-group">Library</div>';
        libD.results.forEach(r => {
          html += `<a href="/library" class="op-search-item" onclick="document.getElementById('opSearchOverlay').classList.remove('open')">
            <span class="op-search-type">🎬</span>
            <div><div class="op-search-name">${r.title || ''}</div>
            <div class="op-search-meta">${[r.year, (r.genres||[]).slice(0,2).join(', ')].filter(Boolean).join(' · ')}</div></div>
          </a>`;
        });
      }
      if (fileD.results && fileD.results.length) {
        html += '<div class="op-search-group">Files</div>';
        fileD.results.slice(0, 5).forEach(f => {
          html += `<a href="/" class="op-search-item" onclick="document.getElementById('opSearchOverlay').classList.remove('open')">
            <span class="op-search-type">${f.type === 'video' ? '🎥' : f.type === 'audio' ? '🎵' : f.type === 'image' ? '🖼️' : '📄'}</span>
            <div><div class="op-search-name">${f.name}</div>
            <div class="op-search-meta">${f.path || ''}</div></div>
          </a>`;
        });
      }
      if (!html) html = '<div class="op-search-empty">No results found</div>';
      results.innerHTML = html;
    } catch {
      results.innerHTML = '<div class="op-search-empty">Search failed</div>';
    }
  },

  _svg(n) {
    const i = {
      'plex': '<circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M12 6v12M12 12l5-3M12 12l5 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>',
      'folder': '<path d="M2 6a2 2 0 012-2h4l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" stroke="currentColor" stroke-width="1.5" fill="none"/>',
      'film': '<rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M7 3v18M17 3v18M3 7h4M3 12h4M3 17h4M17 7h4M17 12h4M17 17h4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>',
      'download': '<path d="M12 3v12m0 0l-4-4m4 4l4-4M4 17v1a2 2 0 002 2h12a2 2 0 002-2v-1" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
      'comments': '<path d="M21 11.5a8.38 8.38 0 01-.9 3.8 8.5 8.5 0 01-7.6 4.7 8.38 8.38 0 01-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 01-.9-3.8 8.5 8.5 0 014.7-7.6 8.38 8.38 0 013.8-.9h.5a8.48 8.48 0 018 8v.5z" stroke="currentColor" stroke-width="1.5" fill="none"/>',
      'search': '<circle cx="11" cy="11" r="7" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M21 21l-5-5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>',
      'user': '<circle cx="12" cy="8" r="4" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M4 20c0-4 4-7 8-7s8 3 8 7" stroke="currentColor" stroke-width="1.5" fill="none"/>',
      'upload': '<path d="M12 15V3m0 0l-4 4m4-4l4 4M4 17v1a2 2 0 002 2h12a2 2 0 002-2v-1" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
      'chart-bar': '<rect x="3" y="12" width="4" height="9" rx="1" stroke="currentColor" stroke-width="1.5" fill="none"/><rect x="10" y="6" width="4" height="15" rx="1" stroke="currentColor" stroke-width="1.5" fill="none"/><rect x="17" y="3" width="4" height="18" rx="1" stroke="currentColor" stroke-width="1.5" fill="none"/>',
      'sign-out': '<path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
      'arrow-left': '<path d="M19 12H5m0 0l7 7m-7-7l7-7" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
    };
    return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none">${i[n]||''}</svg>`;
  }
};

document.readyState==='loading' ? document.addEventListener('DOMContentLoaded',()=>OpenPlexNav.inject()) : OpenPlexNav.inject();
