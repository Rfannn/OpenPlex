const API = window.location.origin;
let token = localStorage.getItem('token');
let currentUser = JSON.parse(localStorage.getItem('user') || 'null');
let _avatars = [];

if (!token) { window.location.href = '/login'; throw new Error('redirect'); }

document.addEventListener('DOMContentLoaded', () => {
  initUserMenu();
  loadProfile();
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
}

async function loadProfile() {
  try {
    const r = await fetch(API + '/api/auth/me', {
      headers: { 'Authorization': 'Bearer ' + token },
    });
    const user = await r.json();
    document.getElementById('profileDisplayName').textContent = user.display_name || user.username;
    document.getElementById('profileUsername').textContent = '@' + user.username;
    document.getElementById('profileDisplayNameInput').value = user.display_name || user.username;
    renderAvatarPreview(user.avatar || '', user.display_name || user.username);

    // Load avatars list
    const ar = await fetch(API + '/api/auth/avatars', {
      headers: { 'Authorization': 'Bearer ' + token },
    });
    const ad = await ar.json();
    _avatars = ad.avatars || [];
    renderAvatarGrid(user.avatar || '');
  } catch (e) {
    toast('Failed to load profile: ' + e.message, 'error');
  }

  document.getElementById('profileSaveBtn').onclick = saveProfile;
}

function renderAvatarPreview(selected, name) {
  const el = document.getElementById('profileAvatarPreview');
  if (selected) {
    el.textContent = '';
    el.style.background = '';
    const img = document.createElement('img');
    img.src = '/static/avatars/' + selected + '.svg';
    img.style.width = '100%';
    img.style.height = '100%';
    img.style.borderRadius = '50%';
    img.style.objectFit = 'cover';
    el.appendChild(img);
  } else {
    el.textContent = (name || '?').charAt(0).toUpperCase();
    el.style.background = 'var(--accent-gradient)';
  }
}

function renderAvatarGrid(selected) {
  const grid = document.getElementById('profileAvatarGrid');
  grid.innerHTML = '';
  // "None" option
  const noneBtn = document.createElement('button');
  noneBtn.className = 'profile-avatar-opt' + (!selected ? ' active' : '');
  noneBtn.textContent = '?';
  noneBtn.title = 'No avatar';
  noneBtn.dataset.value = '';
  noneBtn.onclick = () => selectAvatar('');
  grid.appendChild(noneBtn);

  _avatars.forEach(a => {
    const btn = document.createElement('button');
    btn.className = 'profile-avatar-opt' + (a === selected ? ' active' : '');
    btn.title = a;
    btn.dataset.value = a;
    const img = document.createElement('img');
    img.src = '/static/avatars/' + a + '.svg';
    img.alt = a;
    img.style.width = '100%';
    img.style.height = '100%';
    img.style.objectFit = 'cover';
    img.style.borderRadius = '50%';
    btn.appendChild(img);
    btn.onclick = () => selectAvatar(a);
    grid.appendChild(btn);
  });
}

let _selectedAvatar = '';

function selectAvatar(val) {
  _selectedAvatar = val;
  document.querySelectorAll('.profile-avatar-opt').forEach(b => b.classList.toggle('active', b.dataset.value === val));
  const name = document.getElementById('profileDisplayName').textContent;
  renderAvatarPreview(val, name);
}

async function saveProfile() {
  const displayName = document.getElementById('profileDisplayNameInput').value.trim();
  if (!displayName) { toast('Display name cannot be empty', 'error'); return; }
  const btn = document.getElementById('profileSaveBtn');
  btn.disabled = true;
  btn.textContent = 'Saving...';
  try {
    const r = await fetch(API + '/api/auth/profile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
      body: JSON.stringify({ display_name: displayName, avatar: _selectedAvatar }),
    });
    if (!r.ok) { const d = await r.json(); throw new Error(d.detail || 'Save failed'); }
    const result = await r.json();
    // Update local storage
    if (currentUser) {
      currentUser.display_name = displayName;
      currentUser.avatar = _selectedAvatar;
      localStorage.setItem('user', JSON.stringify(currentUser));
    }
    document.getElementById('profileDisplayName').textContent = displayName;
    toast('Profile saved!', 'success');
  } catch (e) {
    toast('Save failed: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Save Changes';
  }
}