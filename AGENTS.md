# OpenPlex — Milestone Tracker

## Current Status
🟢 **Phase**: Build — All P0/P1/P2 done; Rebranded to OpenPlex; unified nav; multi-source scrapers; systemd running 24/7

---

## Milestones

### P0 — Critical Fixes (Done)
- [x] Step 0: Remove recently added from index.html
- [x] Step 1: SQLite pool_size=5 + WAL mode
- [x] Step 2: Cache file list + async os.walk (30s TTL)
- [x] Step 3: Fix MKV transcoding (capture stderr, fix ffmpeg cmd, fix seek)
- [x] Step 4: Fix thumbnail timestamp (15% of duration)
- [x] Step 5: Integrate MajidAPI GPT for AI categorization
- [x] Step 13: Robust MKV transcode (DTS/TrueHD retry without audio + fail marker)

### P1 — Feature Improvements (Done)
- [x] Step 6: SSE for download progress
- [x] Step 7: Resume playback modal
- [x] Step 8: Integrate FilmRail/FilmZi for metadata enrichment
- [x] Step 9: Unified navbar with sub-menus + profile features
- [x] Step 10: Mobile responsive
- [x] Step 11: Subtitle support (sub-plus.ir + subzone.ir + local .srt)
- [x] Step 12: PWA install (manifest.json + sw.js)
- [x] Step 14: Gallery page removed (route/template/JS/nav all cleaned up)
- [x] Step 15: TMDB integration (search, recommendations, genres, backdrop, cast)
- [x] Step 16: Library page rebuilt as Netflix-style UI (hero, rows, detail modal, search)
- [x] Step 17: Player gestures (volume/brightness swipe) + new icons
- [x] Step 18: Toast queue with action buttons (Open/Play on download complete)
- [x] Step 19: Cache-bust ?v=5 + SW mg-v4
- [x] Step 20: AzFilm fully removed (scraper, router, enricher, updater)
- [x] Step 21: Add to Queue flow (modal + queue-options + season-episodes endpoints)
- [x] Step 22: AI categorization local-heuristic fallback (MajidAPI token invalid)
- [x] Step 23: Dead azfilm cover URLs migrated to TMDB proxy
- [x] Step 24: Local categorizer title/year/genre regex tightened
- [x] Step 25: Integrated OMDb API as TMDB backup metadata source
- [x] Step 26: Integrated Fanart.tv for high-res backdrops/covers
- [x] Step 27: Integrated TVDb API for enhanced TV metadata
- [x] Step 28: Integrated OpenSubtitles API for auto subtitle fetching
- [x] Step 29: Comprehensive logging across all routers/services (middleware + per-endpoint debug)
- [x] Step 30: Dockerfile + docker-compose.yml (port 80 via iptables redirect)
- [x] Step 31: Fix subtitle search 404 (route ordering)
- [x] Step 32: Fix API status "unreachable" display (backend + frontend)
- [x] Step 33: Register AzfilmScraper as 2nd active scraper
- [x] Step 34: Archive caching for DonyayeSerialScraper (5-min TTL)
- [x] Step 35: Scraper health monitoring (auto-disable after 3 fails + cooldown)
- [x] Step 36: Reliability bumps (timeout 5→15s, retries 1→2, archive URL env var)
- [x] Step 37: Scraper health endpoint + status page per-scraper details
- [x] Step 38: systemd service for 24/7 operation (media-server + iptables)
- [x] Step 39: Fix "start_year" artifact (scraper strips literal + hourly scheduled cleanup)
- [x] Step 40: Transcode seek restart (kill old ffmpeg on seek re-request for instant seeking)
- [x] Step 41: Fix player.js transcode poll (properly restore seek position on cache ready)
- [x] Step 42: Fix library page detail modal (TMDB items without catalog id)
- [x] Step 43: Library hero image preload for faster backdrop loading
- [x] Step 44: File upload page (/upload) with chunked support + per-user folder (Uploads/{username}/)
- [x] Step 45: Upload file browser (browse, delete, new folder, download from uploads)
- [x] Step 46: Profile page (/profile) with display name editor
- [x] Step 47: 15 pre-defined color avatars (SVG) with picker on profile page
- [x] Step 48: Unified user dropdown across all pages (Profile, Uploads, Files, Library, Downloads, Status)

### P3 — Rebrand & Quality (In Progress)
- [x] Step 49: Rebrand Media Gallery → OpenPlex (all templates, manifest, Python, deploy)
- [x] Step 50: Unified navigation component (static/nav.js) — desktop top nav + mobile bottom nav
- [x] Step 51: Multi-source DonyayeSerial scrapers (primary + secondary archive fallback)
- [x] Step 52: Remove verify=False from scraper HTTP clients (security hardening)
- [x] Step 53: Fix catalog search (return partial DB results on scraper timeout)
- [x] Step 54: Fix library search (expanded to year, title_type, genres fields)
- [x] Step 55: Add ruff config + Makefile (linting, formatting, run targets)
- [x] Step 56: Git repo init + first commit to github.com/Rfannn/OpenPlex
- [ ] Step 57: Player/subtitle fixes (show sub button, local subtitle matching)
- [ ] Step 58: Tests (auth + catalog + downloads)
- [ ] Step 59: Alembic baseline migration
- [ ] Step 60: Code splitting (downloads_utils.py, library_utils.py)
- [ ] Step 61: AI-powered downloads (action-tag interception in chat)
- [ ] Step 62: README + documentation + screenshots

---

## API Stack

| Service | Endpoint | Purpose |
|---------|----------|---------|
| TMDB | `api.themoviedb.org/3` | Primary metadata: backdrop, cast, recommendations, genres |
| OMDb | `omdbapi.com` | Metadata backup (movie plot/ratings, 1000/day free) |
| Fanart.tv | `webservice.fanart.tv/v3` | High-res movie/TV backdrops & posters |
| TVDb | `api4.thetvdb.com/v4` | Enhanced TV metadata (episodes, seasons, artwork) |
| OpenSubtitles | `api.opensubtitles.com` | Auto subtitle search/download (100/day free) |
| MajidAPI | `gpt/35`, `gpt/4` | AI file categorization |
| sub-plus.ir | `POST api.php` | Subtitle search/download |
| subzone.ir | scrape | Subtitle fallback |

## Config

### Required env vars (`.env` or OS env)
```
MAJIDAPI_TOKEN=csdacfpxjyx34dl:b4iRIAWcaXUQMXnqurr6
# Optional — set any of these to enable their respective services:
TMDB_API_KEY=6bcdd489ea3e04cb5f6f1dae99885e55
OMDB_API_KEY=997790ad
FANART_API_KEY=c35712dc5f7b6f614b2d4813331d1516
TVDB_API_KEY=89128038-e5e4-48bd-b30c-fcce3e5d4166
OPENSUBTITLES_USERNAME=yogurt67
OPENSUBTITLES_PASSWORD=92362765
OPENSUBTITLES_API_KEY=wa98R5u4cEJxDlr9b7pLJEKTSsfgFzZc
```
