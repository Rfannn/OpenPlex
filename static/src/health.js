import { api } from './api.js';

let healthInterval = null;

async function loadHealth() {
  try {
    const r = await api('/api/health/detailed');
    const data = await r.json();
    renderHealth(data);
  } catch (err) {
    document.getElementById('health-content').innerHTML = `
      <div class="health-error">
        <h2>Connection Error</h2>
        <p>Could not reach health endpoint: ${err.message}</p>
        <button class="glass-btn" onclick="location.reload()">Retry</button>
      </div>
    `;
  }
}

function renderHealth(data) {
  const checks = [
    { label: 'Database', key: 'database', icon: 'check' },
    { label: 'aria2 RPC', key: 'aria2', icon: 'download' },
    { label: 'Disk Usage', key: 'disk', icon: 'folder' },
    { label: 'Media Root', key: 'media_root', icon: 'film' },
    { label: 'Scrapers', key: 'scrapers', icon: 'sync' },
    { label: 'Uptime', key: 'uptime', icon: 'clock' },
  ];

  const container = document.getElementById('health-content');
  container.innerHTML = `
    <div class="health-grid">
      ${checks.map(c => {
        const check = data.checks?.[c.key];
        const ok = check?.status === 'ok' || check?.status === 'healthy' || check?.alive;
        return `
          <div class="health-card ${ok ? 'health-ok' : 'health-fail'}">
            <div class="health-card-header">
              <span class="health-indicator ${ok ? 'green' : 'red'}"></span>
              <h3>${c.label}</h3>
            </div>
            <div class="health-card-body">
              ${renderCheckDetails(c.key, check)}
            </div>
          </div>
        `;
      }).join('')}
    </div>
    ${data.timestamp ? `<div class="health-timestamp">Last updated: ${new Date(data.timestamp).toLocaleTimeString()}</div>` : ''}
  `;
}

function renderCheckDetails(key, check) {
  if (!check) return '<span class="text-muted">No data</span>';
  switch (key) {
    case 'database':
      return `
        <div class="health-detail">Connected: ${check.connected ? 'Yes' : 'No'}</div>
        ${check.query_time_ms ? `<div class="health-detail">Query time: ${check.query_time_ms}ms</div>` : ''}
      `;
    case 'aria2':
      return `
        <div class="health-detail">Running: ${check.alive ? 'Yes' : 'No'}</div>
        ${check.latency_ms ? `<div class="health-detail">Latency: ${check.latency_ms}ms</div>` : ''}
        ${check.version ? `<div class="health-detail">Version: ${check.version}</div>` : ''}
      `;
    case 'disk':
      return `
        <div class="health-detail">Total: ${formatBytes(check.total_bytes || check.total)}</div>
        <div class="health-detail">Used: ${formatBytes(check.used_bytes || check.used)} (${check.usage_pct || check.usage_percent}%)</div>
        <div class="health-detail">Free: ${formatBytes(check.free_bytes || check.free)}</div>
        <div class="health-bar">
          <div class="health-bar-fill" style="width:${check.usage_pct || check.usage_percent || 0}%"></div>
        </div>
      `;
    case 'media_root':
      return `
        <div class="health-detail">Path: ${check.path}</div>
        <div class="health-detail">Exists: ${check.exists ? 'Yes' : 'No'}</div>
        ${check.writable !== undefined ? `<div class="health-detail">Writable: ${check.writable ? 'Yes' : 'No'}</div>` : ''}
      `;
    case 'scrapers':
      if (!check.sources || !check.sources.length) return '<div class="health-detail">No scrapers configured</div>';
      return check.sources.map(s => `
        <div class="health-detail">
          <span class="health-indicator-small ${s.reachable ? 'green' : 'red'}"></span>
          ${s.name}: ${s.reachable ? 'OK' : 'Unreachable'}${s.latency_ms ? ` (${s.latency_ms}ms)` : ''}
        </div>
      `).join('');
    case 'uptime':
      return `
        <div class="health-detail">Server: ${check.server_uptime || 'N/A'}</div>
        <div class="health-detail">Python: ${check.python_version || 'N/A'}</div>
        <div class="health-detail">OS: ${check.os || 'N/A'}</div>
      `;
    default:
      return `<pre class="health-raw">${JSON.stringify(check, null, 2)}</pre>`;
  }
}

function formatBytes(bytes) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  let val = bytes;
  while (val >= 1024 && i < units.length - 1) { val /= 1024; i++; }
  return `${val.toFixed(1)} ${units[i]}`;
}

export function initHealth() {
  loadHealth();
  if (healthInterval) clearInterval(healthInterval);
  healthInterval = setInterval(loadHealth, 10000);
}

export function destroyHealth() {
  if (healthInterval) {
    clearInterval(healthInterval);
    healthInterval = null;
  }
}
