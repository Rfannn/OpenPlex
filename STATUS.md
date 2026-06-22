# OpenPlex Project Status

Last updated: June 23, 2026

## Stable & Production-Ready

These features are mature, well-tested, and safe for everyday use.

- **Library browsing** — row display, search, filtering, genre browsing
- **Authentication** — JWT-based login/register system
- **Media player** — video playback with subtitle support, transcoding, resume
- **File browser** — grid/list views, upload, rename, delete, context menus
- **Docker deployment** — fully working docker-compose setup
- **Settings dashboard** — all configuration accessible via UI
- **PWA support** — installable, service worker caching

---

## Beta / Experimental

These features work but may have rough edges.

- **AI chat assistant** — works with Agnes API; fallback to local llama-server (performance varies by hardware)
- **Multi-source scrapers** — DonyayeSerial, AzFilm, MyF2M; can break if upstream sites change HTML structure
- **Download manager** — aria2 integration works; scheduling and speed limits need more testing
- **Metadata enrichment** — TMDB/OMDb/Fanart/TVDb pipeline works; some sources have rate limits
- **AI file categorization** — heuristic + AI hybrid; accuracy depends on model

---

## Known Issues & Limitations

### Major Issues

| Issue | Status | Workaround |
|-------|--------|------------|
| Transcoding can be slow on low-end hardware | Investigating | Disable transcoding, use direct stream |
| Some scrapers fail occasionally | Known | Try different source or enable auto-fallback |
| Local AI fallback uses 4-8GB RAM | Design limitation | Use Agnes API for lower memory usage |

### Minor Issues

| Issue | Status | Workaround |
|-------|--------|------------|
| Subtitle sync off by a few seconds | Known | Adjust manually using player controls |
| Mobile UI sometimes cuts off text | Working on it | Use landscape mode temporarily |
| Windows manual setup not well tested | Help wanted | Use WSL2 or Docker |

### Missing Features

- User profiles and permissions
- Watch history sync across devices
- Automatic library scanning (requires manual trigger)
- Music library support
- Plugin system

---

## Test Coverage Summary

| Component | Coverage | Status |
|-----------|----------|--------|
| Authentication | 65% | Improving |
| Library service | 45% | Needs work |
| API routes | 30% | Low priority |
| Scrapers | 20% | Hard to test (external dependencies) |
| AI service | 10% | Help wanted |
| Download manager | 25% | Improving |

---

## How You Can Help

### High Priority

1. **Add tests** — especially for library and download services
2. **Scraper maintenance** — keep scrapers updated when sites change
3. **Windows support** — test and fix issues on Windows manual setup
4. **Documentation** — write guides, FAQ, improve existing docs
5. **UI polish** — fix mobile responsiveness issues

### Getting Started

1. Check the `good first issue` label on GitHub
2. Read [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions
3. Open an issue for bugs or feature requests
4. Test with your own media library and report findings

---

## Release History

| Version | Date | Key Changes |
|---------|------|-------------|
| v2.1 | Jun 20, 2026 | OpenPlex rebrand, Agnes AI, unified nav, settings page |
| v2.0 | Jun 15, 2026 | Initial open-source release |

---

## Questions?

- Check GitHub Discussions
- Open an issue for bugs
- Read the [README](README.md) for setup help
