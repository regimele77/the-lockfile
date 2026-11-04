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
| `accounts` | GitHub App OAuth login, installation tokens, webhooks |
| `dashboard` | Signed-in overview (HTMX-refreshed stats) |
| `repositories` | Repo sync, connect picker, list/detail; `Repository` model |
| `scans` | Scan pipeline (queue, Celery clone, status UI); scanners placeholder |
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

6. Test GitHub access, repo selection, and scans:
   1. `docker compose up --build` (web, worker, and beat must all be up)
   2. Open [Connect with GitHub](http://localhost:8000/accounts/github/) and authorize / install the App
   3. Open [/repositories/connect/](http://localhost:8000/repositories/connect/)
   4. Click **Refresh from GitHub** (or rely on the post-login sync)
   5. Select the repos to track, click **Save selection**
   6. Confirm them on [/repositories/](http://localhost:8000/repositories/)
   7. Open a repo and click **Run scan** (or use **Scan selected** on the list)
   8. Watch [/scans/](http://localhost:8000/scans/) move queued -> running -> completed or failed

   Real vulnerability / secret / config scanners are still out of scope. A successful
   scan currently completes after clone with zero findings.

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
   - **Webhook URL**: `http://localhost:8000/accounts/github/webhook/`
     - GitHub cannot reach localhost directly. For live webhook delivery, put a
       tunnel in front (ngrok, Cloudflare Tunnel, etc.) and use the public HTTPS
       URL ending in `/accounts/github/webhook/`.
     - You can leave webhooks inactive locally and use **Refresh from GitHub**
       on `/repositories/connect/` instead.
3. Permissions (minimum for login, repo listing, and cloning):
   - **Account permissions → Email addresses**: Read-only
   - **Repository permissions → Metadata**: Read-only (required to list repos)
   - **Repository permissions → Contents**: Read-only (required to clone for scans)
   - Later: Dependabot alerts and other scanner-specific permissions as needed
4. Subscribe to webhook events (when webhooks are active):
   - `installation`
   - `installation_repositories`
5. **Where can this GitHub App be installed?** Any account, or only yours.
6. Create the App, then note:
   - App ID
   - Client ID
   - Generate a **Client secret**
   - Generate a **private key** (PEM download). Required to mint installation
     access tokens for repo sync
   - Webhook secret (set the same value in `.env` as `GITHUB_APP_WEBHOOK_SECRET`)
   - App **slug** from the public page: `https://github.com/apps/<slug>`
7. Put those values in `.env` (never commit real secrets):

   | Variable | Purpose |
   |----------|---------|
   | `GITHUB_APP_ID` | App ID (JWT issuer for installation tokens) |
   | `GITHUB_APP_CLIENT_ID` | OAuth client ID |
   | `GITHUB_APP_CLIENT_SECRET` | OAuth client secret |
   | `GITHUB_APP_PRIVATE_KEY` | PEM text with `\n` for newlines (or use `GITHUB_APP_PRIVATE_KEY_PATH`) |
   | `GITHUB_APP_WEBHOOK_SECRET` | HMAC secret for `X-Hub-Signature-256` |
   | `GITHUB_APP_NAME` | Public slug for install URLs |
   | `GITHUB_OAUTH_CALLBACK_URL` | Must match the App callback URL |

8. Restart Compose after editing `.env` so `web` picks up the values.

**Callback host:** OAuth completion is restricted to the hostname in
`GITHUB_OAUTH_CALLBACK_URL` (for local Docker: `localhost`).

### Auth and repo access notes

- Flow: `/accounts/github/` → `/accounts/github/start/` → GitHub →
  `/accounts/github/callback/` → Django session → `/dashboard/`
- If the user has no App installations yet, they are sent to the install page;
  `/accounts/github/setup/` records the `installation_id` and redirects to
  `/repositories/connect/`.
- User-to-server access tokens are stored on `GitHubAccount` and excluded from
  admin/templates.
- Installation API tokens are short-lived (~1 hour). The app mints them on
  demand with an App JWT (RS256) signed by the private key. They are not
  persisted and must not be treated as permanent.
- Repo sync upserts into `Repository` rows scoped to the `GitHubInstallation`
  (and owning user). Selection (`is_selected`) is chosen on
  `/repositories/connect/`.
- Webhooks at `/accounts/github/webhook/` verify `X-Hub-Signature-256` and keep
  installations / repo membership current. Manual **Refresh from GitHub** is
  always available.
- Logout: `POST /accounts/logout/` (existing session logout).

### Scans

- Start from a repository detail page (**Run scan**) or the repository list
  (**Scan selected** / per-row **Run scan**). Only tracked repos for the
  signed-in user are allowed. Duplicate queued/running scans for the same repo
  are rejected.
- Lifecycle: `queued` -> Celery worker -> `running` (clone) -> `completed` or
  `failed`, with `started_at` / `finished_at`. Failure text is sanitized and
  shown on the scan detail page (HTMX polls while active).
- Clone uses a short-lived installation access token, shallow clone of the
  default branch, and a per-scan workspace under `SCAN_WORKSPACE_ROOT` that is
  always removed afterward. Tokens are never logged or stored on the Scan row.
- Celery beat calls `enqueue_due_scans` on an interval (`SCAN_SCHEDULE_CHECK_HOURS`,
  default 1h). Tracked repos whose last finished scan is older than
  `SCAN_RESCHEDULE_HOURS` (default 24h), or never scanned, get a scheduled scan.
  Active queued/running scans are skipped.
- Scanner hook: `apps/scans/services/scanners.py` (`run_scanners`). Placeholder
  for the next milestone.

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
| `/accounts/github/webhook/` | GitHub App webhooks (signature verified) |
| `/dashboard/` | App home |
| `/repositories/` | Tracked (selected) repos; bulk scan |
| `/repositories/connect/` | Sync + pick repos to track |
| `/repositories/<id>/scan/` | POST: start scan for one repo |
| `/scans/` | Scan list |
| `/scans/<id>/` | Scan detail (status + errors; HTMX poll) |
| `/findings/` | Findings (+ `?severity=` HTMX filter) |
| `/admin/` | Django admin (models registered) |

## License

Source-available. Free for individuals, open-source projects, non-profits, education, and companies with fewer than 10 employees.

Larger companies and anyone offering The Lockfile as a commercial product or hosted service need a commercial license. Contact via [thelockfile.com](https://thelockfile.com).

See [LICENSE](LICENSE) for the full terms.
