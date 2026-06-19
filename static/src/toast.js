const toastContainer = document.createElement('div');
toastContainer.id = 'toast-container';
document.addEventListener('DOMContentLoaded', () => {
  document.body.appendChild(toastContainer);
});

export function toast(message, type = 'info', duration = 4000) {
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.textContent = message;
  toastContainer.appendChild(el);
  requestAnimationFrame(() => el.classList.add('toast-visible'));
  setTimeout(() => {
    el.classList.remove('toast-visible');
    el.addEventListener('transitionend', () => el.remove());
  }, duration);
}
