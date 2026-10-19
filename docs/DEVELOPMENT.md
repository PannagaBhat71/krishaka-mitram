# Development Guide

## Quick Start

```bash
# Clone
git clone <repo-url>
cd "Krishaka Mitram"

# Virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .\.venv\Scripts\Activate.ps1

# Dependencies
pip install -r requirements.txt

# Redis (required for WebSocket chat)
docker run -d -p 6380:6379 --name krishaka-redis redis:7-alpine

# Environment
export DEBUG=true
export SECRET_KEY="django-insecure-dev-only-key-change-in-production"
export REDIS_URL="redis://127.0.0.1:6380/0"

# Database & static
python manage.py migrate
python manage.py load_agri_data

# Run servers (two terminals)
# Terminal 1: HTTP
python manage.py runserver

# Terminal 2: WebSocket
daphne -b 127.0.0.1 -p 8001 kisan.asgi:application

# Visit http://127.0.0.1:8000/
```

## Project Structure Deep Dive

### Settings Modules

| File | Purpose | Use Case |
|------|---------|----------|
| `kisan/settings.py` | Main settings | Production & local dev |
| `kisan/test_settings.py` | Test-only settings | `python manage.py test --settings=kisan.test_settings` |
| `kisan/settings.local.py` | Local overrides (gitignored) | Personal dev tweaks |

**Never commit** `settings.local.py` or `.env` files.

### Key Configuration in `settings.py`

```python
# Environment-driven
DEBUG = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 'yes')
SECRET_KEY = os.environ.get('SECRET_KEY')  # Required in production
ALLOWED_HOSTS = ['*']  # Appends RENDER_EXTERNAL_HOSTNAME automatically

# Database: PostgreSQL via DATABASE_URL, else SQLite
# Channels: Redis via REDIS_URL (prod), InMemory (dev)
```

## Running Tests

```bash
# All tests (87 tests, ~1s)
python manage.py test --settings=kisan.test_settings -v2

# Specific apps
python manage.py test chat moderation --settings=kisan.test_settings -v2

# With coverage (install coverage first)
pip install coverage
coverage run --source='.' manage.py test --settings=kisan.test_settings
coverage report -m
coverage html  # open htmlcov/index.html
```

### Test Settings Explained

`kisan/test_settings.py` is **completely independent** — it does NOT import from production settings. This avoids the `SECRET_KEY` validation error.

| Setting | Test Value | Why |
|---------|------------|-----|
| `DEBUG` | `True` | Better error messages |
| `SECRET_KEY` | Fixed test key | No env var needed |
| `DATABASES` | SQLite `:memory:` | Fast, isolated |
| `CHANNEL_LAYERS` | `InMemoryChannelLayer` | No Redis needed |
| `PASSWORD_HASHERS` | `MD5PasswordHasher` | Fast hashing |
| `SECURE_SSL_REDIRECT` | `False` | Tests run over HTTP |
| `MAILERS` | `locmem.EmailBackend` | Capture emails |

## Common Development Tasks

### Adding a New Model Field

```bash
# 1. Edit model (e.g., farmer/models.py)
# 2. Create migration
python manage.py makemigrations farmer

# 3. Review migration file
cat farmer/migrations/000X_*.py

# 4. Apply
python manage.py migrate

# 5. Test
python manage.py test farmer --settings=kisan.test_settings
```

### Creating a New App

```bash
# 1. Create app structure
python manage.py startapp newapp

# 2. Add to INSTALLED_APPS in settings.py
INSTALLED_APPS = [
    ...
    'newapp',
]

# 3. Create models, views, urls, templates
# 4. Create and run migrations
python manage.py makemigrations newapp
python manage.py migrate

# 5. Add tests in newapp/tests.py
```

### Working with WebSockets Locally

**Option A: Two servers (recommended for debugging)**
```bash
# Terminal 1: Django dev server (HTTP)
python manage.py runserver

# Terminal 2: Daphne (WebSocket)
daphne -b 127.0.0.1 -p 8001 kisan.asgi:application
```
- HTTP: `http://127.0.0.1:8000/`
- WS: `ws://127.0.0.1:8001/ws/chat/<id>/`

**Option B: Single Daphne (closer to production)**
```bash
daphne -b 127.0.0.1 -p 8000 kisan.asgi:application
```
- Both HTTP and WS on port 8000

**Frontend WebSocket URL** (in `chat_detail.html`):
```javascript
const wsUrl = `ws://${window.location.host}/ws/chat/${conversationId}/`;
// If using separate ports:
const wsUrl = `ws://127.0.0.1:8001/ws/chat/${conversationId}/`;
```

### Debugging Moderation Filter Engine

```python
# Quick test in Django shell
python manage.py shell

>>> from moderation.filters import message_filter_engine
>>> result = message_filter_engine.filter_message("Call me at 9876543210")
>>> print(result.is_clean)           # False
>>> print(result.filtered_content)   # "Call me at [PHONE REDACTED]"
>>> print(result.filter_types)       # ['phone', 'keyword']
>>> for v in result.violations:
...     print(f"{v.rule_type}: {v.detected_text} ({v.severity})")
```

### Loading Seed Data

```bash
# Load Karnataka agricultural dataset
python manage.py load_agri_data

# This creates 10 Crop records and sample Farmer listings
# Images served from farmer/crop_images/ via STATICFILES_DIRS
```

### Creating Moderation Filter Rules

```bash
# Via Django admin
python manage.py createsuperuser
# Visit /admin/ → Moderation → Filter Rules → Add

# Or via shell
python manage.py shell
>>> from moderation.models import FilterRule
>>> FilterRule.objects.create(
...     name="Custom Phone Pattern",
...     pattern=r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b",
...     rule_type="phone",
...     severity="high",
...     action="block"
... )
```

## Code Style & Conventions

### Python
- **Type hints** for new functions/classes
- **Docstrings** for public methods (Google or NumPy style)
- **Imports**: stdlib → third-party → local
- **Max line length**: 100 chars (soft)

```python
# Good
def filter_message(self, content: str) -> FilterResult:
    """Filter a message for sensitive content.
    
    Args:
        content: Raw message text from user.
        
    Returns:
        FilterResult with filtered_content and violations.
    """
    ...
```

### Templates
- Extend `base.html` using `{% extends 'base.html' %}`
- Use `{% block content %}` for main content
- Use `data-i18n` attributes for translatable text
- Bootstrap 5 classes for styling
- Minimal inline CSS/JS (use static files if needed)

```html
{% extends 'base.html' %}
{% block title %}My Page{% endblock %}
{% block content %}
<div class="container">
    <h1 data-i18n="page_title">My Page</h1>
</div>
{% endblock %}
```

### JavaScript (in templates)
- Vanilla ES6+ (no build step)
- Keep in `{% block extra_js %}` in templates
- Use `data-i18n` / `data-i18n-ph` for dynamic text
- Event delegation for dynamic content

## Database Utilities

```bash
# Show all migrations
python manage.py showmigrations

# Show migration plan (what would run)
python manage.py migrate --plan

# SQL for migration (review before applying)
python manage.py sqlmigrate farmer 0003

# Django shell with models
python manage.py shell
>>> from farmer.models import Farmer, Crop
>>> Farmer.objects.count()
>>> Crop.objects.all()

# DB shell (direct SQL)
python manage.py dbshell
```

## Debugging Tips

### Common Issues

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| `SECRET_KEY` error | Env var not set | `export DEBUG=true` or set `SECRET_KEY` |
| WebSocket 404 | Daphne not running | Start `daphne` on correct port |
| Redis connection error | Wrong port | Use 6380 (dev), 6379 (prod) |
| 301 redirects in tests | `SECURE_SSL_REDIRECT=True` | Use `--settings=kisan.test_settings` |
| CSRF failure on AJAX | Missing token | Add `X-CSRFToken` header |
| Static files 404 | Not collected | `python manage.py collectstatic` |

### Logging

Add temporary logging in `settings.py`:
```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'loggers': {
        'chat': {'handlers': ['console'], 'level': 'DEBUG'},
        'moderation': {'handlers': ['console'], 'level': 'DEBUG'},
        'django.channels': {'handlers': ['console'], 'level': 'DEBUG'},
    },
}
```

### Django Debug Toolbar (Optional)

```bash
pip install django-debug-toolbar

# settings.py (only when DEBUG=True)
if DEBUG:
    INSTALLED_APPS += ['debug_toolbar']
    MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']
    INTERNAL_IPS = ['127.0.0.1']
```

## Working with Git

### Branch Strategy
- `main` — production-ready
- `feature/*` — new features
- `fix/*` — bug fixes
- `docs/*` — documentation only

### Commit Message Format
```
<type>(<scope>): <subject>

<body>

<footer>
```
Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

### Pre-commit Checks (Recommended)
```bash
pip install pre-commit
pre-commit install

# .pre-commit-config.yaml
repos:
  - repo: https://github.com/psf/black
    rev: 24.1.1
    hooks:
      - id: black
  - repo: https://github.com/pycqa/flake8
    rev: 7.1.1
    hooks:
      - id: flake8
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.8.0
    hooks:
      - id: mypy
```

## Useful Management Commands

```bash
# Custom commands
python manage.py load_agri_data           # Load Karnataka crop data
python manage.py purge_expired_moderation_data --dry-run  # Preview purge
python manage.py purge_expired_moderation_data --force    # Force purge

# Django built-in
python manage.py check                    # System checks
python manage.py check --deploy           # Production checks
python manage.py showmigrations           # Migration status
python manage.py makemigrations --check   # Check for pending migrations
python manage.py createsuperuser          # Admin user
python manage.py changepassword <user>    # Reset password
python manage.py dumpdata > backup.json   # Export data
python manage.py loaddata backup.json     # Import data
python manage.py shell_plus               # Enhanced shell (if django-extensions installed)
```

## IDE Setup (VS Code)

### Recommended Extensions
- Python (Microsoft)
- Django (batisteo)
- Django Template (mrjul)
- Pylance (type checking)
- Black Formatter
- isort

### Settings (`.vscode/settings.json`)
```json
{
    "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
    "python.testing.pytestEnabled": false,
    "python.testing.unittestEnabled": true,
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
        "source.organizeImports": "explicit"
    },
    "[python]": {
        "editor.defaultFormatter": "ms-python.black-formatter"
    }
}
```

## Troubleshooting Checklist

- [ ] Virtual environment activated?
- [ ] Dependencies installed (`pip install -r requirements.txt`)?
- [ ] Redis running on port 6380?
- [ ] `DEBUG=true` and `SECRET_KEY` set?
- [ ] Migrations applied (`python manage.py migrate`)?
- [ ] Static files collected (if testing production build)?
- [ ] Using correct settings module for tests (`--settings=kisan.test_settings`)?
- [ ] Daphne running for WebSocket tests?

## Performance Profiling

```bash
# Install profiling tools
pip install django-silk py-spy

# Add to settings.py (temporary)
# INSTALLED_APPS += ['silk']
# MIDDLEWARE += ['silk.middleware.SilkyMiddleware']
# SILKY_PYTHON_PROFILER = True

# Visit /silk/ for request profiling
# Or use py-spy for CPU profiling:
py-spy record -o profile.svg -- python manage.py runserver
```

---

## Contributing Workflow

1. **Fork & clone**
2. **Create branch**: `git checkout -b feature/my-feature`
3. **Make changes** with tests
4. **Run tests**: `python manage.py test --settings=kisan.test_settings`
5. **Run checks**: `python manage.py check --settings=kisan.test_settings`
6. **Format code**: `black .` (if using black)
7. **Commit**: `git commit -m "feat(chat): add typing indicator"`
8. **Push & PR**: `git push origin feature/my-feature`