# The Lockfile

**Know what's inside your code.**

Self-hosted open-source software security platform.

[thelockfile.com](https://thelockfile.com)

## What it does

The Lockfile scans GitHub repos for security problems: insecure config, missing
practices, vulnerable dependencies, exposed secrets, and gaps in how you ship.

Findings include a short explanation and a recommended fix.

## Why self-hosted

It runs on your infrastructure. Repo data, scan results, and reports stay with you.
Connect a GitHub App, pick repos, and scan.

Public and private repos are supported. Private access uses GitHub's normal
permission system.

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
| `core` | Landing page, health check, shared context processors and template tags |
| `accounts` | GitHub App OAuth login, logout, profile, installation groundwork |
| `dashboard` | Signed-in overview (HTMX-refreshed stats) |
| `repositories` | Repo list/detail and connect page; `Repository` model |
| `scans` | Scan list/detail; `Scan` model with status |
| `findings` | Finding list/detail with severity filters (HTMX); `Finding` model |

Templates: project-level `templates/` (base, layouts, partials) plus per-app templates. Product UI extends `layouts/app.html`.

## Run locally

1. Install and start [Docker Desktop](https://www.docker.com/products/docker-desktop/).
2. Copy the example env file:

   ```bash
   cp .env.example .env
   ```

3. Create a GitHub App and fill the GitHub env vars (see below).
4. From the project root, build and start everything:

   ```bash
   docker compose up --build
   ```

   Services: `db`, `redis`, `frontend` (Tailwind watch), `web`, `worker`, `beat`.

5. Open:
   - Marketing: [http://localhost:8000/](http://localhost:8000/)
   - Health: [http://localhost:8000/health/](http://localhost:8000/health/) -> `{"status": "ok", "service": "the-lockfile"}`
   - Connect: [http://localhost:8000/accounts/github/](http://localhost:8000/accounts/github/)
   - Dashboard (after GitHub login): [http://localhost:8000/dashboard/](http://localhost:8000/dashboard/)

6. Test auth: **Connect with GitHub** → authorize / install → land on `/dashboard/`.

Stop with `Ctrl+C`, or run in the background with `docker compose up --build -d` and stop later with `docker compose down`.

### Create a GitHub App (local Docker)

There is no username/password login. Identity and repo access come from a
**GitHub App** (not a plain OAuth App).

1. Open [GitHub → Settings → Developer settings → GitHub Apps → New GitHub App](https://github.com/settings/apps/new).
2. Fill in:
   - **GitHub App name**: e.g. `The Lockfile Local`
   - **Homepage URL**: `http://localhost:8000/`
   - **Callback URL**: `http://localhost:8000/accounts/github/callback/`
   - **Setup URL** (optional but recommended): `http://localhost:8000/accounts/github/setup/`
   - **Webhook**: uncheck Active for local login-only work, or set a URL later
3. Permissions (minimum for this milestone + future repo read):
   - **Account permissions → Email addresses**: Read-only
   - **Repository permissions → Metadata**: Read-only (always required)
   - Later for scanning: Contents (read), Dependabot alerts, etc. as needed
4. **Where can this GitHub App be installed?** Any account, or only yours.
5. Create the App, then note:
   - App ID
   - Client ID
   - Generate a **Client secret**
   - Generate a **private key** (PEM download) — needed later for installation tokens
   - App **slug** from the public page: `https://github.com/apps/<slug>`
6. Put those values in `.env` (never commit real secrets):

   | Variable | Purpose |
   |----------|---------|
   | `GITHUB_APP_ID` | App ID |
   | `GITHUB_APP_CLIENT_ID` | OAuth client ID |
   | `GITHUB_APP_CLIENT_SECRET` | OAuth client secret |
   | `GITHUB_APP_PRIVATE_KEY` | PEM text with `\n` for newlines (or use `GITHUB_APP_PRIVATE_KEY_PATH`) |
   | `GITHUB_APP_WEBHOOK_SECRET` | Optional until webhooks are wired |
   | `GITHUB_APP_NAME` | Public slug for install URLs |
   | `GITHUB_OAUTH_CALLBACK_URL` | Must match the App callback URL |

7. Restart Compose after editing `.env` so `web` picks up the values.

**Callback host:** OAuth completion is restricted to the hostname in
`GITHUB_OAUTH_CALLBACK_URL` (for local Docker: `localhost`).

### Auth notes

- Flow: `/accounts/github/` → `/accounts/github/start/` → GitHub →
  `/accounts/github/callback/` → Django session → `/dashboard/`
- If the user has no App installations yet, they are sent to the install page;
  `/accounts/github/setup/` records the `installation_id`.
- User-to-server access tokens are stored on `GitHubAccount` and excluded from
  admin/templates. Installation API tokens are short-lived (~1h); mint on demand
  with the App private key later — do not treat them as permanent.
- Logout: `POST /accounts/logout/` (existing session logout).

### Frontend (Tailwind)

- Source: `static/src/input.css` (design tokens + `@source` for Django templates)
- Output: `static/css/app.css`
- The `frontend` Compose service runs `npm install && npm run watch` so CSS rebuilds when templates or the input CSS change.
- One-shot production build:

  ```bash
  docker compose run --rm frontend npm run build
  ```

Fonts are system stacks (Tahoma / Consolas). No webfont CDN. HTMX is pinned via CDN; CSRF is sent on HTMX requests via `hx-headers` on `<body>`.

### Useful URLs

| Path | Notes |
|------|--------|
| `/` | Landing |
| `/privacy/` | Privacy |
| `/terms/` | Terms |
| `/status/` | Health status page |
| `/health/` | JSON health |
| `/accounts/github/` | Start GitHub connect |
| `/accounts/github/callback/` | OAuth callback |
| `/accounts/github/setup/` | App setup / install callback |
| `/dashboard/` | App home |
| `/repositories/` | Repo list |
| `/repositories/connect/` | Installations connected |
| `/scans/` | Scan list |
| `/findings/` | Findings (+ `?severity=` HTMX filter) |
| `/admin/` | Django admin (models registered) |

## License

Source-available. Free for individuals, open-source projects, non-profits, education, and companies with fewer than 10 employees.

Larger companies and anyone offering The Lockfile as a commercial product or hosted service need a commercial license. Contact via [thelockfile.com](https://thelockfile.com).

See [LICENSE](LICENSE) for the full terms.
