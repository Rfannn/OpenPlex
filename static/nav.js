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
          <div class="op-search-wrap" id="opSearchWrap">
            <span class="op-search-icon-sm">${this._svg('search')}</span>
            <input type="text" class="op-search-input" id="opSearchInput" placeholder="Search..." autocomplete="off">
            <kbd class="op-search-kbd">⌘K</kbd>
          </div>
          <div class="op-user">
            <button class="op-avatar" id="opAvatar">${initial}</button>
            <div class="op-menu" id="opMenu">
              <div class="op-menu-head">${name}</div>
              <div class="op-menu-sep"></div>
              <a href="/profile" class="op-menu-item">${this._svg('user')} Profile</a>
              <a href="/upload" class="op-menu-item">${this._svg('upload')} Uploads</a>
              <a href="/settings" class="op-menu-item">${this._svg('settings')} Settings</a>
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

    // Search — inline input with dropdown results
    const searchInput = document.getElementById('opSearchInput');
    if (searchInput) {
      const resultsDiv = document.createElement('div');
      resultsDiv.className = 'op-search-dropdown';
      resultsDiv.id = 'opSearchDropdown';
      searchInput.parentElement.appendChild(resultsDiv);

      let timer = null;
      searchInput.addEventListener('input', (e) => {
        const q = e.target.value.trim();
        clearTimeout(timer);
        if (q.length < 2) { resultsDiv.innerHTML = ''; resultsDiv.classList.remove('open'); return; }
        timer = setTimeout(() => this._doSearch(q), 250);
      });
      searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); }
      });
      searchInput.addEventListener('focus', () => { if (resultsDiv.innerHTML) resultsDiv.classList.add('open'); });
      document.addEventListener('click', (e) => {
        if (!e.target.closest('.op-search-wrap')) resultsDiv.classList.remove('open');
      });
      document.addEventListener('keydown', (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') { e.preventDefault(); searchInput.focus(); }
        if (e.key === 'Escape') { searchInput.blur(); resultsDiv.classList.remove('open'); }
      });
    }
  },

  _currentPage() {
    const p = window.location.pathname;
    if (p === '/') return 'files';
    if (p.startsWith('/library')) return 'library';
    if (p.startsWith('/downloads')) return 'downloads';
    if (p.startsWith('/settings')) return 'settings';
    if (p.startsWith('/chat')) return 'chat';
    return 'other';
  },

  _esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; },

  async _doSearch(q) {
    const results = document.getElementById('opSearchDropdown');
    results.innerHTML = '<div class="op-search-loading">Searching...</div>';
    results.classList.add('open');
    const page = this._currentPage();

    try {
      let html = '';

      if (page === 'settings') {
        const settingsKeywords = [
          { section: 'Server', icon: '🖥️', terms: ['host', 'port', 'debug', 'media', 'root', 'path', 'server'] },
          { section: 'AI Configuration', icon: '🤖', terms: ['agnes', 'ai', 'model', 'llama', 'local', 'majid', 'gpt'] },
          { section: 'Metadata APIs', icon: '🎬', terms: ['tmdb', 'omdb', 'fanart', 'tvdb', 'metadata', 'api key'] },
          { section: 'Subtitles', icon: '💬', terms: ['opensubtitles', 'subtitle', 'sub'] },
          { section: 'Catalog', icon: '📚', terms: ['catalog', 'refresh', 'auto'] },
          { section: 'Downloads', icon: '⬇️', terms: ['aria2', 'download', 'rpc', 'port'] },
          { section: 'Display & Storage', icon: '🎨', terms: ['cors', 'thumbnail', 'cache', 'disk', 'storage', 'display'] },
        ];
        const lq = q.toLowerCase();
        settingsKeywords.forEach(s => {
          if (s.terms.some(t => lq.includes(t) || t.includes(lq))) {
            html += `<div class="op-search-hit" onclick="document.querySelector('[data-settings-nav]')?.click(); window.OpenPlexNav._scrollToSetting('${s.section}'); this.closest('.op-search-dropdown').classList.remove('open');">
              <span class="op-search-hit-icon">${s.icon}</span>
              <div><div class="op-search-hit-name">${s.section}</div>
              <div class="op-search-hit-meta">Settings</div></div>
            </div>`;
          }
        });
        if (!html) html = '<div class="op-search-empty">No matching settings</div>';

      } else if (page === 'files') {
        const fileR = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
        const fileD = await fileR.json();
        if (fileD.results && fileD.results.length) {
          fileD.results.slice(0, 10).forEach(f => {
            html += `<a href="/?q=${encodeURIComponent(f.name)}" class="op-search-hit" onclick="event.preventDefault(); this.closest('.op-search-dropdown').classList.remove('open'); document.getElementById('opSearchInput').value='';">
              <span class="op-search-hit-icon">${f.type === 'video' ? '🎥' : f.type === 'audio' ? '🎵' : '📄'}</span>
              <div><div class="op-search-hit-name">${this._esc(f.name)}</div>
              <div class="op-search-hit-meta">File</div></div>
            </a>`;
          });
        }
        if (!html) html = '<div class="op-search-empty">No matching files</div>';

      } else if (page === 'downloads') {
        const dlR = await fetch(`/api/downloads/search?q=${encodeURIComponent(q)}`);
        const dlD = await dlR.json();
        if (dlD.downloads && dlD.downloads.length) {
          dlD.downloads.slice(0, 10).forEach(d => {
            html += `<div class="op-search-hit" onclick="this.closest('.op-search-dropdown').classList.remove('open');">
              <span class="op-search-hit-icon">⬇️</span>
              <div><div class="op-search-hit-name">${this._esc(d.title || d.file_name)}</div>
              <div class="op-search-hit-meta">${d.status || ''}</div></div>
            </div>`;
          });
        }
        if (!html) html = '<div class="op-search-empty">No matching downloads</div>';

      } else {
        const libR = await fetch(`/api/library/search?q=${encodeURIComponent(q)}&limit=8`);
        const libD = await libR.json();
        if (libD.results && libD.results.length) {
          libD.results.forEach(r => {
            html += `<a href="/library?q=${encodeURIComponent(r.title || '')}" class="op-search-hit" onclick="event.preventDefault(); this.closest('.op-search-dropdown').classList.remove('open'); window.location.href='/library';">
              <span class="op-search-hit-icon">🎬</span>
              <div><div class="op-search-hit-name">${this._esc(r.title || '')}</div>
              <div class="op-search-hit-meta">${[r.year, (r.genres||[]).slice(0,2).join(', ')].filter(Boolean).join(' · ')}</div></div>
            </a>`;
          });
        }
        const fileR = await fetch(`/api/search?q=${encodeURIComponent(q)}`).catch(() => ({ json: () => ({ results: [] }) }));
        const fileD = await fileR.json();
        if (fileD.results && fileD.results.length) {
          fileD.results.slice(0, 5).forEach(f => {
            html += `<a href="/?q=${encodeURIComponent(f.name)}" class="op-search-hit" onclick="event.preventDefault(); this.closest('.op-search-dropdown').classList.remove('open'); window.location.href='/';">
              <span class="op-search-hit-icon">${f.type === 'video' ? '🎥' : f.type === 'audio' ? '🎵' : '📄'}</span>
              <div><div class="op-search-hit-name">${this._esc(f.name)}</div>
              <div class="op-search-hit-meta">File</div></div>
            </a>`;
          });
        }
        if (!html) html = '<div class="op-search-empty">No results</div>';
      }

      results.innerHTML = html;
    } catch { results.innerHTML = '<div class="op-search-empty">Search failed</div>'; }
  },

  _scrollToSetting(section) {
    const headings = document.querySelectorAll('.settings-section-header h2');
    headings.forEach(h => {
      if (h.textContent === section) {
        h.closest('.settings-section')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        h.closest('.settings-section')?.classList.add('settings-highlight');
        setTimeout(() => h.closest('.settings-section')?.classList.remove('settings-highlight'), 2000);
      }
    });
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
      'settings': '<circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" stroke="currentColor" stroke-width="1.5" fill="none"/>',
      'arrow-left': '<path d="M19 12H5m0 0l7 7m-7-7l7-7" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
    };
    return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none">${i[n]||''}</svg>`;
  }
};

document.readyState==='loading' ? document.addEventListener('DOMContentLoaded',()=>OpenPlexNav.inject()) : OpenPlexNav.inject();
