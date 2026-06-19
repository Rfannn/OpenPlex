// OpenPlex — Shared Navigation Component
// Injects a consistent nav bar into every page

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
    const path = window.location.pathname;
    if (pageId === 'files' && path === '/') return true;
    if (pageId === 'library' && path.startsWith('/library')) return true;
    if (pageId === 'downloads' && path.startsWith('/downloads')) return true;
    if (pageId === 'chat' && path.startsWith('/chat')) return true;
    return false;
  },

  render() {
    const user = this.getUser();
    const navLinks = this.pages.map(p => {
      const active = this.isActive(p.id) ? ' active' : '';
      return `<a href="${p.href}" class="nav-link${active}" data-page="${p.id}">
        <span class="nav-icon">${this._svg(p.icon)}</span>
        <span class="nav-label">${p.label}</span>
      </a>`;
    }).join('');

    const userInitial = user ? (user.display_name || user.username || '?')[0].toUpperCase() : '?';
    const userName = user ? (user.display_name || user.username) : 'Not logged in';

    return `
    <header class="op-header" id="opHeader">
      <div class="op-header-inner">
        <a href="/" class="op-brand">
          <span class="op-brand-icon">${this._svg('plex')}</span>
          <span class="op-brand-text">OpenPlex</span>
        </a>
        <nav class="op-nav" id="opNav">
          ${navLinks}
        </nav>
        <div class="op-header-right">
          <button class="op-icon-btn" id="opSearchBtn" title="Search">${this._svg('search')}</button>
          <div class="op-user-menu">
            <button class="op-user-btn" id="opUserBtn">
              <span class="op-user-avatar">${userInitial}</span>
            </button>
            <div class="op-dropdown" id="opDropdown">
              <div class="op-dropdown-header">${userName}</div>
              <div class="op-dropdown-divider"></div>
              <a href="/profile" class="op-dropdown-item">${this._svg('user')} Profile</a>
              <a href="/upload" class="op-dropdown-item">${this._svg('upload')} Uploads</a>
              <a href="/status" class="op-dropdown-item">${this._svg('chart-bar')} Server Status</a>
              <div class="op-dropdown-divider"></div>
              <button class="op-dropdown-item" id="opLogoutBtn">${this._svg('sign-out')} Logout</button>
            </div>
          </div>
        </div>
      </div>
    </header>

    <nav class="op-bottom-nav" id="opBottomNav">
      ${this.pages.map(p => {
        const active = this.isActive(p.id) ? ' active' : '';
        return `<a href="${p.href}" class="op-bottom-item${active}">
          <span class="op-bottom-icon">${this._svg(p.icon)}</span>
          <span class="op-bottom-label">${p.label}</span>
        </a>`;
      }).join('')}
    </nav>`;
  },

  inject() {
    // Remove existing headers/navs that aren't ours
    document.querySelectorAll('.header, .lib-header, .chat-header, .bottom-nav').forEach(el => el.remove());

    // Inject our nav at the start of body
    const navHtml = this.render();
    const wrapper = document.createElement('div');
    wrapper.id = 'opNavWrapper';
    wrapper.innerHTML = navHtml;
    document.body.insertBefore(wrapper, document.body.firstChild);

    // Add padding-top to main content
    const style = document.createElement('style');
    style.textContent = `
      body { padding-top: 56px; padding-bottom: 64px; }
      @media (min-width: 769px) { body { padding-bottom: 0; } }
    `;
    document.head.appendChild(style);

    // Wire up user menu
    const userBtn = document.getElementById('opUserBtn');
    const dropdown = document.getElementById('opDropdown');
    if (userBtn && dropdown) {
      userBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        dropdown.classList.toggle('open');
      });
      document.addEventListener('click', () => dropdown.classList.remove('open'));
    }

    // Wire up logout
    const logoutBtn = document.getElementById('opLogoutBtn');
    if (logoutBtn) {
      logoutBtn.addEventListener('click', () => {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        window.location.href = '/login';
      });
    }
  },

  _svg(name) {
    const icons = {
      'plex': '<rect x="3" y="3" width="18" height="18" rx="3" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M8 8v8M8 12h4M16 8v8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>',
      'folder': '<path d="M2 6a2 2 0 012-2h4l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" stroke="currentColor" stroke-width="1.5" fill="none"/>',
      'film': '<rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M7 3v18M17 3v18M3 7h4M3 12h4M3 17h4M17 7h4M17 12h4M17 17h4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>',
      'download': '<path d="M12 3v12m0 0l-4-4m4 4l4-4M4 17v1a2 2 0 002 2h12a2 2 0 002-2v-1" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
      'comments': '<path d="M21 11.5a8.38 8.38 0 01-.9 3.8 8.5 8.5 0 01-7.6 4.7 8.38 8.38 0 01-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 01-.9-3.8 8.5 8.5 0 014.7-7.6 8.38 8.38 0 013.8-.9h.5a8.48 8.48 0 018 8v.5z" stroke="currentColor" stroke-width="1.5" fill="none"/>',
      'search': '<circle cx="11" cy="11" r="7" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M21 21l-5-5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>',
      'user': '<circle cx="12" cy="8" r="4" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M4 20c0-4 4-7 8-7s8 3 8 7" stroke="currentColor" stroke-width="1.5" fill="none"/>',
      'upload': '<path d="M12 15V3m0 0l-4 4m4-4l4 4M4 17v1a2 2 0 002 2h12a2 2 0 002-2v-1" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
      'chart-bar': '<rect x="3" y="12" width="4" height="9" rx="1" stroke="currentColor" stroke-width="1.5" fill="none"/><rect x="10" y="6" width="4" height="15" rx="1" stroke="currentColor" stroke-width="1.5" fill="none"/><rect x="17" y="3" width="4" height="18" rx="1" stroke="currentColor" stroke-width="1.5" fill="none"/>',
      'sign-out': '<path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
    };
    return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">${icons[name] || ''}</svg>`;
  }
};

// Auto-inject on DOMContentLoaded
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => OpenPlexNav.inject());
} else {
  OpenPlexNav.inject();
}
