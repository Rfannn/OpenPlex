# Contributing to OpenPlex

Thanks for your interest in contributing! This document provides guidelines for contributing to OpenPlex.

## Development Setup

```bash
git clone https://github.com/Rfannn/OpenPlex.git
cd OpenPlex
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
make run
```

## Code Style

- **Python**: Follow PEP 8, use ruff for linting (`make lint`)
- **Formatting**: Run `make format` before committing
- **Type hints**: Use Python 3.10+ syntax (`list[str]`, `dict[str, Any]`)
- **Async**: Use `async/await` for all I/O operations
- **Imports**: Sorted by isort (via ruff)

## Project Conventions

- **Routers**: One file per feature in `app/routers/`
- **Services**: Business logic in `app/services/`
- **Models**: SQLAlchemy ORM in `app/models/`
- **Templates**: Jinja2 in `templates/`
- **Static files**: CSS/JS in `static/`
- **Tests**: pytest in `tests/`

## Pull Request Process

1. Create a feature branch from `main`
2. Make your changes with tests
3. Run `make test` and `make lint`
4. Update documentation if needed
5. Submit a PR with a clear description

## Reporting Issues

- Use GitHub Issues
- Include steps to reproduce
- Include your environment (OS, Python version, browser)
- Include error messages/screenshots

## Areas for Contribution

- [ ] Tests (currently minimal)
- [ ] Documentation
- [ ] Mobile responsiveness improvements
- [ ] Accessibility (ARIA labels, keyboard nav)
- [ ] Performance optimizations
- [ ] New scraper sources
- [ ] UI/UX improvements
