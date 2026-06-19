const routes = {};

function getHash() {
  return window.location.hash.replace(/^#/, '') || '/';
}

export function registerRoute(path, handler) {
  routes[path] = handler;
}

export function navigate(path) {
  window.location.hash = path;
}

export function initRouter() {
  function handleRoute() {
    const hash = getHash();
    const handler = routes[hash];
    if (handler) {
      handler();
    } else {
      const catchAll = routes['*'];
      if (catchAll) catchAll(hash);
    }
  }

  window.addEventListener('hashchange', handleRoute);
  window.addEventListener('DOMContentLoaded', handleRoute);
  handleRoute();
}
