const API = window.location.origin;
let token = localStorage.getItem('token');
let currentUser = JSON.parse(localStorage.getItem('user') || 'null');
let currentMediaList = [];
let currentMediaIndex = 0;
let currentView = 'grid';
let currentPath = '';
let allItems = [];
let historyInterval = null;
let ctxItem = null;

const BROWSER_VIDEO = ['mp4', 'webm', 'ogv'];

const $ = (id) => document.getElementById(id);
const fileListEl = $('fileList');
const currentPathEl = $('currentPath');
const backButton = $('backButton');
const searchToggle = $('searchToggle');
const searchContainer = $('searchContainer');
const searchInput = $('searchInput');
const clearSearch = $('clearSearch');
const searchResults = $('searchResults');
const gridViewBtn = $('gridViewBtn');
const listViewBtn = $('listViewBtn');
const sortSelect = $('sortSelect');
const modal = $('mediaModal');
const viewerContainer = $('viewerContainer');
const prevBtn = $('prevBtn');
const nextBtn = $('nextBtn');
const mediaInfo = $('mediaInfo');
const downloadBtn = $('downloadBtn');
const userMenuBtn = $('userMenuBtn');
const userDropdown = $('userDropdown');
const logoutBtn = $('logoutBtn');
const contextMenu = $('contextMenu');
const uploadOverlay = $('uploadOverlay');
const fileInput = $('fileInput');
const renameDialog = $('renameDialog');
const renameInput = $('renameInput');
const folderNameInput = $('folderNameInput');
const newFolderDialog = $('newFolderDialog');
const infoPanel = $('infoPanel');
const infoContent = $('infoContent');
const diskInfo = $('diskInfo');

if (!token) { window.location.href = '/login'; throw new Error('redirect'); }

function initIcons() {
  document.querySelectorAll('[class*="icon-"]').forEach(el => {
    const name = el.textContent.trim();
    const cls = el.className;
    const size = cls.includes('icon-sm') ? 16 : cls.includes('icon-lg') ? 32 : 20;
    el.outerHTML = svg(name, size);
  });
  const map = {
    backButton: 'arrow-left', searchToggle: 'search', uploadToggle: 'upload',
    newFolderBtn: 'folder-plus',
    prevBtn: 'chevron-left', nextBtn: 'chevron-right', downloadBtn: 'download',
  };
  for (const [id, icon] of Object.entries(map)) {
    const el = $(id);
    if (el) {
      const label = id === 'gridViewBtn' ? ' Grid' : id === 'listViewBtn' ? ' List' : '';
      el.innerHTML = svg(icon.replace(/_.*$/, ''), 18) + label;
    }
  }
  const clearBtn = $('clearSearch');
  if (clearBtn) clearBtn.innerHTML = '&times;';
}
initIcons();

if (currentUser) {
  userMenuBtn.textContent = (currentUser.display_name || currentUser.username)[0].toUpperCase();
  const header = document.getElementById('userDropdownHeader');
  if (header) header.textContent = currentUser.display_name || currentUser.username;
}
userMenuBtn.addEventListener('click', (e) => { e.stopPropagation(); userDropdown.classList.toggle('show'); });
document.addEventListener('click', (e) => { if (!e.target.closest('.user-menu')) userDropdown.classList.remove('show'); });
logoutBtn.addEventListener('click', () => { localStorage.removeItem('token'); localStorage.removeItem('user'); window.location.href = '/login'; });

// Highlight active nav link based on current URL
(function highlightNav() {
  const nav = document.getElementById('mainNav');
  if (!nav) return;
  const path = window.location.pathname;
  nav.querySelectorAll('.nav-link').forEach(link => {
    const page = link.dataset.page;
    const href = link.getAttribute('href');
    if (href === path || (page && path.startsWith('/' + page)) || (path === '/' && (!page || page === 'files'))) {
      link.classList.add('active');
    } else {
      link.classList.remove('active');
    }
  });
})();

// Mobile: toggle sub-menus on click instead of hover
(function mobileNav() {
  if (window.innerWidth > 768) return;
  const nav = document.getElementById('mainNav');
  if (!nav) return;
  nav.querySelectorAll('.nav-link').forEach(link => {
    const sub = link.querySelector('.nav-sub');
    if (!sub) return;
    link.addEventListener('click', function(e) {
      if (link.getAttribute('href') && link.getAttribute('href') !== '#') return;
      e.preventDefault();
      const wasOpen = link.classList.contains('nav-sub-open');
      nav.querySelectorAll('.nav-link.nav-sub-open').forEach(l => l.classList.remove('nav-sub-open'));
      if (!wasOpen) link.classList.add('nav-sub-open');
    });
  });
})();

async function api(path, opts = {}) {
  const headers = { ...opts.headers };
  if (token && !headers['Authorization']) headers['Authorization'] = `Bearer ${token}`;
  const r = await fetch(API + path, { ...opts, headers });
  if (r.status === 401) { localStorage.removeItem('token'); localStorage.removeItem('user'); window.location.href = '/login'; }
  return r;
}

function toast(msg, type = 'success') {
  const container = $('toastContainer');
  if (!container) return;
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  const icons = { success: 'check', error: 'exclamation-circle', info: 'info-circle' };
  t.innerHTML = `${svg(icons[type] || icons.info, 16)} ${esc(msg)}`;
  container.appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; t.style.transform = 'translateX(60px)'; t.style.transition = 'all 0.3s'; setTimeout(() => t.remove(), 300); }, 3500);
}

function svg(name, size = 16) {
  const paths = {
    'folder': 'M2 6a2 2 0 012-2h4l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H4a2 2 0 01-2-2V6z',
    'film': 'M4 3a2 2 0 00-2 2v14a2 2 0 002 2h16a2 2 0 002-2V5a2 2 0 00-2-2H4zm3 2h2v2H7V5zm4 0h2v2h-2V5zm4 0h2v2h-2V5zM3 9h2v2H3V9zm4 0h2v2H7V9zm4 0h2v2h-2V9zm4 0h2v2h-2V9zM3 13h2v2H3v-2zm4 0h2v2H7v-2zm4 0h2v2h-2v-2zm4 0h2v2h-2v-2z',
    'music': 'M9 18V5l12-2v13M9 18c0 1.657-1.343 3-3 3s-3-1.343-3-3 1.343-3 3-3 3 1.343 3 3zM21 16c0 1.657-1.343 3-3 3s-3-1.343-3-3 1.343-3 3-3 3 1.343 3 3z',
    'image': 'M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z',
    'file': 'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z',
    'search': 'M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z',
    'th': 'M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z',
    'list': 'M4 6h16M4 12h16M4 18h16',
    'chevron-left': 'M15 19l-7-7 7-7',
    'chevron-right': 'M9 5l7 7-7 7',
    'download': 'M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4',
    'play': 'M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664zM21 12a9 9 0 11-18 0 9 9 0 0118 0z',
    'photo-video': 'M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z',
    'images': 'M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z',
    'arrow-left': 'M10 19l-7-7m0 0l7-7m-7 7h18',
    'exclamation-triangle': 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z',
    'folder-open': 'M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z',
    'spinner': 'M12 2a10 10 0 0110 10',
    'check': 'M5 13l4 4L19 7',
    'exclamation-circle': 'M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
    'info-circle': 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
    'sign-out': 'M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1',
    'pause': 'M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z',
    'clock': 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z',
    'trash': 'M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16',
    'times': 'M6 18L18 6M6 6l12 12',
    'upload': 'M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-7-8V4m0 0L7 8m5-4l5 4m0 0H7',
    'edit': 'M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z',
    'folder-plus': 'M9 13h6m-3-3v6m-5 6h10a2 2 0 002-2V8a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2v11a2 2 0 002 2z',
    'move': 'M8 17l4 4 4-4m-4-5v9M12 7l-4 4 4-4 4 4m-4-4V2',
    'copy': 'M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z',
    'zip': 'M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4',
    'caption': 'M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z',
  };
  const d = paths[name] || paths['file'];
  return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="${d}"/></svg>`;
}

function showSkeleton(count = 8) {
  const view = currentView || 'grid';
  const el = fileListEl;
  el.className = `file-list loading-skeleton ${view}-view`;
  let html = '';
  if (view === 'grid') {
    for (let i = 0; i < count; i++)
      html += `<div class="skeleton-card"><div class="skeleton skeleton-thumb-square"></div><div class="skeleton skeleton-text" style="margin-top:6px;"></div><div class="skeleton skeleton-text-short"></div></div>`;
  } else {
    for (let i = 0; i < count; i++)
      html += `<div class="skeleton-row"><div class="skeleton skeleton-thumb-square"></div><div class="skeleton-row-content"><div class="skeleton skeleton-text"></div><div class="skeleton skeleton-text-short"></div></div></div>`;
  }
  el.innerHTML = html;
}

async function loadDirectory(subpath = '', refresh = false) {
  try {
    showSkeleton();
    const r = await api(`/api/browse/${encodeURIComponent(subpath)}?refresh=${refresh}`);
    const data = await r.json();
    if (!data.success) throw new Error(data.error);
    currentPath = data.current_path;
    currentPathEl.textContent = currentPath || '/';
    backButton.style.display = (data.parent_path !== undefined && currentPath) ? 'flex' : 'none';
    backButton.onclick = () => loadDirectory(data.parent_path);
    allItems = data.items;
    displayItems(data.items);
    if (data.disk) {
      const pct = data.disk.used / data.disk.total * 100;
      diskInfo.textContent = `\u00b7 ${fmtSize(data.disk.free)} free`;
      diskInfo.title = `Disk: ${fmtSize(data.disk.used)} used / ${fmtSize(data.disk.total)} total (${pct.toFixed(1)}%)`;
    }
    // Fetch covers for video files
    const videoItems = data.items.filter(i => !i.is_dir && i.type === 'video');
    if (videoItems.length > 0) {
      const paths = videoItems.map(i => i.path);
      try {
        const cr = await api(`/api/file/covers?${paths.map(p => 'paths=' + encodeURIComponent(p)).join('&')}`, { method: 'POST' });
        const cd = await cr.json();
        if (cd.success && cd.covers) {
          const thumbnails = fileListEl.querySelectorAll('.file-item');
          videoItems.forEach(item => {
            const cover = cd.covers[item.path];
            if (cover) {
              for (const el of thumbnails) {
                if (el.dataset.path === item.path) {
                  const thumb = el.querySelector('.file-thumbnail');
                  if (thumb) thumb.innerHTML = `<img src="${cover}" alt="" loading="lazy" style="width:100%;height:100%;object-fit:cover;" onerror="this.style.display='none'">`;
                  break;
                }
              }
            }
          });
        }
      } catch (_) {}
    }
  } catch (err) {
    fileListEl.innerHTML = `<div class="loading">${svg('exclamation-triangle', 32)}<p>Error: ${err.message}</p></div>`;
  }
}

function displayItems(items) {
  if (!items || items.length === 0) {
    fileListEl.innerHTML = `<div class="loading">${svg('folder-open', 32)}<p>Empty directory</p></div>`;
    return;
  }
  fileListEl.innerHTML = '';
  fileListEl.className = `file-list ${currentView}-view`;
  const frag = document.createDocumentFragment();
  items.forEach((item, i) => {
    const el = createItemElement(item);
    el.style.animationDelay = `${i * 30}ms`;
    frag.appendChild(el);
  });
  fileListEl.appendChild(frag);
}

function parseSeasonEpisode(name) {
  const patterns = [
    /S(\d{1,2})E(\d{1,3})/i,
    /s(\d{1,2})\s*[-.\s]?e(\d{1,3})/i,
    /(\d{1,2})x(\d{2})/i,
  ];
  for (const p of patterns) {
    const m = name.match(p);
    if (m) {
      const season = parseInt(m[1], 10);
      const episode = parseInt(m[2], 10);
      return {season, episode};
    }
  }
  return null;
}

function parseQuality(name) {
  if (/\b4k\b/i.test(name)) return '4K';
  if (/\b2160p\b/i.test(name)) return '4K';
  if (/\b1080p\b/i.test(name)) return '1080p';
  if (/\b720p\b/i.test(name)) return '720p';
  if (/\b480p\b/i.test(name)) return '480p';
  return null;
}

function createItemElement(item) {
  const div = document.createElement('div');
  div.className = 'file-item';
  div.dataset.path = item.path;
  let thumb = '';
  if (item.is_dir) {
    thumb = svg('folder', 40);
  } else if (item.type === 'video') {
    thumb = svg('film', 32);
  } else if (item.type === 'audio') {
    thumb = svg('music', 32);
  } else if (item.type === 'image') {
    thumb = `<div class="thumbnail-loader" data-path="${encodeURIComponent(item.path)}">${svg('image', 32)}</div>`;
  } else if (item.type === 'text') {
    thumb = svg('file', 32);
  } else {
    thumb = svg('file', 32);
  }
  let badges = '';
  if (!item.is_dir) {
    const cat = item.category;
    const year = item.year;
    const genre = item.genre;
    const quality = parseQuality(item.name);
    const se = parseSeasonEpisode(item.name);
    const catColors = {movie: 'type-movie', series: 'type-series', anime: 'type-series', documentary: 'type-series'};
    let badgeParts = [];
    if (cat) badgeParts.push(['cat', catColors[cat] || '', cat]);
    if (year) badgeParts.push(['year', '', year]);
    if (quality) badgeParts.push(['qual', 'rating', quality]);
    if (se) badgeParts.push(['se', '', `S${se.season}·E${se.episode}`]);
    if (badgeParts.length > 0) {
      badges = '<div class="file-badges">' + badgeParts.map(([t, cls, txt]) =>
        `<span class="dl-badge ${cls}" data-type="${t}">${esc(txt)}</span>`
      ).join('') + '</div>';
    }
  }
  div.innerHTML = `
    <div class="file-thumbnail">${thumb}</div>
    <div class="file-info">
      <div class="file-name">${esc(item.name)}</div>
      <div class="file-type">${item.is_dir ? 'Folder' : item.type}${item.size ? ' · ' + fmtSize(item.size) : ''}</div>
      ${badges}
    </div>`;

  div.addEventListener('click', (e) => {
    if (e.target.closest('.file-item-action')) return;
    if (item.is_dir) loadDirectory(item.path);
    else if (item.is_media) openMedia(item.path);
    else if (item.type === 'text') openTextFile(item.path, item.name);
  });

  div.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    ctxItem = item;
    showContextMenu(e.clientX, e.clientY, item);
  });
  // Mobile long-press for context menu
  (function() {
    let longTimer = null;
    div.addEventListener('touchstart', (e) => {
      longTimer = setTimeout(() => {
        longTimer = null;
        ctxItem = item;
        showContextMenu(e.touches[0].clientX, e.touches[0].clientY, item);
      }, 500);
    }, { passive: true });
    div.addEventListener('touchend', () => { if (longTimer) { clearTimeout(longTimer); longTimer = null; } }, { passive: true });
    div.addEventListener('touchmove', () => { if (longTimer) { clearTimeout(longTimer); longTimer = null; } }, { passive: true });
  })();

  return div;
}

// ── Context Menu ────────────────────────────────

function showContextMenu(x, y, item) {
  const playBtn = $('ctxPlay');
  const downloadBtn_ = $('ctxDownload');
  const renameBtn = $('ctxRename');
  const deleteBtn = $('ctxDelete');
  const infoBtn = $('ctxInfo');
  const zipBtn = $('ctxDownloadZip');

  playBtn.style.display = item.is_media ? 'flex' : 'none';
  downloadBtn_.style.display = !item.is_dir ? 'flex' : 'none';
  renameBtn.style.display = 'flex';
  deleteBtn.style.display = 'flex';
  infoBtn.style.display = 'flex';
  zipBtn.style.display = item.is_dir ? 'flex' : 'none';

  contextMenu.style.left = `${Math.min(x, window.innerWidth - 200)}px`;
  contextMenu.style.top = `${Math.min(y, window.innerHeight - 300)}px`;
  contextMenu.classList.add('show');
}

function hideContextMenu() { contextMenu.classList.remove('show'); }

// Context menu actions
$('ctxPlay')?.addEventListener('click', () => {
  if (ctxItem && ctxItem.is_media) openMedia(ctxItem.path);
  hideContextMenu();
});
$('ctxDownload')?.addEventListener('click', () => {
  if (ctxItem && !ctxItem.is_dir) {
    const a = document.createElement('a');
    a.href = `/api/download/${encodeURIComponent(ctxItem.path)}`;
    a.download = ctxItem.name;
    a.click();
  }
  hideContextMenu();
});
$('ctxRename')?.addEventListener('click', () => {
  if (ctxItem) {
    renameInput.value = ctxItem.name;
    renameDialog.style.display = 'flex';
    renameInput.focus();
    renameInput.select();
    renameInput.dataset.path = ctxItem.path;
  }
  hideContextMenu();
});

$('ctxSuggestRename')?.addEventListener('click', async () => {
  if (ctxItem && !ctxItem.is_dir) {
    const ext = ctxItem.name.includes('.') ? '.' + ctxItem.name.split('.').pop() : '';
    let suggestion = '';
    try {
      const r = await api('/api/ai-rename-suggest?filename=' + encodeURIComponent(ctxItem.name));
      const d = await r.json();
      suggestion = (d.suggestion || '').trim();
      if (suggestion && !suggestion.includes('.')) suggestion += ext;
    } catch {}
    if (!suggestion) {
      const se = parseSeasonEpisode(ctxItem.name);
      const name = ctxItem.name
        .replace(/\.[^.]+$/, '')
        .replace(/\b(19|20)\d{2}\b/, '')
        .replace(/S\d{1,2}E\d{1,3}/i, se ? `S${String(se.season).padStart(2,'0')}E${String(se.episode).padStart(2,'0')}` : '')
        .replace(/\.(WEB[-_.]?DL|BluRay|HDRip|WEBRip|WEB[-_.]?Rip|HDTV)/i, '')
        .replace(/[.\-_.720p480p2160p4K].*$/i, '')
        .replace(/\s*\.\s*/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
      suggestion = name + ext;
    }
    renameInput.value = suggestion;
    renameDialog.style.display = 'flex';
    renameInput.focus();
    renameInput.select();
    renameInput.dataset.path = ctxItem.path;
  }
  hideContextMenu();
});
$('ctxDelete')?.addEventListener('click', async () => {
  if (ctxItem && confirm(`Delete "${ctxItem.name}"?`)) {
    try {
      const r = await api(`/api/delete?path=${encodeURIComponent(ctxItem.path)}`, { method: 'DELETE' });
      const d = await r.json();
      if (d.success) { toast('Deleted'); loadDirectory(currentPath, true); }
      else toast(d.error || 'Delete failed', 'error');
    } catch (e) { toast('Delete failed', 'error'); }
  }
  hideContextMenu();
});
$('ctxInfo')?.addEventListener('click', async () => {
  if (ctxItem) {
    await showFileInfo(ctxItem.path);
  }
  hideContextMenu();
});
$('ctxDownloadZip')?.addEventListener('click', () => {
  if (ctxItem && ctxItem.is_dir) {
    window.open(`/api/download-zip?path=${encodeURIComponent(ctxItem.path)}`, '_blank');
  }
  hideContextMenu();
});

document.addEventListener('click', (e) => {
  if (!e.target.closest('.context-menu')) hideContextMenu();
});

// ── Upload ──────────────────────────────────────

$('uploadToggle')?.addEventListener('click', () => {
  uploadOverlay.style.display = 'flex';
});

uploadOverlay?.addEventListener('click', (e) => {
  if (e.target === uploadOverlay) uploadOverlay.style.display = 'none';
});

uploadOverlay?.addEventListener('dragover', (e) => {
  e.preventDefault();
  uploadOverlay.querySelector('.upload-dropzone').classList.add('drag-over');
});
uploadOverlay?.addEventListener('dragleave', () => {
  uploadOverlay.querySelector('.upload-dropzone').classList.remove('drag-over');
});
uploadOverlay?.addEventListener('drop', (e) => {
  e.preventDefault();
  uploadOverlay.querySelector('.upload-dropzone').classList.remove('drag-over');
  if (e.dataTransfer.files.length) handleUploadFiles(e.dataTransfer.files);
});

$('uploadToggle')?.addEventListener('click', () => {
  fileInput.click();
});
uploadOverlay?.querySelector('.upload-dropzone')?.addEventListener('click', () => {
  fileInput.click();
});
fileInput?.addEventListener('change', () => {
  if (fileInput.files.length) handleUploadFiles(fileInput.files);
});

async function handleUploadFiles(files) {
  const dz = uploadOverlay.querySelector('.upload-dropzone');
  dz.innerHTML = `<div class="upload-progress"><div class="dl-progress"><div class="dl-progress-bar" style="width:0%"></div></div><p>Uploading 0/${files.length}...</p></div>`;
  let completed = 0;
  for (const file of files) {
    try {
      const form = new FormData();
      form.append('file', file);
      const r = await api(`/api/upload/${encodeURIComponent(currentPath)}`, { method: 'POST', body: form });
      const d = await r.json();
      if (d.success) completed++;
    } catch (e) { toast(`Failed: ${file.name}`, 'error'); }
    const pct = (completed / files.length) * 100;
    dz.querySelector('.dl-progress-bar').style.width = `${pct}%`;
    dz.querySelector('p').textContent = `Uploading ${completed}/${files.length}...`;
  }
  dz.innerHTML = `<span class="icon-lg" style="color:var(--success)">${svg('check', 32)}</span><h3>Uploaded ${completed}/${files.length} files</h3><p>Click to close</p>`;
  toast(`Uploaded ${completed} files`);
  loadDirectory(currentPath, true);
}

// ── New Folder ──────────────────────────────────

$('newFolderBtn')?.addEventListener('click', () => {
  folderNameInput.value = '';
  newFolderDialog.style.display = 'flex';
  folderNameInput.focus();
});
function closeNewFolder() { newFolderDialog.style.display = 'none'; }
window.closeNewFolder = closeNewFolder;
$('folderCreateConfirm')?.addEventListener('click', async () => {
  const name = folderNameInput.value.trim();
  if (!name) return;
  try {
    const r = await api(`/api/mkdir?path=${encodeURIComponent(currentPath)}&name=${encodeURIComponent(name)}`, { method: 'POST' });
    const d = await r.json();
    if (d.success) { toast('Folder created'); loadDirectory(currentPath, true); closeNewFolder(); }
    else toast(d.error || 'Failed', 'error');
  } catch (e) { toast('Failed to create folder', 'error'); }
});
folderNameInput?.addEventListener('keydown', (e) => { if (e.key === 'Enter') $('folderCreateConfirm').click(); if (e.key === 'Escape') closeNewFolder(); });

// ── Rename ──────────────────────────────────────

function closeRename() { renameDialog.style.display = 'none'; }
window.closeRename = closeRename;
$('renameConfirm')?.addEventListener('click', async () => {
  const path = renameInput.dataset.path;
  const newName = renameInput.value.trim();
  if (!path || !newName) return;
  try {
    const r = await api(`/api/rename?path=${encodeURIComponent(path)}&new_name=${encodeURIComponent(newName)}`, { method: 'PUT' });
    const d = await r.json();
    if (d.success) { toast('Renamed'); loadDirectory(currentPath, true); closeRename(); }
    else toast(d.error || 'Failed', 'error');
  } catch (e) { toast('Rename failed', 'error'); }
});
renameInput?.addEventListener('keydown', (e) => { if (e.key === 'Enter') $('renameConfirm').click(); if (e.key === 'Escape') closeRename(); });

// ── File Info ───────────────────────────────────

async function showFileInfo(path) {
  try {
    const r = await api(`/api/file-info/${encodeURIComponent(path)}`);
    const d = await r.json();
    if (!d.success) { toast('Info not available', 'error'); return; }
    const info = d.info;
    const rows = [
      ['Name', info.name],
      ['Path', info.path],
      ['Type', info.is_dir ? 'Directory' : info.type],
      ['Size', fmtSize(info.size)],
      ['Modified', new Date(info.modified * 1000).toLocaleString()],
      ['Created', new Date(info.created * 1000).toLocaleString()],
    ];
    if (info.ext) rows.splice(3, 0, ['Extension', info.ext.toUpperCase()]);
    infoContent.innerHTML = rows.map(([l, v]) =>
      `<div class="info-row"><span class="info-label">${l}</span><span class="info-value">${esc(String(v))}</span></div>`
    ).join('');
    infoPanel.style.display = 'block';
  } catch (e) { toast('Failed to get info', 'error'); }
}
function closeInfo() { infoPanel.style.display = 'none'; }
window.closeInfo = closeInfo;

// ── Text Preview ────────────────────────────────

async function openTextFile(path, name) {
  try {
    const r = await api(`/api/media/${encodeURIComponent(path)}`);
    const text = await r.text();
    viewerContainer.innerHTML = `
      <div style="width:100%;max-height:70vh;overflow:auto;background:var(--bg-elevated);border-radius:var(--radius-md);padding:20px;">
        <pre style="font-family:monospace;font-size:0.8rem;line-height:1.5;white-space:pre-wrap;word-break:break-word;color:var(--text);margin:0;">${esc(text.slice(0, 50000))}</pre>
        ${text.length > 50000 ? '<p style="color:var(--text-muted);font-size:0.75rem;margin-top:12px;">File truncated at 50KB for preview</p>' : ''}
      </div>`;
    mediaInfo.textContent = name;
    downloadBtn.href = `/api/download/${encodeURIComponent(path)}`;
    modal.style.display = 'block';
    document.body.style.overflow = 'hidden';
  } catch (e) { toast('Failed to open file', 'error'); }
}

// ── Media Viewer (existing) ─────────────────────

async function openMedia(filePath) {
  try {
    const r = await api(`/api/browse/${encodeURIComponent(currentPath)}`);
    const data = await r.json();
    if (data.success) {
      currentMediaList = data.items.filter(i => i.is_media);
      currentMediaIndex = currentMediaList.findIndex(i => i.path === filePath);
      window.currentMediaList = currentMediaList;
      window.currentMediaIndex = currentMediaIndex;
      if (currentMediaIndex !== -1) {
        const showModal = displayMedia(currentMediaIndex);
        if (showModal !== false) {
          modal.style.display = 'block';
          document.body.style.overflow = 'hidden';
        }
      }
    }
  } catch (err) {
    toast('Failed to open media', 'error');
  }
}

function displayMedia(index) {
  if (index < 0 || index >= currentMediaList.length) return;
  const media = currentMediaList[index];
  const fp = media.path;
  const fn = media.name;
  const ext = (fn.split('.').pop() || '').toLowerCase();
  const fu = `/api/stream?path=${encodeURIComponent(fp)}`;

  if (media.type === 'image') {
    viewerContainer.innerHTML = `<img src="/api/media/${encodeURIComponent(fp)}" alt="${esc(fn)}" style="max-width:100%;max-height:70vh;object-fit:contain;">`;
  } else if (media.type === 'video') {
    const isTranscode = !BROWSER_VIDEO.includes(ext);
    const videoUrl = isTranscode ? `/api/stream?path=${encodeURIComponent(fp)}&transcode=true` : fu;
    if (typeof Player !== 'undefined') {
      Player.play(videoUrl, esc(fn), fmtSize(media.size), fp);
    }
    return false;
  } else if (media.type === 'audio') {
    if (typeof Player !== 'undefined') {
      Player.play(fu, esc(fn), fmtSize(media.size), fp);
    }
    return false;
  }
  mediaInfo.textContent = `${index + 1} / ${currentMediaList.length}`;
  downloadBtn.href = `/api/download/${encodeURIComponent(fp)}`;
  checkResume(fp);
}

window.tryPlayAnyway = function(encodedPath) {
  const fu = `/api/media/${decodeURIComponent(encodedPath)}`;
  viewerContainer.innerHTML = `
    <div style="width:100%;text-align:center">
      <video id="videoPlayer" controls autoplay style="width:100%;max-height:70vh;background:#000;border-radius:12px;" preload="metadata">
        <source src="${fu}">
      </video>
      <p style="color:var(--text-muted);font-size:0.75rem;margin-top:8px;">If this doesn't work, download the file.</p>
    </div>`;
};

async function checkResume(fp) {
  try {
    const r = await api(`/api/history/${encodeURIComponent(fp)}`);
    const d = await r.json();
    if (d.success && d.found && !d.completed && d.position_sec > 30) {
      const btn = document.createElement('button');
      btn.className = 'btn btn-primary';
      btn.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);z-index:10;padding:12px 24px;font-size:1rem;';
      btn.innerHTML = `${svg('play', 16)} Resume at ${fmtTime(d.position_sec)}`;
      btn.addEventListener('click', () => {
        const v = document.getElementById('videoPlayer');
        if (v) { v.currentTime = d.position_sec; v.play(); }
        btn.remove();
      });
      viewerContainer.appendChild(btn);
    }
  } catch (e) {}
}



function previousMedia() { if (currentMediaIndex > 0) { currentMediaIndex--; window.currentMediaIndex = currentMediaIndex; displayMedia(currentMediaIndex); } }
function nextMedia() { if (currentMediaIndex < currentMediaList.length - 1) { currentMediaIndex++; window.currentMediaIndex = currentMediaIndex; displayMedia(currentMediaIndex); } }

function closeModal() {
  modal.style.display = 'none';
  document.body.style.overflow = 'auto';
  if (historyInterval) { clearInterval(historyInterval); historyInterval = null; }
}

// ── Search ──────────────────────────────────────

let searchTimeout;
async function searchFiles(query) {
  if (query.length < 2) { searchResults.innerHTML = ''; return; }
  try {
    const r = await api(`/api/search?q=${encodeURIComponent(query)}`);
    const d = await r.json();
    if (d.success && d.results.length > 0) {
      searchResults.innerHTML = d.results.map(r => `
        <div class="search-result-item" data-path="${r.path}">
          ${svg(r.type === 'image' ? 'image' : r.type === 'video' ? 'film' : 'music', 16)}
          ${esc(r.name)}
        </div>`).join('');
      searchResults.querySelectorAll('.search-result-item').forEach(el => {
        el.addEventListener('click', () => {
          const p = el.dataset.path;
          const parent = p.substring(0, p.lastIndexOf('/'));
          currentPath = parent;
          openMedia(p);
          searchContainer.style.display = 'none';
          searchInput.value = '';
          searchResults.innerHTML = '';
        });
      });
    }
  } catch (e) {}
}

// ── Sorting & View ──────────────────────────────

function sortItems(items, by) {
  const sorted = [...items];
  switch (by) {
    case 'name': sorted.sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase())); break;
    case 'date': sorted.sort((a, b) => (b.modified || 0) - (a.modified || 0)); break;
    case 'size': sorted.sort((a, b) => (b.size || 0) - (a.size || 0)); break;
    case 'type': sorted.sort((a, b) => a.type.localeCompare(b.type) || a.name.localeCompare(b.name)); break;
  }
  return sorted;
}

function setView(view) {
  currentView = view;
  loadDirectory(currentPath, true);
  gridViewBtn.classList.toggle('active', view === 'grid');
  listViewBtn.classList.toggle('active', view === 'list');
}

function esc(str) { const d = document.createElement('div'); d.textContent = str; return d.innerHTML; }
function fmtSize(bytes) {
  if (!bytes || bytes === 0) return '';
  const s = ['B','KB','MB','GB']; const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${s[i]}`;
}
function fmtTime(s) {
  const h = Math.floor(s / 3600); const m = Math.floor((s % 3600) / 60); const sec = Math.floor(s % 60);
  return h ? `${h}:${m.toString().padStart(2,'0')}:${sec.toString().padStart(2,'0')}` : `${m}:${sec.toString().padStart(2,'0')}`;
}

// ── Subtitles ────────────────────────────────────

function getSubSettings() {
  return {
    fontSize: parseInt(localStorage.getItem('subFontSize') || '100'),
    color: localStorage.getItem('subColor') || 'white',
    bg: localStorage.getItem('subBg') || 'black',
  };
}

function applySubSettings() {
  const size = document.getElementById('subFontSize')?.value || '100';
  const color = document.getElementById('subColor')?.value || 'white';
  const bg = document.getElementById('subBg')?.value || 'black';
  localStorage.setItem('subFontSize', size);
  localStorage.setItem('subColor', color);
  localStorage.setItem('subBg', bg);
  const video = document.getElementById('videoPlayer');
  if (!video) return;
  video.style.setProperty('--cue-font-size', (parseInt(size) / 100) + 'em');
  video.style.setProperty('--cue-color', color);
  video.style.setProperty('--cue-background-color', bg === 'transparent' ? 'transparent' : bg);
}

let subSettingsVisible = false;
function toggleSubSettings() {
  subSettingsVisible = !subSettingsVisible;
  const el = document.getElementById('subSettings');
  if (el) el.style.display = subSettingsVisible ? '' : 'none';
}




async function loadSubtitleFile(encodedPath) {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.srt,.vtt,.ass,.sub';
  input.onchange = async () => {
    const file = input.files[0];
    if (!file) return;
    const text = await file.text();
    const vtt = 'WEBVTT\n\n' + (file.name.endsWith('.vtt') ? text : text
      .replace(/\r\n/g, '\n')
      .replace(/(\d{2}:\d{2}:\d{2}),(\d{3})/g, '$1.$2'));
    const blob = new Blob([vtt], { type: 'text/vtt' });
    const url = URL.createObjectURL(blob);
    const video = document.getElementById('videoPlayer');
    if (video) {
      video.querySelectorAll('track').forEach(t => t.remove());
      const track = document.createElement('track');
      track.kind = 'subtitles';
      track.label = file.name;
      track.srclang = 'en';
      track.src = url;
      track.default = true;
      video.appendChild(track);
      document.getElementById('subStatus').textContent = `Loaded: ${file.name}`;
    }
  };
  input.click();
}

// ── VLC ──────────────────────────────────────────

function openInVlc(encodedPath) {
  const url = window.location.origin + '/api/media/' + encodedPath;
  const vlcUrl = 'vlc://' + url;
  // Try VLC protocol handler
  const a = document.createElement('a');
  a.href = vlcUrl;
  a.target = '_blank';
  a.click();
  // Also copy URL to clipboard as fallback
  navigator.clipboard.writeText(url).then(() => {
    toast('Media URL copied (VLC may need it pasted as "Open Network Stream")', 'info', 5000);
  }).catch(() => {});
}

// ── Event listeners ─────────────────────────────

searchToggle.addEventListener('click', () => {
  const v = searchContainer.style.display === 'block';
  searchContainer.style.display = v ? 'none' : 'block';
  if (!v) searchInput.focus();
});
clearSearch.addEventListener('click', () => { searchInput.value = ''; searchResults.innerHTML = ''; });
searchInput.addEventListener('input', (e) => { clearTimeout(searchTimeout); searchTimeout = setTimeout(() => searchFiles(e.target.value), 500); });
gridViewBtn.addEventListener('click', () => setView('grid'));
listViewBtn.addEventListener('click', () => setView('list'));
sortSelect.addEventListener('change', () => {
  allItems = sortItems(allItems, sortSelect.value);
  displayItems(allItems);
});
prevBtn.addEventListener('click', previousMedia);
nextBtn.addEventListener('click', nextMedia);
document.querySelector('.modal-close')?.addEventListener('click', closeModal);
window.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });
document.addEventListener('keydown', (e) => {
  if (modal.style.display === 'block') {
    if (e.key === 'ArrowLeft') previousMedia();
    if (e.key === 'ArrowRight') nextMedia();
    if (e.key === 'Escape') closeModal();
  }
  if (renameDialog.style.display === 'flex' && e.key === 'Escape') closeRename();
  if (newFolderDialog.style.display === 'flex' && e.key === 'Escape') closeNewFolder();
});

async function loadThumbnails() {
  document.querySelectorAll('.thumbnail-loader').forEach(async (el) => {
    const path = el.dataset.path;
    if (!path) return;
    try {
      const r = await api(`/api/thumbnail/${path}`);
      if (r.ok) {
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);
        el.innerHTML = `<img src="${url}" alt="" loading="lazy">`;
        setTimeout(() => URL.revokeObjectURL(url), 10000);
      }
    } catch (e) {}
  });
}

const thumbnailObserver = new MutationObserver(() => loadThumbnails());
thumbnailObserver.observe(fileListEl, { childList: true, subtree: true });

// AI health indicator polling
async function updateAiIndicator() {
  const el = document.getElementById('aiIndicator');
  if (!el) return;
  try {
    const r = await fetch('/api/ai-health');
    const d = await r.json();
    el.className = 'ai-indicator ' + (d.healthy ? 'on' : 'off');
    el.title = d.healthy ? 'AI running (' + d.categorized + ' files categorized)' : 'AI offline';
  } catch {
    el.className = 'ai-indicator off';
    el.title = 'AI unreachable';
  }
}
updateAiIndicator();
setInterval(updateAiIndicator, 15000);

loadDirectory('');
