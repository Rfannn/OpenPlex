# OpenPlex

A self-hosted media server with library browsing, AI-powered chat, download management, and multi-source content discovery.

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi)
![License](https://img.shields.io/badge/License-MIT-green)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker)
[![Roadmap](https://img.shields.io/badge/roadmap-v2.2-blue)](ROADMAP.md)
[![Status](https://img.shields.io/badge/status-beta-yellow)](STATUS.md)

## Features

- **Netflix-style Library** — Hero banner, genre rows, continue watching, TMDB trending
- **AI Chat Assistant** — Agnes AI primary with local llama-server fallback
- **Download Manager** — aria2-powered with SSE progress, scheduling, speed limits
- **Multi-source Catalog** — DonyayeSerial, AzFilm, MyF2M scrapers with health monitoring
- **Media Player** — Custom player with subtitle support, transcoding, resume playback
- **File Browser** — Grid/list views, search, upload, rename, context menus
- **Metadata Enrichment** — TMDB, OMDb, Fanart.tv, TVDb integration
- **Subtitle Search** — OpenSubtitles + sub-plus.ir auto-fetching
- **PWA Support** — Installable, offline-capable service worker
- **Mobile Responsive** — Bottom tab navigation, touch gestures
- **Settings Dashboard** — Edit all API keys, AI config, scraper settings

## Quick Start

### Docker (Recommended)

```bash
git clone https://github.com/Rfannn/OpenPlex.git
cd OpenPlex
cp .env.example .env
# Edit .env with your API keys
docker compose up -d
```

### Manual Setup

```bash
git clone https://github.com/Rfannn/OpenPlex.git
cd OpenPlex
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your settings
make run
```

Open http://localhost:8185

## Configuration

Copy `.env.example` to `.env` and configure:

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes | Random secret for JWT tokens |
| `MEDIA_ROOT` | Yes | Path to your media files |
| `AGNES_API_KEY` | Recommended | Agnes AI for chat features |
| `TMDB_API_KEY` | Optional | Movie/TV metadata |
| `OMDB_API_KEY` | Optional | Backup metadata source |
| `FANART_API_KEY` | Optional | High-res artwork |
| `TVDB_API_KEY` | Optional | Enhanced TV metadata |
| `OPENSUBTITLES_API_KEY` | Optional | Auto subtitle fetching |

Full configuration available in the **Settings** page at `/settings`.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/register` | POST | Create account |
| `/api/auth/login` | POST | Get JWT token |
| `/api/library/rows` | GET | Netflix-style rows |
| `/api/library/search` | GET | Search catalog |
| `/api/catalog-search` | GET | Search local + scrapers |
| `/api/downloads` | GET/POST | Download management |
| `/api/chat/stream` | GET | AI chat (SSE) |
| `/api/subtitles/search` | GET | Find subtitles |
| `/api/settings` | GET/POST | Server settings (admin) |
| `/api/health/detailed` | GET | Health checks |

Full API docs at `/docs` (Swagger UI).

## Tech Stack

- **Backend**: FastAPI, SQLAlchemy (async), SQLite, aria2c
- **Frontend**: Vanilla JS, CSS custom properties, PWA
- **AI**: Agnes AI (primary), llama-server (fallback)
- **Metadata**: TMDB, OMDb, Fanart.tv, TVDb
- **Deployment**: Docker, systemd

## Project Structure

```
OpenPlex/
├── app/
│   ├── main.py           # FastAPI app, middleware, lifespan
│   ├── config.py          # Pydantic settings
│   ├── database.py        # SQLAlchemy async engine
│   ├── dependencies.py    # Auth, JWT
│   ├── models/            # ORM models
│   ├── routers/           # API endpoints
│   └── services/          # Business logic
├── static/                # CSS, JS, icons
├── templates/             # Jinja2 HTML
├── tests/                 # Pytest tests
├── deploy/                # systemd service
├── Dockerfile
├── docker-compose.yml
├── Makefile
└── pyproject.toml
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing`)
5. Open a Pull Request

## License

MIT License — see [LICENSE](LICENSE) for details.
