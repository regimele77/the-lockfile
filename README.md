# The Lockfile

**Know what's inside your code.**

Self-hosted open-source software security platform.

[thelockfile.com](https://thelockfile.com)

## What it does

The Lockfile scans your GitHub repositories for security problems, insecure configs, missing security practices, vulnerable dependencies, exposed secrets, and weak spots in your development workflow.

Findings come with clear explanations and recommendations, so you don't need to be a security expert to act on them.

## Why self-hosted

Everything runs on your own infrastructure. Repo data, scan results, and reports stay with you. You connect a GitHub App, pick which repos to scan, and go.

Supports public and private repos. Private access goes through GitHub's normal permission system.

## Stack

- Python / Django 6
- PostgreSQL
- Celery + Redis
- Tailwind CSS 4 + HTMX
- Docker Compose

## Architecture (application base)

Django apps live under `apps/`:

| App | Role |
|-----|------|
| `core` | Landing page, health check, shared context processors & template tags |
| `accounts` | GitHub connect stub / logout / profile shell |
| `dashboard` | Authenticated overview (HTMX-refreshed stats) |
| `repositories` | Repo list/detail + connect stub; `Repository` model |
| `scans` | Scan list/detail; `Scan` model with status |
| `findings` | Finding list/detail with severity filters (HTMX); `Finding` model |

Templates: project-level `templates/` (base, layouts, partials) plus per-app templates. Product UI extends `layouts/app.html`.

## Run locally

1. Install and start [Docker Desktop](https://www.docker.com/products/docker-desktop/).
2. Copy the example env file:

   ```bash
   cp .env.example .env
   ```

3. From the project root, build and start everything:

   ```bash
   docker compose up --build
   ```

   Services: `db`, `redis`, `frontend` (Tailwind watch), `web`, `worker`, `beat`.

4. Open:
   - Marketing: [http://localhost:8000/](http://localhost:8000/)
   - Health: [http://localhost:8000/health/](http://localhost:8000/health/) → `{"status": "ok", "service": "the-lockfile"}`
   - Dashboard (login required): [http://localhost:8000/dashboard/](http://localhost:8000/dashboard/)

5. Auth will be GitHub App–based (no password login). For local UI exploration only, create a Django superuser and use the admin, or temporarily authenticate via the shell. Product CTAs point at `/accounts/github/`.

Stop with `Ctrl+C`, or run in the background with `docker compose up --build -d` and stop later with `docker compose down`.

### Frontend (Tailwind)

- Source: `static/src/input.css` (design tokens + `@source` for Django templates)
- Output: `static/css/app.css`
- The `frontend` Compose service runs `npm install && npm run watch` so CSS rebuilds when templates or the input CSS change.
- One-shot production build:

  ```bash
  docker compose run --rm frontend npm run build
  ```

Fonts are system stacks (Tahoma / Consolas) — no webfont CDN. HTMX is pinned via CDN; CSRF is sent on HTMX requests via `hx-headers` on `<body>`.

### Useful URLs

| Path | Notes |
|------|--------|
| `/` | Landing |
| `/privacy/` | Privacy |
| `/terms/` | Terms |
| `/status/` | Health status page |
| `/health/` | JSON health |
| `/accounts/github/` | GitHub connect stub |
| `/dashboard/` | App home |
| `/repositories/` | Repo list |
| `/repositories/connect/` | Connect GitHub App stub |
| `/scans/` | Scan list |
| `/findings/` | Findings (+ `?severity=` HTMX filter) |
| `/admin/` | Django admin (models registered) |

## License

Source-available. Free for individuals, open-source projects, non-profits, education, and companies with fewer than 10 employees.

Larger companies and anyone offering The Lockfile as a commercial product or hosted service need a commercial license — contact via [thelockfile.com](https://thelockfile.com).

See [LICENSE](LICENSE) for the full terms.
