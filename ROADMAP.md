# OpenPlex Roadmap

This document outlines the planned development path for OpenPlex. Features and timelines may change based on community feedback and contributions.

## v2.2 — "Community & Stability" (Q3 2026)

**Focus:** Solidify the foundation, improve reliability, and make contribution easier.

### Core Improvements
- [ ] Expanded test coverage — unit & integration tests for all major services
- [ ] Enhanced logging — structured logging with log rotation for easier debugging
- [ ] Performance optimizations — database query optimization, caching layer
- [ ] Docker improvements — multi-stage build for smaller image size

### Features
- [ ] User management — multiple accounts with permission levels (Admin/User/Guest)
- [ ] Watch lists — per-user watch lists and personalized recommendations
- [ ] Subtitle management — manual subtitle upload and better sync tools
- [ ] Media scanner improvements — automatic library scanning on file changes

### Documentation
- [ ] API reference — complete API documentation with examples
- [ ] Troubleshooting guide — common issues and solutions
- [ ] Contributor guide — development setup, coding standards, PR process

---

## v3.0 — "Next Generation" (Q1 2027)

**Focus:** Advanced features, deeper integrations, and user experience polish.

### Advanced Features
- [ ] Transcoding farm — distributed transcoding with multiple worker nodes
- [ ] User profiles — separate profiles with watch history and preferences
- [ ] Smart playlists — auto-generated playlists based on user behavior
- [ ] Parental controls — content filtering and viewing restrictions

### Integrations
- [ ] Trakt.tv — scrobble watch progress and sync watch lists
- [ ] Sonarr/Radarr — direct integration for automated media acquisition
- [ ] Home Assistant — voice control and automation triggers
- [ ] OIDC support — Single Sign-On (SSO) with OAuth providers

### AI/ML
- [ ] Personalized recommendations — ML-based suggestions based on viewing habits
- [ ] Content tagging — automatic genre/tag suggestions using AI
- [ ] Voice commands — voice-controlled browsing and playback

---

## Ideas & Experiments (Backlog)

Features we're exploring but haven't committed to yet:

- Mobile apps (iOS/Android)
- Plex/Jellyfin media import tool
- Collaborative watch parties (sync playback across users)
- Music library support (audio streaming, playlists)
- 4K HDR transcoding optimizations
- Anime-specific metadata sources (AniDB, MyAnimeList)
- Plugin system for custom scrapers

---

## Contributing to the Roadmap

Have an idea? Open an issue with the `enhancement` label or start a discussion.

Priority is given to features that align with OpenPlex's vision of being:

- **Self-hosted first** — you own your data
- **Modern** — clean UI, PWA, latest tech
- **Feature-rich** — AI, scraping, downloads, all in one
- **Community-driven** — built by and for users

---

**Legend:**
- ✅ Done — feature is implemented and stable
- 🟡 In progress — actively being worked on
- ⬜ Planned — planned for future release
- 💭 Considering — still evaluating feasibility
