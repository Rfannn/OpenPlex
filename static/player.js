const Player = {
  el: null, video: null, currentTrack: null,
  subtitleTracks: [], currentSubIndex: -1, subOverlay: null,
  subCache: {},  // path -> tracks[] cache so re-playing same file doesn't re-fetch
  playbackRate: parseFloat(localStorage.getItem('cpRate') || '1'),
  volume: parseFloat(localStorage.getItem('cpVolume') || '1'),
  muted: localStorage.getItem('cpMuted') === 'true',
  controlsTimer: null, controlsVisible: true,
  histInterval: null, histPath: null, histTitle: null,
  _transcodeReady: true, _transcodePollTimer: null, _transcodeFilePath: null,
  _autoPlayNext: localStorage.getItem('autoPlayNext') !== 'false',
  _countdownTimer: null, _countdownValue: 5,

  init() {
    if (document.getElementById('mediaPlayer')) return;
    const html = `
<div id="mediaPlayer" class="custom-player" style="display:none;">
  <div class="cp-video-wrap" id="cpVideoWrap">
    <video id="playerVideo" preload="metadata" playsinline></video>
    <div id="cpSubOverlay" class="cp-sub-overlay"></div>
    <div class="cp-loading-spinner" id="cpSpinner" style="display:none;"><div class="cp-spinner"></div></div>
    <div class="cp-error-overlay" id="cpError" style="display:none;">
      <div class="cp-error-icon">${this._svg('times', 32)}</div>
      <div class="cp-error-msg" id="cpErrorMsg">Playback failed</div>
      <div class="cp-error-detail" id="cpErrorDetail" style="font-size:0.75rem;opacity:0.7;margin-top:4px;"></div>
      <button class="cp-btn cp-btn-sm" id="cpRetryBtn" style="margin-top:8px;display:none;">Retry</button>
    </div>
    <div class="cp-center-play" id="cpCenterPlay">${this._svg('play', 48)}</div>
    <div class="cp-resume-overlay" id="cpResumeOverlay" style="display:none;">
      <div class="cp-resume-box">
        <h3>Resume Playback?</h3>
        <div class="cp-resume-info">
          <div class="cp-resume-title" id="cpResumeTitle"></div>
          <div class="cp-resume-progress-wrap">
            <div class="cp-resume-progress-bar" id="cpResumeBar"><div class="cp-resume-progress-fill" id="cpResumeFill"></div></div>
            <span class="cp-resume-text" id="cpResumeText">0:00 / 0:00</span>
          </div>
        </div>
        <div class="cp-resume-actions">
          <button class="cp-btn cp-btn-primary" id="cpResumeBtn">Resume</button>
          <button class="cp-btn cp-btn-ghost" id="cpRestartBtn">Start Over</button>
          <button class="cp-btn cp-btn-ghost" id="cpResumeClose">Cancel</button>
        </div>
      </div>
    </div>
  </div>
  <div class="cp-audio-wrap" id="cpAudioWrap" style="display:none;">
    <div class="cp-audio-art" id="cpAudioArt">${this._svg('music', 48)}</div>
    <div class="cp-audio-info">
      <div class="cp-audio-title" id="cpAudioTitle">-</div>
      <div class="cp-audio-meta" id="cpAudioMeta"></div>
    </div>
    <div class="cp-audio-progress">
      <span class="cp-audio-time" id="cpAudioTime">0:00</span>
      <div class="cp-audio-bar-wrap">
        <input type="range" id="cpAudioSeek" class="cp-audio-seek" min="0" max="1000" value="0" step="0.1">
        <div class="cp-audio-loaded" id="cpAudioProgress" style="width:0%"></div>
      </div>
      <span class="cp-audio-duration" id="cpAudioDuration">0:00</span>
    </div>
  </div>
  <div class="cp-controls" id="cpControls">
    <div class="cp-progress-wrap" id="cpProgressWrap">
      <input type="range" id="cpSeek" class="cp-seek" min="0" max="1000" value="0" step="0.1">
      <div class="cp-progress-buffer" id="cpBuffer"></div>
      <div class="cp-progress-loaded" id="cpProgress" style="width:0%"></div>
      <div class="cp-seek-tooltip" id="cpSeekTooltip" style="display:none;">0:00</div>
    </div>
    <div class="cp-controls-row">
      <div class="cp-left">
        <span class="cp-time" id="cpTime">0:00 / 0:00</span>
      </div>
      <div class="cp-center">
        <button class="cp-btn cp-seek-btn" id="cpSeekBack" title="-10s">${this._svg('back', 16)}</button>
        <button class="cp-btn" id="cpPrevBtn" title="Previous" style="display:none;">${this._svg('prev', 14)}</button>
        <button class="cp-btn cp-play-btn" id="cpPlayBtn" title="Play/Pause (Space)">${this._svg('play', 18)}</button>
        <button class="cp-btn" id="cpNextBtn" title="Next" style="display:none;">${this._svg('next', 14)}</button>
        <button class="cp-btn cp-seek-btn" id="cpSeekFwd" title="+10s">${this._svg('forward', 16)}</button>
      </div>
      <div class="cp-right">
        <button class="cp-btn cp-vol-btn" id="cpVolBtn" title="Mute">${this._svg('volume', 16)}</button>
        <input type="range" id="cpVolSlider" class="cp-vol-slider" min="0" max="1" step="0.05" value="${this.volume}">
        <button class="cp-btn" id="cpRateBtn" title="Speed">${this._svg('speed', 16)} ${this.playbackRate}x</button>
        <button class="cp-btn" id="cpSubBtn" title="Subtitles (S)" style="display:none;">${this._svg('subtitles', 16)}</button>
        <button class="cp-btn" id="cpInfoBtn" title="Media info (I)">${this._svg('info', 16)}</button>
        <button class="cp-btn" id="cpAdjBtn" title="Picture">${this._svg('adjust', 16)}</button>
        <button class="cp-btn" id="cpMiniBtn" title="Mini">${this._svg('mini', 14)}</button>
        <button class="cp-btn" id="cpSizeBtn" title="Theater">${this._svg('theater', 16)}</button>
        <button class="cp-btn" id="cpDlBtn" title="Download">${this._svg('download', 16)}</button>
        <button class="cp-btn" id="cpCopyBtn" title="Copy link">${this._svg('link', 16)}</button>
        <button class="cp-btn" id="cpPipBtn" title="PiP">${this._svg('pip', 16)}</button>
        <button class="cp-btn" id="cpFullBtn" title="Fullscreen">${this._svg('fullscreen', 16)}</button>
        <button class="cp-btn" id="cpCloseBtn" title="Close">${this._svg('times', 18)}</button>
      </div>
    </div>
  </div>
  <div class="cp-sub-panel" id="cpSubPanel" style="display:none;">
    <div class="cp-sub-header"><span>Subtitles</span><button class="cp-btn cp-btn-sm" id="cpSubClose">${this._svg('times', 14)}</button></div>
    <div id="cpSubList" class="cp-sub-list"></div>
    <button class="cp-sub-search-btn" id="cpSubSearchBtn">${this._svg('search', 12)} Search online</button>
    <div class="cp-sub-options">
      <label>Size: <select id="cpSubSize"><option value="0.8em">Small</option><option value="1em">Normal</option><option value="1.2em">Large</option><option value="1.5em">X-Large</option><option value="2em">XXL</option></select></label>
      <label>BG: <select id="cpSubBg"><option value="rgba(0,0,0,0.75)">Black</option><option value="rgba(0,0,0,0.5)">Dim</option><option value="transparent">None</option></select></label>
      <label>Color: <select id="cpSubColor"><option value="white">White</option><option value="yellow">Yellow</option><option value="cyan">Cyan</option><option value="green">Green</option></select></label>
    </div>
  </div>
  <div class="cp-sub-panel" id="cpSubSearchPanel" style="display:none;">
    <div class="cp-sub-header"><span>Search Subtitles</span><button class="cp-btn cp-btn-sm" id="cpSubSearchClose">${this._svg('times', 14)}</button></div>
    <div class="cp-sub-search-form">
      <input type="text" id="cpSubSearchInput" placeholder="Movie / Series name...">
      <button class="cp-btn cp-btn-sm" id="cpSubSearchGo">Search</button>
    </div>
    <div id="cpSubSearchResults" class="cp-sub-list"></div>
  </div>
  <div class="cp-adj-panel" id="cpAdjPanel" style="display:none;">
    <div class="cp-adj-header"><span>Picture</span><button class="cp-btn cp-btn-sm" id="cpAdjClose">${this._svg('times', 14)}</button></div>
    <div class="cp-adj-options">
      <label>Brightness: <input type="range" id="cpBrightness" min="0" max="200" value="100"></label>
      <label>Contrast: <input type="range" id="cpContrast" min="0" max="200" value="100"></label>
      <label>Saturation: <input type="range" id="cpSaturation" min="0" max="300" value="100"></label>
      <button class="cp-btn cp-btn-sm" id="cpAdjReset">Reset</button>
    </div>
  </div>
  <div class="cp-shortcuts" id="cpShortcuts" style="display:none;">
    <div class="cp-shortcuts-header">Keyboard Shortcuts <button class="cp-btn cp-btn-sm" id="cpShortcutsClose">${this._svg('times', 14)}</button></div>
    <div class="cp-shortcuts-grid">
      <span>Space / K</span><span>Play / Pause</span>
      <span>F</span><span>Fullscreen</span>
      <span>T</span><span>Theater mode</span>
      <span>Esc</span><span>Close player</span>
      <span>M</span><span>Mute / Unmute</span>
      <span>S</span><span>Subtitles</span>
      <span>I</span><span>Media info</span>
      <span>Arrow Left / Right</span><span>Seek -10s / +10s</span>
      <span>Arrow Up / Down</span><span>Volume +10% / -10%</span>
      <span>&lt; &gt;</span><span>Speed down / up</span>
      <span>9 / 0</span><span>Seek -60s / +60s</span>
      <span>N</span><span>Next episode</span>
      <span>P</span><span>Previous episode</span>
      <span>?</span><span>Toggle this help</span>
    </div>
  </div>
  <div class="cp-countdown-overlay" id="cpCountdown" style="display:none;">
    <div class="cp-countdown-box">
      <div class="cp-countdown-title" id="cpCountdownTitle">Next episode in...</div>
      <div class="cp-countdown-number" id="cpCountdownNumber">5</div>
      <div class="cp-countdown-bar"><div class="cp-countdown-bar-fill" id="cpCountdownFill"></div></div>
      <div class="cp-countdown-actions">
        <button class="cp-btn cp-countdown-cancel" id="cpCountdownCancel">Cancel</button>
        <button class="cp-btn cp-countdown-play" id="cpCountdownPlay">Play Now</button>
      </div>
    </div>
  </div>
  <div class="cp-info-panel" id="cpInfoPanel" style="display:none;">
    <div class="cp-info-header"><span>Media Info</span><button class="cp-btn cp-btn-sm" id="cpInfoClose">${this._svg('times', 14)}</button></div>
    <div id="cpInfoContent" class="cp-info-content"></div>
  </div>
</div>`;
    const w = document.createElement('div'); w.innerHTML = html;
    this.el = w.firstElementChild;
    document.body.appendChild(this.el);

    this.video = document.getElementById('playerVideo');
    this.subOverlay = document.getElementById('cpSubOverlay');
    if (typeof document.pictureInPictureEnabled === 'undefined' || !document.pictureInPictureEnabled) {
      document.getElementById('cpPipBtn').style.display = 'none';
    }
    this._bindEvents();
    this._loadSubPrefs();
    // Auto-play from URL params (e.g., /player?url=...&title=...)
    const up = new URLSearchParams(window.location.search);
    const autoUrl = up.get('url');
    if (autoUrl) {
      const autoTitle = up.get('title') || 'Media';
      const autoPath = up.get('path') || '';
      setTimeout(() => this.play(decodeURIComponent(autoUrl), autoTitle, '', autoPath ? decodeURIComponent(autoPath) : ''), 100);
    }
  },

  _svg(name, size) {
    const p = {
      'play': '<polygon points="6,4 20,12 6,20" fill="currentColor"/>',
      'pause': '<rect x="6" y="4" width="4" height="16" fill="currentColor"/><rect x="14" y="4" width="4" height="16" fill="currentColor"/>',
      'times': '<path d="M6 18L18 6M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
      'subtitles': '<path d="M4 6a2 2 0 012-2h12a2 2 0 012 2v8a2 2 0 01-2 2h-4l-4 4v-4H6a2 2 0 01-2-2V6z"/><path d="M8 10h.01M12 10h.01M16 10h.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
      'fullscreen': '<path d="M8 3H5a2 2 0 00-2 2v3m18 0V5a2 2 0 00-2-2h-3m0 18h3a2 2 0 002-2v-3M3 16v3a2 2 0 002 2h3" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/>',
      'fullscreen-exit': '<path d="M8 3v3a2 2 0 01-2 2H3m0 0h5V3m8 0v3a2 2 0 002 2h3m0 0h-5V3m5 13v3a2 2 0 01-2 2h-3m0 0V3m-5 13v3a2 2 0 002 2h3m0 0h-5" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/>',
      'pip': '<path d="M21 13v4a2 2 0 01-2 2H9m-6-6V7a2 2 0 012-2h14a2 2 0 012 2v4" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"/><rect x="15" y="13" width="6" height="5" rx="1" fill="currentColor" opacity="0.6"/>',
      'speed': '<path d="M12 2a10 10 0 110 20 10 10 0 010-20z" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M12 6v6l4 2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
      'volume': '<path d="M3 9v6h4l5 5V4L7 9H3zm13.5 2A4.5 4.5 0 0114 15M14 5a8.5 8.5 0 015 7 8.5 8.5 0 01-5 7" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"/>',
      'volume-mute': '<path d="M3 9v6h4l5 5V4L7 9H3z" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"/>',
      'muted': '<path d="M3 9v6h4l5 5V4L7 9H3zm11 4l6-6m0 6l-6-6" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"/>',
      'sun': '<circle cx="12" cy="12" r="4" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
      'prev': '<path d="M19 20L9 12l10-8v16zM5 4v16" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/>',
      'next': '<path d="M5 20l10-8L5 4v16zM19 4v16" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/>',
      'music': '<path d="M9 18V5l12-2v13" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/><circle cx="6" cy="18" r="3" stroke="currentColor" stroke-width="2" fill="none"/><circle cx="18" cy="16" r="3" stroke="currentColor" stroke-width="2" fill="none"/>',
      'film': '<rect x="2" y="2" width="20" height="20" rx="2" stroke="currentColor" stroke-width="2" fill="none"/><path d="M8 2v20M16 2v20M2 8h20M2 16h20" stroke="currentColor" stroke-width="2"/>',
      'adjust': '<circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M12 1v2m0 18v2M4.22 4.22l1.42 1.42m12.72 12.72l1.42 1.42M1 12h2m18 0h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" stroke="currentColor" stroke-width="1.8"/>',
      'mini': '<path d="M4 6a2 2 0 012-2h12a2 2 0 012 2v3H4V6zm0 5v7a2 2 0 002 2h12a2 2 0 002-2v-7H4z" stroke="currentColor" stroke-width="1.8" fill="none"/>',
      'theater': '<rect x="2" y="5" width="20" height="14" rx="2" stroke="currentColor" stroke-width="1.6" fill="none"/><path d="M2 8h20M8 5v14" stroke="currentColor" stroke-width="1.6"/>',
      'theater-exit': '<path d="M4 6a2 2 0 012-2h12a2 2 0 012 2v1H4V6zm0 3v9a2 2 0 002 2h12a2 2 0 002-2V9H4z" stroke="currentColor" stroke-width="1.6" fill="none"/><path d="M10 12l4 4m0-4l-4 4" stroke="currentColor" stroke-width="1.6"/>',
      'back': '<path d="M11 4L4 12l7 8M4 12h16" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/><text x="13" y="20" font-size="7" font-weight="bold" fill="currentColor">10</text>',
      'forward': '<path d="M13 4l7 8-7 8M20 12H4" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/><text x="2" y="20" font-size="7" font-weight="bold" fill="currentColor">10</text>',
      'download': '<path d="M12 3v12m0 0l-4-4m4 4l4-4M5 17v2a2 2 0 002 2h10a2 2 0 002-2v-2" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"/>',
      'link': '<path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"/>',
      'info': '<circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M12 16v-4m0-4h.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
    };
    return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" style="display:inline-block;vertical-align:middle;">${p[name]||''}</svg>`;
  },

  _bindEvents() {
    const v = this.video;
    const seek = document.getElementById('cpSeek');
    const playBtn = document.getElementById('cpPlayBtn');
    const timeEl = document.getElementById('cpTime');
    const centerPlay = document.getElementById('cpCenterPlay');
    const spinner = document.getElementById('cpSpinner');
    const errEl = document.getElementById('cpError');
    const wrap = document.getElementById('cpVideoWrap');
    const controls = document.getElementById('cpControls');

    // ── Video events ──
    v.addEventListener('loadedmetadata', () => {
      this._detectSubs();
      timeEl.textContent = '0:00 / ' + this._fmt(v.duration);
      if (this._mode === 'audio') {
        document.getElementById('cpAudioDuration').textContent = this._fmt(v.duration);
      }
      spinner.style.display = 'none';
      errEl.style.display = 'none';
      if (!this._loggedMeta) { this._loggedMeta = true; console.log('[Player] video:', v.videoWidth+'x'+v.videoHeight, 'duration:', this._fmt(v.duration)); }
    });
    v.addEventListener('error', (e) => {
      spinner.style.display = 'none';
      errEl.style.display = '';
      centerPlay.style.display = 'none';
      const msgEl = document.getElementById('cpErrorMsg');
      const detailEl = document.getElementById('cpErrorDetail');
      const retryBtn = document.getElementById('cpRetryBtn');
      const errCode = v.error ? v.error.code : 0;
      const errMsg = v.error ? v.error.message : 'unknown';
      console.error('[Player] video error:', errMsg, 'code:', errCode, e);
      if (errMsg && (errMsg.includes('DEMUXER') || errMsg.includes('FFmpegDemuxer') || errMsg.includes('open context failed'))) {
        msgEl.textContent = 'Cannot play this file';
        detailEl.textContent = 'File may still be downloading or is corrupted. Try again later.';
        retryBtn.style.display = '';
      } else if (errCode === 4) {  // MEDIA_ERR_DECODE
        msgEl.textContent = 'Cannot play this file';
        detailEl.textContent = 'The file may be damaged or use an unsupported codec.';
        retryBtn.style.display = '';
      } else {
        msgEl.textContent = 'Playback failed';
        detailEl.textContent = '';
        retryBtn.style.display = 'none';
      }
    });
    v.addEventListener('play', () => {
      centerPlay.style.display = 'none';
      playBtn.innerHTML = this._svg('pause', 18);
    });
    v.addEventListener('pause', () => {
      playBtn.innerHTML = this._svg('play', 18);
    });
    v.addEventListener('ended', () => {
      playBtn.innerHTML = this._svg('play', 18);
      if (this._autoPlayNext && typeof window.currentMediaList !== 'undefined') {
        const idx = typeof window.currentMediaIndex !== 'undefined' ? window.currentMediaIndex : -1;
        if (idx >= 0 && idx < window.currentMediaList.length - 1) {
          this._startCountdown();
          return;
        }
      }
      centerPlay.style.display = '';
    });

    v.addEventListener('waiting', () => {
      spinner.style.display = '';
    });
    v.addEventListener('canplay', () => {
      spinner.style.display = 'none';
    });
    v.addEventListener('stalled', () => {
      spinner.style.display = '';
    });

    v.addEventListener('error', () => {
      spinner.style.display = 'none';
      errEl.style.display = '';
      centerPlay.style.display = 'none';
    });

    // ── Controls timeline ──
    const progressWrap = document.getElementById('cpProgressWrap');
    progressWrap.addEventListener('mousemove', (e) => {
      const rect = progressWrap.getBoundingClientRect();
      const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      const tooltip = document.getElementById('cpSeekTooltip');
      tooltip.textContent = v.duration ? this._fmt(v.duration * pct) : '0:00';
      tooltip.style.left = `calc(${pct * 100}% - 20px)`;
      tooltip.style.display = '';
    });
    progressWrap.addEventListener('mouseleave', () => {
      document.getElementById('cpSeekTooltip').style.display = 'none';
    });
    progressWrap.addEventListener('click', (e) => {
      if (!v.duration) return;
      const rect = progressWrap.getBoundingClientRect();
      const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      this._seekTo(v.duration * pct);
    });

    seek.addEventListener('input', () => {
      if (v.duration) this._seekTo((seek.value / 1000) * v.duration);
    });

    // Audio seek
    const audioSeek = document.getElementById('cpAudioSeek');
    audioSeek.addEventListener('input', () => {
      if (v.duration) this._seekTo((audioSeek.value / 1000) * v.duration);
    });

    // ── Time update: progress, time, buffer, subs ──
    v.addEventListener('timeupdate', () => {
      if (!v.duration) return;
      const pct = (v.currentTime / v.duration) * 1000;
      seek.value = pct;
      document.getElementById('cpProgress').style.width = (v.currentTime / v.duration * 100) + '%';
      timeEl.textContent = this._fmt(v.currentTime) + ' / ' + this._fmt(v.duration);
      // Buffer
      if (v.buffered.length > 0) {
        const bufEnd = v.buffered.end(v.buffered.length - 1);
        document.getElementById('cpBuffer').style.width = (bufEnd / v.duration * 100) + '%';
      }
      // Subs
      this._renderSubs(v.currentTime);
      // Audio
      if (this._mode === 'audio') {
        document.getElementById('cpAudioTime').textContent = this._fmt(v.currentTime);
        audioSeek.value = pct;
        document.getElementById('cpAudioProgress').style.width = (v.currentTime / v.duration * 100) + '%';
      }
    });

    // ── Play / Pause ──
    playBtn.addEventListener('click', () => this.togglePlay());
    centerPlay.addEventListener('click', () => this.togglePlay());
    wrap.addEventListener('dblclick', () => this.toggleFullscreen());
    wrap.addEventListener('click', () => this.togglePlay());

    // ── Double-tap seek (mobile) ──
    let lastTap = 0;
    let touchStartX = 0, touchStartY = 0, touchStartTime = 0, touchStartVol = 1;
    wrap.addEventListener('touchstart', (e) => {
      if (e.touches.length === 1) {
        touchStartX = e.touches[0].clientX;
        touchStartY = e.touches[0].clientY;
        touchStartTime = Date.now();
        touchStartVol = v.volume;
      }
    }, { passive: true });
    wrap.addEventListener('touchend', (e) => {
      const now = Date.now();
      const dt = now - touchStartTime;
      const dx = e.changedTouches.length ? e.changedTouches[0].clientX - touchStartX : 0;
      const dy = e.changedTouches.length ? e.changedTouches[0].clientY - touchStartY : 0;

      if (now - lastTap < 400 && e.changedTouches.length === 1 && Math.abs(dx) < 10 && Math.abs(dy) < 10) {
        const rect = wrap.getBoundingClientRect();
        const x = e.changedTouches[0].clientX - rect.left;
        if (x < rect.width * 0.4) {
          this._seekTo(v.currentTime - 10);
          this._flashSeek(-10);
        } else if (x > rect.width * 0.6) {
          this._seekTo(v.currentTime + 10);
          this._flashSeek(10);
        }
      } else if (dt < 300 && Math.abs(dy) > 30 && Math.abs(dy) > Math.abs(dx) * 1.5) {
        // Vertical swipe → volume (left side) or brightness (right side)
        const rect = wrap.getBoundingClientRect();
        const x = touchStartX - rect.left;
        if (x < rect.width * 0.5) {
          // Volume: up = louder
          const delta = -dy / rect.height;
          const newVol = Math.max(0, Math.min(1, touchStartVol + delta));
          v.volume = newVol;
          v.muted = newVol === 0;
          this.volume = newVol;
          localStorage.setItem('cpVolume', String(newVol));
          this._showGestureIndicator('volume', Math.round(newVol * 100));
          const volSlider = document.getElementById('cpVolSlider');
          if (volSlider) volSlider.value = newVol;
        } else {
          // Brightness feedback (visual only — we can't change OS brightness)
          const delta = -dy / rect.height;
          const pct = Math.max(0, Math.min(1, 0.5 + delta));
          this._showGestureIndicator('brightness', Math.round(pct * 100));
        }
      }
      lastTap = now;
    });

    // ── Fullscreen ──
    document.getElementById('cpFullBtn').addEventListener('click', () => this.toggleFullscreen());
    document.addEventListener('fullscreenchange', () => {
      const btn = document.getElementById('cpFullBtn');
      if (document.fullscreenElement) {
        btn.innerHTML = this._svg('fullscreen-exit', 16);
        btn.title = 'Exit Fullscreen (F)';
      } else {
        btn.innerHTML = this._svg('fullscreen', 16);
        btn.title = 'Fullscreen (F)';
      }
    });

    // ── PiP ──
    document.getElementById('cpPipBtn').addEventListener('click', () => this.togglePip());

    // ── Mini player ──
    document.getElementById('cpMiniBtn').addEventListener('click', () => this.toggleMini());

    // ── Theater size ──
    document.getElementById('cpSizeBtn').addEventListener('click', () => this.toggleSize());

    // ── Download ──
    document.getElementById('cpDlBtn').addEventListener('click', () => this._downloadCurrent());

    // ── Copy link ──
    document.getElementById('cpCopyBtn').addEventListener('click', () => this._copyLink());

    // ── Close ──
    document.getElementById('cpCloseBtn').addEventListener('click', () => this.stop());

    // ── Volume ──
    const volSlider = document.getElementById('cpVolSlider');
    const volBtn = document.getElementById('cpVolBtn');
    volSlider.addEventListener('input', () => {
      this.volume = parseFloat(volSlider.value);
      this.muted = this.volume === 0;
      v.volume = this.volume;
      v.muted = this.muted;
      localStorage.setItem('cpVolume', this.volume);
      localStorage.setItem('cpMuted', this.muted);
      this._updateVolIcon();
    });
    volBtn.addEventListener('click', () => {
      this.muted = !this.muted;
      v.muted = this.muted;
      localStorage.setItem('cpMuted', this.muted);
      this._updateVolIcon();
    });
    v.volume = this.volume;
    v.muted = this.muted;
    this._updateVolIcon();

    // ── Subtitles ──
    document.getElementById('cpSubBtn').addEventListener('click', () => {
      const p = document.getElementById('cpSubPanel');
      document.getElementById('cpAdjPanel').style.display = 'none';
      p.style.display = p.style.display === 'none' ? '' : 'none';
    });
    document.getElementById('cpSubClose').addEventListener('click', () => {
      document.getElementById('cpSubPanel').style.display = 'none';
    });
    document.getElementById('cpSubSize').addEventListener('change', (e) => {
      if (this.subOverlay) this.subOverlay.style.setProperty('--sub-size', e.target.value);
      localStorage.setItem('cpSubSize', e.target.value);
    });
    document.getElementById('cpSubBg').addEventListener('change', (e) => {
      if (this.subOverlay) this.subOverlay.style.setProperty('--sub-bg', e.target.value);
      localStorage.setItem('cpSubBg', e.target.value);
    });
    document.getElementById('cpSubColor').addEventListener('change', (e) => {
      if (this.subOverlay) this.subOverlay.style.setProperty('--sub-color', e.target.value);
      localStorage.setItem('cpSubColor', e.target.value);
    });

    // ── Subtitle Search ──
    const subSearchBtn = document.getElementById('cpSubSearchBtn');
    const subSearchPanel = document.getElementById('cpSubSearchPanel');
    const subSearchInput = document.getElementById('cpSubSearchInput');
    const subSearchGo = document.getElementById('cpSubSearchGo');
    const subSearchResults = document.getElementById('cpSubSearchResults');
    const subSearchClose = document.getElementById('cpSubSearchClose');
    if (subSearchBtn && subSearchPanel) {
      subSearchBtn.addEventListener('click', () => {
        document.getElementById('cpSubPanel').style.display = 'none';
        subSearchPanel.style.display = subSearchPanel.style.display === 'none' ? '' : 'none';
        if (subSearchPanel.style.display !== 'none' && this.currentSubPath) {
          subSearchInput.value = this._currentMediaTitle || this.currentSubPath.split('/').pop().replace(/\.[^.]+$/, '');
        }
      });
    }
    if (subSearchClose && subSearchPanel) {
      subSearchClose.addEventListener('click', () => { subSearchPanel.style.display = 'none'; });
    }
    async function doSubSearch() {
      const q = subSearchInput.value.trim();
      if (!q) return;
      subSearchResults.innerHTML = '<div style="padding:12px;text-align:center;color:var(--text-muted);font-size:0.78rem;">Searching...</div>';
      try {
        const r = await fetch('/api/subtitles/search?q=' + encodeURIComponent(q) + '&l=English');
        const d = await r.json();
        if (!d.success || !d.results || !d.results.length) {
          subSearchResults.innerHTML = '<div style="padding:12px;text-align:center;color:var(--text-muted);font-size:0.78rem;">No results found</div>';
          return;
        }
        subSearchResults.innerHTML = '';
        d.results.forEach(res => {
          const div = document.createElement('div');
          div.className = 'cp-sub-search-result';
          div.innerHTML = `
            <div class="cp-sub-result-info">
              <div class="cp-sub-result-title">${esc(res.title)}</div>
              <div class="cp-sub-result-meta">${res.info || ''} ${res.series ? '[Series]' : ''}</div>
            </div>
            <button class="cp-sub-result-dl" data-tag="${esc(res.tag)}">Download</button>
          `;
          const dlBtn = div.querySelector('.cp-sub-result-dl');
          dlBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            dlBtn.textContent = '...';
            try {
              const r2 = await fetch('/api/subtitles/download', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({tag: res.tag, media_path: Player.currentSubPath}),
              });
              const d2 = await r2.json();
              if (d2.success && d2.saved && d2.saved.length) {
                dlBtn.textContent = '✓ Saved';
                div.classList.add('cp-sub-result-done');
                // Clear cache so next load picks up local files
                delete Player.subCache[Player.currentSubPath];
                Player._loadEmbeddedSubs(Player.currentSubPath);
              } else {
                dlBtn.textContent = 'Failed';
              }
            } catch (_) { dlBtn.textContent = 'Error'; }
          });
          subSearchResults.appendChild(div);
        });
      } catch (_) {
        subSearchResults.innerHTML = '<div style="padding:12px;text-align:center;color:var(--danger);font-size:0.78rem;">Search failed</div>';
      }
    }
    if (subSearchGo) { subSearchGo.addEventListener('click', doSubSearch); }
    if (subSearchInput) { subSearchInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') doSubSearch(); }); }

    // ── Picture Adjust ──
    document.getElementById('cpAdjBtn').addEventListener('click', () => {
      const p = document.getElementById('cpAdjPanel');
      document.getElementById('cpSubPanel').style.display = 'none';
      p.style.display = p.style.display === 'none' ? '' : 'none';
    });
    document.getElementById('cpAdjClose').addEventListener('click', () => {
      document.getElementById('cpAdjPanel').style.display = 'none';
    });
    ['Brightness', 'Contrast', 'Saturation'].forEach(name => {
      const el = document.getElementById('cp' + name);
      el.addEventListener('input', () => this._applyFilters());
    });
    document.getElementById('cpAdjReset').addEventListener('click', () => {
      ['Brightness', 'Contrast', 'Saturation'].forEach(name => {
        document.getElementById('cp' + name).value = 100;
      });
      this._applyFilters();
    });

    // ── Speed ──
    const rates = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2];
    let rateIdx = rates.indexOf(this.playbackRate);
    if (rateIdx === -1) { rateIdx = rates.indexOf(1); this.playbackRate = 1; }
    document.getElementById('cpRateBtn').addEventListener('click', () => {
      rateIdx = (rateIdx + 1) % rates.length;
      this.playbackRate = rates[rateIdx];
      v.playbackRate = this.playbackRate;
      localStorage.setItem('cpRate', this.playbackRate);
      document.getElementById('cpRateBtn').innerHTML = this._svg('speed', 16) + ' ' + this.playbackRate + 'x';
    });

    // ── Seek -10 / +10 ──
    document.getElementById('cpSeekBack').addEventListener('click', () => { this._seekTo(v.currentTime - 10); this._flashSeek(-10); });
    document.getElementById('cpSeekFwd').addEventListener('click', () => { this._seekTo(v.currentTime + 10); this._flashSeek(10); });

    // ── Prev / Next ──
    document.getElementById('cpPrevBtn').addEventListener('click', () => this._navMedia(-1));
    document.getElementById('cpNextBtn').addEventListener('click', () => this._navMedia(1));

    // ── Auto-hide controls ──
    const autoHide = () => {
      if (this.controlsTimer) clearTimeout(this.controlsTimer);
      if (!this.video.paused) {
        this.controlsTimer = setTimeout(() => {
          if (!this.video.paused) {
            controls.style.opacity = '0';
            controls.style.pointerEvents = 'none';
            this.controlsVisible = false;
          }
        }, 3000);
      }
    };
    this.el.addEventListener('mousemove', () => {
      controls.style.opacity = '1';
      controls.style.pointerEvents = '';
      this.controlsVisible = true;
      autoHide();
    });
    this.el.addEventListener('mouseleave', () => {
      autoHide();
    });
    v.addEventListener('play', autoHide);
    v.addEventListener('pause', () => {
      if (this.controlsTimer) clearTimeout(this.controlsTimer);
      controls.style.opacity = '1';
      controls.style.pointerEvents = '';
      this.controlsVisible = true;
    });

    // ── Keyboard shortcuts ──
    document.addEventListener('keydown', (e) => {
      if (!this.currentTrack || this.el.style.display === 'none') return;
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
      const code = e.code;
      if (code === 'Space' || code === 'KeyK') { e.preventDefault(); this.togglePlay(); }
      if (code === 'ArrowLeft') { e.preventDefault(); this._seekTo(v.currentTime - 10); this._flashSeek(-10); }
      if (code === 'ArrowRight') { e.preventDefault(); this._seekTo(v.currentTime + 10); this._flashSeek(10); }
      if (code === 'ArrowUp') { e.preventDefault(); volSlider.value = Math.min(1, parseFloat(volSlider.value) + 0.1); volSlider.dispatchEvent(new Event('input')); }
      if (code === 'ArrowDown') { e.preventDefault(); volSlider.value = Math.max(0, parseFloat(volSlider.value) - 0.1); volSlider.dispatchEvent(new Event('input')); }
      if (code === 'KeyF') { e.preventDefault(); this.toggleFullscreen(); }
      if (code === 'KeyT') { e.preventDefault(); this.toggleSize(); }
      if (code === 'KeyM') { e.preventDefault(); volBtn.click(); }
      if (code === 'KeyS') { e.preventDefault(); document.getElementById('cpSubBtn').click(); }
      if (code === 'KeyI') { e.preventDefault(); this._toggleInfo(); }
      if (code === 'KeyN') { e.preventDefault(); this._navMedia(1); }
      if (code === 'KeyP') { e.preventDefault(); this._navMedia(-1); }
      if (code === 'Comma') { e.preventDefault(); rateIdx = Math.max(0, rateIdx - 1); document.getElementById('cpRateBtn').click(); rateIdx = Math.max(0, rateIdx - 1); }
      if (code === 'Period') { e.preventDefault(); rateIdx = Math.min(rates.length - 1, rateIdx + 1); document.getElementById('cpRateBtn').click(); rateIdx = Math.min(rates.length - 1, rateIdx + 1); }
      if (code === 'Escape') {
        if (document.getElementById('cpShortcuts').style.display !== 'none') {
          document.getElementById('cpShortcuts').style.display = 'none';
        } else if (this.el.classList.contains('cp-maximized')) {
          this.toggleSize();
        } else {
          this.stop();
        }
      }
      if (code === 'Slash' && e.shiftKey) { e.preventDefault(); document.getElementById('cpShortcuts').style.display = document.getElementById('cpShortcuts').style.display === 'none' ? '' : 'none'; }
      if (code === 'Digit9') { e.preventDefault(); this._seekTo(v.currentTime - 60); }
      if (code === 'Digit0') { e.preventDefault(); this._seekTo(v.currentTime + 60); }
    });

    // ── Retry on error ──
    document.getElementById('cpRetryBtn').addEventListener('click', () => {
      document.getElementById('cpError').style.display = 'none';
      spinner.style.display = '';
      v.load();
      v.play().catch(() => {});
    });

    // ── Context menu ──
    wrap.addEventListener('contextmenu', (e) => e.preventDefault());

    // ── Shortcuts help ──
    document.getElementById('cpShortcutsClose').addEventListener('click', () => {
      document.getElementById('cpShortcuts').style.display = 'none';
    });

    // ── Info panel ──
    document.getElementById('cpInfoClose').addEventListener('click', () => {
      document.getElementById('cpInfoPanel').style.display = 'none';
    });
    document.getElementById('cpInfoBtn').addEventListener('click', () => this._toggleInfo());

    // ── Countdown (auto-play next) ──
    document.getElementById('cpCountdownCancel').addEventListener('click', () => this._stopCountdown());
    document.getElementById('cpCountdownPlay').addEventListener('click', () => { this._stopCountdown(); this._navMedia(1); });

    // ── Disable PiP via video attribute ──
    v.disablePictureInPicture = false;
  },

  _updateVolIcon() {
    const btn = document.getElementById('cpVolBtn');
    btn.innerHTML = this.muted || this.volume === 0 ? this._svg('muted', 16) : this._svg('volume', 16);
    btn.title = this.muted ? 'Unmute (M)' : 'Mute (M)';
  },

  _applyFilters() {
    const b = document.getElementById('cpBrightness').value;
    const c = document.getElementById('cpContrast').value;
    const s = document.getElementById('cpSaturation').value;
    this.video.style.filter = `brightness(${b}%) contrast(${c}%) saturate(${s}%)`;
  },

  _seekTo(time) {
    const v = this.video;
    time = Math.max(0, Math.min(v.duration || Infinity, time));
    if (!this._transcodeReady && v.buffered.length > 0) {
      let inBuffer = false;
      for (let i = 0; i < v.buffered.length; i++) {
        if (time >= v.buffered.start(i) && time <= v.buffered.end(i)) { inBuffer = true; break; }
      }
      if (!inBuffer) {
        // Reload stream from new seek position instead of blocking
        const url = v.src;
        const base = url.split('?')[0];
        const params = new URLSearchParams(url.split('?')[1] || '');
        params.set('t', time);
        v.src = base + '?' + params.toString();
        v.load();
        v.play().catch(() => {});
        return;
      }
    }
    v.currentTime = time;
  },

  _flashSeek(sec) {
    const el = document.createElement('div');
    el.className = 'cp-seek-flash';
    el.textContent = (sec > 0 ? '+' : '') + sec + 's';
    el.style.cssText = `position:absolute;top:50%;${sec > 0 ? 'right' : 'left'}:30%;transform:translateY(-50%);color:#fff;font-size:2rem;font-weight:700;text-shadow:0 2px 8px rgba(0,0,0,0.8);z-index:5;pointer-events:none;animation:cpFadeOut 0.6s ease forwards;`;
    this.el.querySelector('.cp-video-wrap').appendChild(el);
    setTimeout(() => el.remove(), 600);
  },

  _showGestureIndicator(type, pct) {
    let el = document.getElementById('cpGestureIndicator');
    if (!el) {
      el = document.createElement('div');
      el.id = 'cpGestureIndicator';
      el.className = 'cp-gesture-indicator';
      this.el.querySelector('.cp-video-wrap').appendChild(el);
    }
    const icon = type === 'volume'
      ? (pct === 0 ? this._svg('volume-mute', 28) : this._svg('volume', 28))
      : this._svg('sun', 28);
    el.innerHTML = `${icon}<div class="cp-gesture-bar"><div class="cp-gesture-bar-fill" style="width:${pct}%"></div></div><div class="cp-gesture-pct">${pct}%</div>`;
    el.classList.add('cp-gesture-visible');
    clearTimeout(this._gestureTimer);
    this._gestureTimer = setTimeout(() => el.classList.remove('cp-gesture-visible'), 800);
  },

  togglePlay() {
    if (this.video.paused) this.video.play().catch(() => {});
    else this.video.pause();
  },

  toggleFullscreen() {
    if (!document.fullscreenElement) {
      // Exit mini/maximized when going fullscreen
      this.el.classList.remove('cp-mini');
      this.el.requestFullscreen().catch(() => {});
    } else {
      document.exitFullscreen().catch(() => {});
    }
  },

  toggleSize() {
    this.el.classList.toggle('cp-maximized');
    this.el.classList.remove('cp-mini');
    const btn = document.getElementById('cpSizeBtn');
    if (this.el.classList.contains('cp-maximized')) {
      btn.innerHTML = this._svg('theater-exit', 16);
      btn.title = 'Exit theater mode (T)';
    } else {
      btn.innerHTML = this._svg('theater', 16);
      btn.title = 'Theater mode (T)';
    }
  },

  togglePip() {
    if (document.pictureInPictureElement) document.exitPictureInPicture().catch(() => {});
    else this.video.requestPictureInPicture().catch(() => {});
  },

  toggleMini() {
    this.el.classList.toggle('cp-mini');
    this.el.classList.remove('cp-maximized');
    const btn = document.getElementById('cpMiniBtn');
    if (this.el.classList.contains('cp-mini')) {
      btn.innerHTML = this._svg('fullscreen', 14);
      btn.title = 'Expand';
      document.getElementById('cpSizeBtn').innerHTML = this._svg('theater', 16);
      document.getElementById('cpSizeBtn').title = 'Theater mode (T)';
    } else {
      btn.innerHTML = this._svg('mini', 16);
      btn.title = 'Mini Player';
    }
  },

  _downloadCurrent() {
    const path = this.currentTrack?.url ? this._getPathFromUrl(this.currentTrack.url) : null;
    if (!path) return;
    const a = document.createElement('a');
    a.href = '/api/download/' + encodeURIComponent(path);
    a.download = this.currentTrack?.title || 'video';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  },

  async _copyLink() {
    const path = this.currentTrack?.url ? this._getPathFromUrl(this.currentTrack.url) : null;
    if (!path) return;
    const dlUrl = window.location.origin + '/api/download/' + encodeURIComponent(path);
    try {
      await navigator.clipboard.writeText(dlUrl);
      const btn = document.getElementById('cpCopyBtn');
      const orig = btn.innerHTML;
      btn.innerHTML = 'copied';
      btn.style.color = 'var(--accent)';
      setTimeout(() => { btn.innerHTML = orig; btn.style.color = ''; }, 2000);
    } catch (_) {
      // Fallback
      const ta = document.createElement('textarea');
      ta.value = dlUrl; ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select(); document.execCommand('copy'); document.body.removeChild(ta);
    }
  },

  async play(url, title, meta, filePath) {
    document.getElementById('cpError').style.display = 'none';
    document.getElementById('cpSpinner').style.display = '';
    this.currentTrack = { url, title, meta: meta || '' };
    this.currentSubPath = filePath || this._getPathFromUrl(url);
    this._currentMediaTitle = title || this.currentSubPath.split('/').pop().replace(/\.[^.]+$/, '');
    const isTranscode = url.includes('transcode=true');
    this._loggedMeta = false;
    this._transcodeReady = !isTranscode;
    this._stopTranscodePoll();
    this._transcodeFilePath = isTranscode ? (filePath || this._getPathFromUrl(url)) : null;
    // Start video immediately, load subs in background
    this.video.src = url;
    this.video.load();
    this._setMode(url);
    this.show();
    document.getElementById('cpCenterPlay').style.display = 'none';
    // Try autoplay immediately and again once metadata loads (transcode streams need time)
    this.video.play().catch(() => {});
    const tryPlay = () => {
      this.video.play().catch(() => { document.getElementById('cpCenterPlay').style.display = ''; });
      this.video.removeEventListener('loadedmetadata', tryPlay);
    };
    this.video.addEventListener('loadedmetadata', tryPlay);
    // Check for resume point after duration is known
    this.video.addEventListener('loadedmetadata', () => this._checkResumePoint(this.currentSubPath), { once: true });
    this._startHistory();
    this._loadEmbeddedSubs(this.currentSubPath);
    // Start polling for cache completion
    if (isTranscode) this._startTranscodePoll();

    // Show/hide prev/next buttons based on media list
    const hasList = typeof window.currentMediaList !== 'undefined' && window.currentMediaList.length > 0;
    const prevBtn = document.getElementById('cpPrevBtn');
    const nextBtn = document.getElementById('cpNextBtn');
    if (hasList) {
      const idx = typeof window.currentMediaIndex !== 'undefined' ? window.currentMediaIndex : -1;
      prevBtn.style.display = idx > 0 ? '' : 'none';
      nextBtn.style.display = idx < window.currentMediaList.length - 1 ? '' : 'none';
    } else {
      prevBtn.style.display = 'none';
      nextBtn.style.display = 'none';
    }
  },

  async _startTranscodePoll() {
    if (!this._transcodeFilePath) return;
    while (this._transcodeFilePath) {
      await new Promise(r => setTimeout(r, 3000));
      if (!this._transcodeFilePath) break;
      try {
        const r = await fetch('/api/transcode/status?path=' + encodeURIComponent(this._transcodeFilePath));
        const d = await r.json();
        if (d.ready) {
          this._transcodeReady = true;
          const directUrl = '/api/stream?path=' + encodeURIComponent(this._transcodeFilePath) + '&transcode=true';
          const ct = this.video.currentTime;
          this.video.src = directUrl;
          this.video.addEventListener('loadedmetadata', () => {
            this.video.currentTime = Math.min(ct, this.video.duration - 1);
            this.video.play().catch(() => {});
          }, { once: true });
          break;
        }
      } catch(e) {}
    }
    this._transcodePollTimer = null;
  },

  _stopTranscodePoll() {
    this._transcodeFilePath = null;
    this._transcodePollTimer = null;
  },

  _formatTime(s) {
    if (isNaN(s) || s < 0) return '0:00';
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    const h = Math.floor(m / 60);
    return h > 0 ? `${h}:${String(m % 60).padStart(2,'0')}:${String(sec).padStart(2,'0')}` : `${m}:${String(sec).padStart(2,'0')}`;
  },

  async _checkResumePoint(subPath) {
    if (!subPath) return;
    const v = this.video;
    if (!v.duration || v.duration < 30) return;
    try {
      const r = await fetch('/api/history/' + encodeURIComponent(subPath), {
        headers: { 'Authorization': 'Bearer ' + (localStorage.getItem('token') || '') }
      });
      const d = await r.json();
      if (!d.success) return;
      const pos = d.position_sec;
      const dur = d.duration_sec || v.duration;
      if (!pos || pos < 10 || pos >= dur - 10) return;
      // Show resume overlay
      const overlay = document.getElementById('cpResumeOverlay');
      document.getElementById('cpResumeTitle').textContent = this.currentTrack?.title || '';
      const fill = document.getElementById('cpResumeFill');
      fill.style.width = (pos / dur * 100) + '%';
      document.getElementById('cpResumeText').textContent = this._formatTime(pos) + ' / ' + this._formatTime(dur);
      v.pause();
      overlay.style.display = '';
      // Auto-resume after 10 seconds
      const autoTimer = setTimeout(() => {
        overlay.style.display = 'none';
        v.currentTime = pos;
        v.play().catch(() => {});
      }, 10000);
      const cleanup = () => { clearTimeout(autoTimer); overlay.style.display = 'none'; };
      document.getElementById('cpResumeBtn').onclick = () => {
        cleanup();
        v.currentTime = pos;
        v.play().catch(() => {});
      };
      document.getElementById('cpRestartBtn').onclick = () => {
        cleanup();
        v.play().catch(() => {});
      };
      document.getElementById('cpResumeClose').onclick = () => {
        cleanup();
        v.play().catch(() => {});
      };
    } catch(_) {}
  },

  _setMode(url) {
    const audioExts = ['mp3', 'wav', 'ogg', 'aac', 'flac', 'm4a', 'wma'];
    const ext = (url.match(/\.([a-z0-9]+)(?:\?|$)/i) || [])[1] || '';
    this._mode = audioExts.includes(ext) ? 'audio' : 'video';
    this.el.classList.toggle('cp-mode-audio', this._mode === 'audio');
    this.el.classList.toggle('cp-mode-video', this._mode === 'video');
    document.body.classList.toggle('cp-mode-audio', this._mode === 'audio');
    const vw = document.getElementById('cpVideoWrap');
    const aw = document.getElementById('cpAudioWrap');
    const pipBtn = document.getElementById('cpPipBtn');
    const fullBtn = document.getElementById('cpFullBtn');
    const sizeBtn = document.getElementById('cpSizeBtn');
    const miniBtn = document.getElementById('cpMiniBtn');
    const subBtn = document.getElementById('cpSubBtn');
    const adjBtn = document.getElementById('cpAdjBtn');
    const infoBtn = document.getElementById('cpInfoBtn');
    if (this._mode === 'audio') {
      vw.style.display = 'none';
      aw.style.display = '';
      subBtn.style.display = 'none';
      pipBtn.style.display = 'none';
      fullBtn.style.display = 'none';
      sizeBtn.style.display = 'none';
      adjBtn.style.display = 'none';
      infoBtn.style.display = 'none';
      miniBtn.style.display = 'none';
      document.getElementById('cpSubPanel').style.display = 'none';
      document.getElementById('cpAdjPanel').style.display = 'none';
    } else {
      vw.style.display = '';
      aw.style.display = 'none';
      subBtn.style.display = pipBtn.style.display = fullBtn.style.display = sizeBtn.style.display = adjBtn.style.display = infoBtn.style.display = miniBtn.style.display = '';
      if (typeof document.pictureInPictureEnabled === 'undefined' || !document.pictureInPictureEnabled) {
        pipBtn.style.display = 'none';
      }
    }
  },

  _getPathFromUrl(url) {
    if (!url) return '';
    const m = url.match(/\/api\/stream\?path=([^&]+)/);
    if (m) return decodeURIComponent(m[1]);
    const m2 = url.match(/\/api\/media\/(.+?)(?:\?|$)/);
    if (m2) return decodeURIComponent(m2[1]);
    return url;
  },

  // ── Subtitle Overlay (div-based, not native <track>) ──

  _parseSrt(text) {
    const cues = [];
    const blocks = text.replace(/\r\n/g, '\n').split(/\n\n+/);
    for (const block of blocks) {
      const lines = block.split('\n');
      if (lines.length < 3) continue;
      const timeLine = lines.find(l => l.includes('-->'));
      if (!timeLine) continue;
      const parts = timeLine.split(/-->\s*/);
      const start = this._timeToSeconds(parts[0].trim());
      const end = this._timeToSeconds(parts[1].trim());
      const txt = lines.slice(lines.indexOf(timeLine) + 1).join('\n').trim();
      if (txt) cues.push({ start, end, text: txt });
    }
    return cues;
  },

  _parseVtt(text) {
    const clean = text.replace(/\r\n/g, '\n').replace(/^WEBVTT.*\n/, '');
    return this._parseSrt(clean);
  },

  _timeToSeconds(t) {
    t = t.replace(',', '.');
    const parts = t.split(':');
    if (parts.length === 3) return parseFloat(parts[0]) * 3600 + parseFloat(parts[1]) * 60 + parseFloat(parts[2]);
    if (parts.length === 2) return parseFloat(parts[0]) * 60 + parseFloat(parts[1]);
    return parseFloat(t) || 0;
  },

  _renderSubs(time) {
    if (!this.subOverlay) return;
    if (this.currentSubIndex < 0 || !this.subtitleTracks[this.currentSubIndex]) {
      this.subOverlay.innerHTML = '';
      return;
    }
    const cues = this.subtitleTracks[this.currentSubIndex].cues;
    if (!cues) { this.subOverlay.innerHTML = ''; return; }
    // Find active cues (allow overlapping)
    const active = cues.filter(c => time >= c.start && time < c.end);
    if (active.length === 0) {
      this.subOverlay.innerHTML = '';
      return;
    }
    this.subOverlay.innerHTML = active.map(c => `<span class="cp-sub-cue">${this._cleanSubText(c.text)}</span>`).join('\n');
  },

  _cleanSubText(s) {
    const d = document.createElement('div');
    d.innerHTML = s;
    return d.textContent || d.innerText || '';
  },

  _selectSub(index) {
    this.currentSubIndex = index;
    if (this.subOverlay) this.subOverlay.innerHTML = '';
    document.querySelectorAll('#cpSubList .cp-sub-item').forEach(btn => {
      btn.classList.toggle('active', parseInt(btn.dataset.index) === index);
    });
  },

  _detectSubs() {
    const subBtn = document.getElementById('cpSubBtn');
    const subList = document.getElementById('cpSubList');
    if (!subList) return;
    subList.innerHTML = '';

    const offBtn = document.createElement('button');
    offBtn.className = 'cp-sub-item' + (this.currentSubIndex === -1 ? ' active' : '');
    offBtn.textContent = 'Off';
    offBtn.addEventListener('click', () => this._selectSub(-1));
    subList.appendChild(offBtn);

    this.subtitleTracks.forEach((t, i) => {
      const btn = document.createElement('button');
      btn.className = 'cp-sub-item' + (this.currentSubIndex === i ? ' active' : '');
      btn.textContent = t.label + (t.language ? ' (' + t.language + ')' : '');
      btn.dataset.index = i;
      btn.addEventListener('click', () => this._selectSub(i));
      subList.appendChild(btn);
    });

    if (this.subtitleTracks.length > 0) {
      subBtn.style.display = '';
      if (this.currentSubIndex >= this.subtitleTracks.length) this.currentSubIndex = -1;
      this._selectSub(this.currentSubIndex >= 0 ? this.currentSubIndex : 0);
    } else {
      subBtn.style.display = 'none';
    }
  },

  async _loadEmbeddedSubs(subPath) {
    if (!subPath) return;
    if (this.subCache[subPath]) {
      this.subtitleTracks = this.subCache[subPath];
      if (this.subtitleTracks.length) this._detectSubs();
      return;
    }
    const tracks = [];
    try {
      const r = await fetch('/api/subtitles/' + encodeURIComponent(subPath));
      const d = await r.json();
      if (!d.success || !d.tracks || !d.tracks.length) {
        this.subCache[subPath] = tracks;
        this.subtitleTracks = tracks;
        return;
      }
      const textCodecs = ['subrip', 'ass', 'ssa', 'text', 'webvtt', 'srt', 'vtt'];
      for (const track of d.tracks) {
        if (track.type === 'local') {
          try {
            const sr = await fetch('/api/subtitles/' + encodeURIComponent(subPath) + '?track=' + track.index + '&local=1');
            if (!sr.ok) continue;
            const text = await sr.text();
            if (!text.trim()) continue;
            let cues = this._parseSrt(text);
            if (!cues.length) cues = this._parseVtt(text);
            if (!cues.length) continue;
            tracks.push({ label: track.title || track.file.split('/').pop(), language: track.language || 'und', cues });
          } catch (_) {}
        } else if (track.type === 'embedded' && textCodecs.includes(track.codec)) {
          try {
            const sr = await fetch('/api/subtitles/' + encodeURIComponent(subPath) + '?track=' + track.index);
            if (!sr.ok) continue;
            const text = await sr.text();
            if (!text.trim()) continue;
            const cues = this._parseSrt(text);
            if (!cues.length) continue;
            tracks.push({ label: track.title || track.language || ('Track ' + track.index), language: track.language || 'und', cues });
          } catch (_) {}
        }
      }
      this.subCache[subPath] = tracks;
      this.subtitleTracks = tracks;
      if (tracks.length) this._detectSubs();
    } catch (e) { console.warn('[Player] Subtitle detection failed:', e); }
  },

  _loadSubPrefs() {
    const size = localStorage.getItem('cpSubSize') || '1em';
    const bg = localStorage.getItem('cpSubBg') || 'rgba(0,0,0,0.75)';
    const color = localStorage.getItem('cpSubColor') || 'white';
    document.getElementById('cpSubSize').value = size;
    document.getElementById('cpSubBg').value = bg;
    document.getElementById('cpSubColor').value = color;
    if (this.subOverlay) {
      this.subOverlay.style.setProperty('--sub-size', size);
      this.subOverlay.style.setProperty('--sub-bg', bg);
      this.subOverlay.style.setProperty('--sub-color', color);
    }
  },

  _startHistory() {
    this._stopHistory();
    const match = this.currentTrack?.url ? this._getPathFromUrl(this.currentTrack.url) : null;
    if (!match) return;
    this.histPath = match;
    this.histTitle = this.currentTrack?.title || '';
    const token = localStorage.getItem('token');
    this.histInterval = setInterval(() => {
      const v = this.video;
      if (!v || !v.duration || !v.currentTime) return;
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = 'Bearer ' + token;
      fetch('/api/history/update', {
        method: 'POST', headers,
        body: JSON.stringify({
          media_path: this.histPath,
          title: this.histTitle,
          position_sec: v.currentTime,
          duration_sec: v.duration,
          completed: (v.currentTime / v.duration) > 0.9
        })
      }).catch(() => {});
    }, 30000);
  },

  _stopHistory() {
    if (this.histInterval) { clearInterval(this.histInterval); this.histInterval = null; }
    this.histPath = null;
    this.histTitle = null;
  },

  stop() {
    this.video.pause();
    this._stopHistory();
    this._stopTranscodePoll();
    this._stopCountdown();
    this.video.removeAttribute('src');
    this.video.load();
    this.currentTrack = null;
    this.currentSubPath = null;
    this._currentMediaTitle = null;
    this.subtitleTracks = [];
    this.currentSubIndex = -1;
    if (this.subOverlay) this.subOverlay.innerHTML = '';
    document.getElementById('cpSubPanel').style.display = 'none';
    document.getElementById('cpSubSearchPanel').style.display = 'none';
    document.getElementById('cpAdjPanel').style.display = 'none';
    document.getElementById('cpShortcuts').style.display = 'none';
    document.getElementById('cpInfoPanel').style.display = 'none';
    document.getElementById('cpSubBtn').style.display = 'none';
    document.getElementById('cpError').style.display = 'none';
    document.getElementById('cpSpinner').style.display = 'none';
    this.el.classList.remove('cp-mini', 'cp-maximized', 'cp-mode-audio', 'cp-mode-video');
    document.body.classList.remove('cp-player-visible', 'cp-mode-audio');
    document.body.style.paddingBottom = '';
    document.getElementById('cpSizeBtn').innerHTML = this._svg('theater', 16);
    document.getElementById('cpSizeBtn').title = 'Theater mode (T)';
    document.getElementById('cpMiniBtn').innerHTML = this._svg('mini', 16);
    document.getElementById('cpMiniBtn').title = 'Mini Player';
    this.video.style.filter = '';
    this.hide();
  },

  show() {
    if (!this.el) return;
    this.el.style.display = '';
    document.getElementById('cpCenterPlay').style.display = '';
    document.getElementById('cpControls').style.opacity = '1';
    document.getElementById('cpControls').style.pointerEvents = '';
    const title = this.currentTrack?.title || '';
    document.getElementById('cpTime').textContent = '0:00 / 0:00';
    document.getElementById('cpProgress').style.width = '0%';
    document.getElementById('cpBuffer').style.width = '0%';
    document.getElementById('cpSeek').value = 0;
    document.getElementById('cpPlayBtn').innerHTML = this._svg('play', 18);
    document.getElementById('cpRateBtn').innerHTML = this._svg('speed', 16) + ' ' + this.playbackRate + 'x';
    this.video.playbackRate = this.playbackRate;

    // Audio UI
    if (this._mode === 'audio') {
      document.getElementById('cpAudioTime').textContent = '0:00';
      document.getElementById('cpAudioDuration').textContent = '0:00';
      document.getElementById('cpAudioProgress').style.width = '0%';
      document.getElementById('cpAudioSeek').value = 0;
      document.getElementById('cpAudioTitle').textContent = title || this.currentTrack?.title || '-';
      const art = document.getElementById('cpAudioArt');
      art.innerHTML = this._svg('music', 48);
      art.style.background = '';
    }

    // Dynamic body padding so content isn't hidden behind player
    document.body.classList.add('cp-player-visible');
    setTimeout(() => {
      const h = this.el.offsetHeight;
      if (h > 0) document.body.style.paddingBottom = (h + 16) + 'px';
    }, 100);
  },

  hide() {
    if (this.el) this.el.style.display = 'none';
  },

  _navMedia(dir) {
    if (typeof window.currentMediaList === 'undefined' || !window.currentMediaList.length) return;
    let idx = window.currentMediaIndex + dir;
    if (idx < 0 || idx >= window.currentMediaList.length) return;
    window.currentMediaIndex = idx;
    const m = window.currentMediaList[idx];
    if (!m) return;
    document.getElementById('cpPrevBtn').style.display = idx > 0 ? '' : 'none';
    document.getElementById('cpNextBtn').style.display = idx < window.currentMediaList.length - 1 ? '' : 'none';
    const ext = m.name.split('.').pop().toLowerCase();
    const isTranscode = !['mp4','webm','ogv'].includes(ext);
    let url = '/api/stream?path=' + encodeURIComponent(m.path);
    if (isTranscode) url += '&transcode=true';
    if (m.position) url += '&t=' + m.position;
    this.play(url, m.name, '', m.path);
  },

  _startCountdown() {
    this._countdownValue = 5;
    const overlay = document.getElementById('cpCountdown');
    const numEl = document.getElementById('cpCountdownNumber');
    const fillEl = document.getElementById('cpCountdownFill');
    const titleEl = document.getElementById('cpCountdownTitle');
    const idx = window.currentMediaIndex + 1;
    const next = window.currentMediaList[idx];
    titleEl.textContent = next ? 'Up next: ' + next.name : 'Next episode in...';
    numEl.textContent = this._countdownValue;
    fillEl.style.width = '100%';
    overlay.style.display = '';
    this.video.pause();
    this._countdownTimer = setInterval(() => {
      this._countdownValue--;
      numEl.textContent = this._countdownValue;
      fillEl.style.width = (this._countdownValue / 5 * 100) + '%';
      if (this._countdownValue <= 0) {
        this._stopCountdown();
        this._navMedia(1);
      }
    }, 1000);
  },

  _stopCountdown() {
    if (this._countdownTimer) { clearInterval(this._countdownTimer); this._countdownTimer = null; }
    document.getElementById('cpCountdown').style.display = 'none';
  },

  async _toggleInfo() {
    const panel = document.getElementById('cpInfoPanel');
    if (panel.style.display !== 'none') { panel.style.display = 'none'; return; }
    document.getElementById('cpSubPanel').style.display = 'none';
    document.getElementById('cpAdjPanel').style.display = 'none';
    const content = document.getElementById('cpInfoContent');
    content.innerHTML = '<div class="cp-info-loading">Loading...</div>';
    panel.style.display = '';
    const path = this.currentTrack?.url ? this._getPathFromUrl(this.currentTrack.url) : null;
    if (!path) { content.innerHTML = '<div class="cp-info-loading">No file info</div>'; return; }
    try {
      const r = await fetch('/api/metadata/' + encodeURIComponent(path));
      const d = await r.json();
      let html = '';
      if (d.width) html += `<div class="cp-info-row"><span>Resolution</span><span>${d.width}x${d.height}</span></div>`;
      if (d.codec) html += `<div class="cp-info-row"><span>Codec</span><span>${d.codec}</span></div>`;
      if (d.fps) html += `<div class="cp-info-row"><span>FPS</span><span>${d.fps}</span></div>`;
      if (d.duration) html += `<div class="cp-info-row"><span>Duration</span><span>${this._fmt(d.duration)}</span></div>`;
      if (d.size) html += `<div class="cp-info-row"><span>Size</span><span>${(d.size / 1048576).toFixed(1)} MB</span></div>`;
      if (d.bit_rate) html += `<div class="cp-info-row"><span>Bitrate</span><span>${(parseInt(d.bit_rate) / 1000).toFixed(0)} kbps</span></div>`;
      if (d.audio) {
        html += `<div class="cp-info-divider"></div>`;
        html += `<div class="cp-info-row"><span>Audio</span><span>${d.audio.codec || ''} ${d.audio.channels || ''}ch ${d.audio.sample_rate ? d.audio.sample_rate/1000 + 'kHz' : ''}</span></div>`;
      }
      if (d.subtitle_count !== undefined) html += `<div class="cp-info-row"><span>Subtitles</span><span>${d.subtitle_count} track(s)</span></div>`;
      if (d.format) html += `<div class="cp-info-row"><span>Container</span><span>${d.format}</span></div>`;
      content.innerHTML = html || '<div class="cp-info-loading">No metadata available</div>';
    } catch (e) {
      content.innerHTML = '<div class="cp-info-loading">Failed to load info</div>';
    }
  },

  _fmt(s) {
    if (!s || !isFinite(s)) return '0:00';
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = Math.floor(s % 60);
    if (h > 0) return h + ':' + m.toString().padStart(2,'0') + ':' + sec.toString().padStart(2,'0');
    return m + ':' + sec.toString().padStart(2,'0');
  }
};

function esc(str) { const d = document.createElement('div'); d.textContent = str; return d.innerHTML; }
document.addEventListener('DOMContentLoaded', () => Player.init());
