const API_BASE = '';

function authHeaders() {
  const token = localStorage.getItem('token');
  return token ? { 'Authorization': `Bearer ${token}` } : {};
}

export async function api(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const headers = { 'Content-Type': 'application/json', ...authHeaders(), ...options.headers };
  const res = await fetch(url, {
    credentials: 'include',
    headers,
    ...options,
  });
  if (res.status === 401) {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
  }
  if (!res.ok) {
    const err = new Error(`API ${res.status}: ${res.statusText}`);
    err.status = res.status;
    try { err.data = await res.json(); } catch {}
    throw err;
  }
  return res;
}

export async function apiText(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const headers = { ...authHeaders(), ...options.headers };
  const res = await fetch(url, { credentials: 'include', headers, ...options });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.text();
}

export async function apiBlob(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const headers = { ...authHeaders(), ...options.headers };
  const res = await fetch(url, { credentials: 'include', headers, ...options });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.blob();
}
