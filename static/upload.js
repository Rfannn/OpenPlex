// Upload page — file uploader + per-user file browser
const UP = window.location.origin;
let token = localStorage.getItem('token');
let currentUser = JSON.parse(localStorage.getItem('user') || 'null');
let _uploadQueue = [];
let _uploading = false;

if (!token) { window.location.href = '/login'; throw new Error('redirect'); }

document.addEventListener('DOMContentLoaded', () => {
  initUserMenu();
  initUploader();
  initBrowser();
});

function toast(msg, type = 'info', duration = 3500) {
  const c = document.getElementById('toastContainer');
  if (!c) return;
  const t = document.createElement('div');
  t.className = `toast toast-${type}`;
  t.innerHTML = `<span class="toast-msg">${msg}</span>`;
  c.appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; t.style.transform = 'translateX(60px)'; t.style.transition = 'all 0.3s'; setTimeout(() => t.remove(), 300); }, duration);
}

function initUserMenu() {
  const btn = document.getElementById('userMenuBtn');
  const drop = document.getElementById('userDropdown');
  if (btn && drop) {
    btn.onclick = (e) => { e.stopPropagation(); drop.classList.toggle('show'); };
    document.addEventListener('click', () => drop.classList.remove('show'));
  }
  if (currentUser) {
    const h = document.getElementById('userDropdownHeader');
    if (h) h.textContent = currentUser.display_name || currentUser.username || 'User';
    document.getElementById('userMenuBtn').textContent = (currentUser.display_name || currentUser.username || 'U').charAt(0).toUpperCase();
  }
  const logoutBtn = document.getElementById('logoutBtn');
  if (logoutBtn) logoutBtn.onclick = () => { localStorage.removeItem('token'); localStorage.removeItem('user'); window.location.href = '/login'; };
  const userDir = document.getElementById('uploadUserDir');
  if (userDir && currentUser) userDir.textContent = currentUser.username;
}

function initUploader() {
  const dropzone = document.getElementById('uploadDropzone');
  const input = document.getElementById('uploadInput');
  dropzone.addEventListener('click', () => input.click());
  dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.style.borderColor = 'var(--primary)'; });
  dropzone.addEventListener('dragleave', () => { dropzone.style.borderColor = ''; });
  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.style.borderColor = '';
    if (e.dataTransfer.files.length) queueFiles(e.dataTransfer.files);
  });
  input.addEventListener('change', () => {
    if (input.files.length) queueFiles(input.files);
    input.value = '';
  });
}

function queueFiles(files) {
  for (const f of files) _uploadQueue.push(f);
  processQueue();
}

async function processQueue() {
  if (_uploading) return;
  _uploading = true;
  const progressEl = document.getElementById('uploadProgress');
  progressEl.style.display = '';
  while (_uploadQueue.length) {
    const file = _uploadQueue.shift();
    await uploadFile(file);
  }
  _uploading = false;
  progressEl.style.display = 'none';
  toast('All uploads complete', 'success');
  loadFiles(_currentPath);
}

let _currentPath = '';

async function uploadFile(file, subpath = '') {
  const progressEl = document.getElementById('uploadProgress');
  const pct = Math.round((1 - _uploadQueue.length / (_uploadQueue.length + 1)) * 100);
  progressEl.innerHTML = `<div class="upload-progress-item"><span>${esc(file.name)}</span><div class="upload-progress-bar"><div class="upload-progress-fill" style="width:${pct}%"></div></div></div>`;

  const CHUNK_SIZE = 5 * 1024 * 1024; // 5MB
  const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
  const path = subpath || _currentPath;

  if (totalChunks <= 1) {
    const form = new FormData();
    form.append('file', file);
    form.append('path', path);
    try {
      const r = await fetch(API + '/api/user-upload', {
        method: 'POST',
        headers: { 'Authorization': 'Bearer ' + token },
        body: form,
      });
      if (!r.ok) { const d = await r.json(); throw new Error(d.detail || 'Upload failed'); }
    } catch (e) {
      toast('Upload failed: ' + e.message, 'error');
    }
  } else {
    // Chunked upload
    for (let i = 0; i < totalChunks; i++) {
      const start = i * CHUNK_SIZE;
      const end = Math.min(start + CHUNK_SIZE, file.size);
      const chunk = file.slice(start, end);
      const form = new FormData();
      form.append('file', chunk, file.name);
      form.append('path', path);
      form.append('chunk_index', String(i));
      form.append('total_chunks', String(totalChunks));
      try {
        const r = await fetch(API + '/api/user-upload/chunk', {
          method: 'POST',
          headers: { 'Authorization': 'Bearer ' + token },
          body: form,
        });
        if (!r.ok) throw new Error('Chunk upload failed');
        const pct2 = Math.round(((i + 1) / totalChunks) * 100);
        progressEl.innerHTML = `<div class="upload-progress-item"><span>${esc(file.name)} (chunk ${i+1}/${totalChunks})</span><div class="upload-progress-bar"><div class="upload-progress-fill" style="width:${pct2}%"></div></div></div>`;
      } catch (e) {
        toast('Chunk upload failed: ' + e.message, 'error');
        break;
      }
    }
  }
}

// ── File browser for Uploads ──
function initBrowser() {
  document.getElementById('uploadRefreshBtn').onclick = () => loadFiles(_currentPath);
  document.getElementById('uploadNewFolderBtn').onclick = () => {
    const name = prompt('Folder name:');
    if (name && name.trim()) createFolder(name.trim());
  };
  loadFiles('');
}

async function loadFiles(subpath) {
  _currentPath = subpath || '';
  const grid = document.getElementById('uploadGrid');
  grid.innerHTML = '<div class="lib-loader"><span class="icon-lg">spinner</span><p>Loading...</p></div>';
  try {
    const base = 'Uploads/' + (currentUser ? currentUser.username : '');
    const browsePath = subpath ? base + '/' + subpath : base;
    const r = await fetch(API + '/api/browse/' + encodeURIComponent(browsePath), {
      headers: { 'Authorization': 'Bearer ' + token },
    });
    const d = await r.json();
    if (!d.success) throw new Error(d.detail || 'Browse failed');
    renderFiles(d.items || []);
  } catch (e) {
    grid.innerHTML = '<div class="lib-empty"><p>Failed to load files: ' + e.message + '</p></div>';
  }
}

function renderFiles(entries) {
  const grid = document.getElementById('uploadGrid');
  const bread = document.getElementById('uploadBreadcrumb');
  // Breadcrumb
  const parts = _currentPath ? _currentPath.split('/') : [];
  let bc = '<a href="#" class="up-bc-link" data-path="">Uploads/' + esc(currentUser ? currentUser.username : '') + '</a>';
  let acc = '';
  parts.forEach((p, i) => {
    acc += (i ? '/' : '') + p;
    bc += ' <span style="color:var(--text-muted)">/</span> <a href="#" class="up-bc-link" data-path="' + acc + '">' + esc(p) + '</a>';
  });
  bread.innerHTML = bc;
  bread.querySelectorAll('.up-bc-link').forEach(el => {
    el.onclick = (e) => { e.preventDefault(); loadFiles(el.dataset.path); };
  });

  if (!entries.length) {
    grid.innerHTML = '<div class="lib-empty"><p>No files in this folder.</p><p>Drop files above to upload.</p></div>';
    return;
  }
  grid.innerHTML = '';
  entries.forEach(e => {
    const el = document.createElement('div');
    el.className = 'up-file-item';
    const isDir = e.type === 'directory';
    el.innerHTML = `
      <div class="up-file-icon">${isDir ? '📁' : '📄'}</div>
      <div class="up-file-info">
        <div class="up-file-name">${esc(e.name)}</div>
        <div class="up-file-meta">${isDir ? 'Folder' : formatSize(e.size)}</div>
      </div>
      <button class="up-file-del" data-path="${esc(e.path || e.name)}" title="Delete">&times;</button>
    `;
    if (isDir) {
      el.querySelector('.up-file-info').onclick = () => loadFiles(_currentPath ? _currentPath + '/' + e.name : e.name);
    } else {
      el.querySelector('.up-file-info').onclick = () => {
        window.open('/api/media/' + encodeURIComponent(e.path), '_blank');
      };
    }
    const delBtn = el.querySelector('.up-file-del');
    delBtn.onclick = async (ev) => {
      ev.stopPropagation();
      if (!confirm('Delete "' + e.name + '"?')) return;
      try {
        const r = await fetch(API + '/api/user-upload?path=' + encodeURIComponent(_currentPath ? _currentPath + '/' + e.name : e.name), {
          method: 'DELETE',
          headers: { 'Authorization': 'Bearer ' + token },
        });
        if (!r.ok) throw new Error('Delete failed');
        toast('Deleted', 'success');
        loadFiles(_currentPath);
      } catch (err) {
        toast('Delete failed: ' + err.message, 'error');
      }
    };
    grid.appendChild(el);
  });
}

async function createFolder(name) {
  try {
    const base = 'Uploads/' + (currentUser ? currentUser.username : '');
    const folderPath = _currentPath ? base + '/' + _currentPath + '/' + name : base + '/' + name;
    const r = await fetch(API + '/api/browse/mkdir', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
      body: JSON.stringify({ path: '/' + folderPath }),
    });
    if (!r.ok) throw new Error('Create folder failed');
    toast('Folder created', 'success');
    loadFiles(_currentPath);
  } catch (e) {
    toast('Failed: ' + e.message, 'error');
  }
}

function formatSize(bytes) {
  if (!bytes) return '';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  let size = bytes;
  while (size >= 1024 && i < units.length - 1) { size /= 1024; i++; }
  return size.toFixed(1) + ' ' + units[i];
}

function esc(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

// Shorthand without depending on API constant
const API = window.location.origin;