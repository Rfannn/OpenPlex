// OpenPlex Toast Notifications — professional-grade alerts
const OpenPlexToast = {
  container: null,

  init() {
    if (this.container) return;
    this.container = document.createElement('div');
    this.container.className = 'toast-container';
    document.body.appendChild(this.container);
  },

  _icon(type) {
    const icons = {
      success: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M20 6L9 17l-5-5"/></svg>',
      error: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><path d="M15 9l-6 6M9 9l6 6"/></svg>',
      warning: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/></svg>',
      info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4m0-4h.01"/></svg>',
    };
    return icons[type] || icons.info;
  },

  show({ type = 'info', title = '', message = '', duration = 4000, actions = [] }) {
    this.init();
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    let actionsHtml = '';
    if (actions.length) {
      actionsHtml = '<div class="toast-actions">' +
        actions.map((a, i) => `<button class="toast-btn ${i === 0 ? 'toast-btn-primary' : 'toast-btn-ghost'}" data-action="${i}">${a.label}</button>`).join('') +
        '</div>';
    }

    toast.innerHTML = `
      <div class="toast-icon">${this._icon(type)}</div>
      <div class="toast-body">
        ${title ? `<div class="toast-title">${title}</div>` : ''}
        ${message ? `<div class="toast-message">${message}</div>` : ''}
        ${actionsHtml}
      </div>
      <button class="toast-close">&times;</button>
      ${duration > 0 ? '<div class="toast-progress"></div>' : ''}
    `;

    toast.querySelector('.toast-close').addEventListener('click', () => this._remove(toast));
    actions.forEach((a, i) => {
      const btn = toast.querySelector(`[data-action="${i}"]`);
      if (btn && a.onClick) btn.addEventListener('click', () => { a.onClick(); this._remove(toast); });
    });

    this.container.appendChild(toast);

    if (duration > 0) {
      toast.addEventListener('mouseenter', () => {
        const progress = toast.querySelector('.toast-progress');
        if (progress) progress.style.animationPlayState = 'paused';
      });
      toast.addEventListener('mouseleave', () => {
        const progress = toast.querySelector('.toast-progress');
        if (progress) progress.style.animationPlayState = 'running';
      });
      setTimeout(() => this._remove(toast), duration);
    }

    return toast;
  },

  _remove(toast) {
    if (!toast || toast.classList.contains('removing')) return;
    toast.classList.add('removing');
    setTimeout(() => toast.remove(), 300);
  },

  success(title, message, actions) { return this.show({ type: 'success', title, message, actions }); },
  error(title, message, actions) { return this.show({ type: 'error', title, message, duration: 6000, actions }); },
  warning(title, message, actions) { return this.show({ type: 'warning', title, message, duration: 5000, actions }); },
  info(title, message, actions) { return this.show({ type: 'info', title, message, actions }); },
};
