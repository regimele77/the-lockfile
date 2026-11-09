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
| `scans` | Scan pipeline (queue, Celery clone, scanners, status UI) |
| `findings` | Finding list/detail with status triage and filters (HTMX); `Finding` model |

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
   9. Open the scan detail page and [/findings/](http://localhost:8000/findings/) for plain-language results
  10. On a finding detail page, mark **Resolved** or **Ignore**, confirm the default findings list and dashboard **Open critical** count update, and use **View on GitHub** when a file path and commit/branch exist

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
3. Permissions (set under **Permissions & events** on the App). Minimum for
   current features:

   | Area | Permission | Why |
   |------|------------|-----|
   | Account | Email addresses: Read-only | Login / user email |
   | Repository | Metadata: Read-only | List repos for sync |
   | Repository | Contents: Read-only | Clone default branch for scans |
   | Repository | Administration: Read-only | Practices scanner (branch protection). Without it, practices emit a low finding and continue. |

   OAuth login also requests `read:user` and `user:email` on the authorize URL.

4. After you change App permissions, open each installation on GitHub
   ([Settings → Applications → Installed GitHub Apps](https://github.com/settings/installations))
   and **Accept** the new permissions. Until then, API calls may return 401/403.
5. Subscribe to webhook events (when webhooks are active):
   - `installation`
   - `installation_repositories`
   - `ping` is handled automatically (returns `pong`)
6. **Where can this GitHub App be installed?** Any account, or only yours.
7. Create the App, then note:
   - App ID
   - Client ID
   - Generate a **Client secret**
   - Generate a **private key** (PEM download). Required to mint installation
     access tokens for repo sync and clone
   - Webhook secret (set the same value in `.env` as `GITHUB_APP_WEBHOOK_SECRET`)
   - App **slug** from the public page: `https://github.com/apps/<slug>`
8. Put those values in `.env` (never commit real secrets):

   | Variable | Purpose |
   |----------|---------|
   | `GITHUB_APP_ID` | App ID (JWT issuer for installation tokens) |
   | `GITHUB_APP_CLIENT_ID` | OAuth client ID |
   | `GITHUB_APP_CLIENT_SECRET` | OAuth client secret |
   | `GITHUB_APP_PRIVATE_KEY` | PEM text with `\n` for newlines (or use `GITHUB_APP_PRIVATE_KEY_PATH`) |
   | `GITHUB_APP_WEBHOOK_SECRET` | HMAC secret for `X-Hub-Signature-256` |
   | `GITHUB_APP_NAME` | Public slug for install URLs |
   | `GITHUB_OAUTH_CALLBACK_URL` | Must match the App callback URL |
   | `GITHUB_TOKEN_FERNET_KEY` | Fernet key encrypting user OAuth tokens at rest |

9. Generate and store a Fernet key for user OAuth tokens:

   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

   Put the output in `GITHUB_TOKEN_FERNET_KEY`. Back up the key; losing it makes
   existing tokens unreadable (users re-connect GitHub). Rotating means decrypt
   with the old key and re-encrypt with the new one, or ask users to re-auth.
   Do not derive this from `DJANGO_SECRET_KEY`. Required when `DJANGO_DEBUG=0`.

10. Restart Compose after editing `.env` so `web` and `worker` pick up the values.

**Callback host:** OAuth completion is restricted to the hostname in
`GITHUB_OAUTH_CALLBACK_URL` (for local Docker: `localhost`).

### Auth and repo access notes

- Flow: `/accounts/github/` → `/accounts/github/start/` → GitHub →
  `/accounts/github/callback/` → Django session → `/dashboard/`
- If the user has no App installations yet, they are sent to the install page;
  `/accounts/github/setup/` records the `installation_id` and redirects to
  `/repositories/connect/`.
- User-to-server OAuth tokens are stored on `GitHubAccount.access_token`,
  encrypted with `GITHUB_TOKEN_FERNET_KEY` (Fernet). Admin and templates never
  show them. Plaintext legacy rows are encrypted on read/migration when a key
  is set. Tokens never appear in logs, flashes, or findings.
- Installation API tokens are short-lived (~1 hour). The app mints them on
  demand with an App JWT (RS256) signed by the private key. They are not
  persisted and must not be treated as permanent.
- Repo sync upserts into `Repository` rows scoped to the `GitHubInstallation`
  (and owning user). Selection (`is_selected`) is chosen on
  `/repositories/connect/`.
- Webhooks at `/accounts/github/webhook/` verify `X-Hub-Signature-256` (raw
  body HMAC, constant-time compare). Delivery id is the log correlation key;
  payload bodies are never logged. A lean `WebhookDeliveryLog` row stores
  delivery id, event, action, and ok/error (no payload). Ignored events return
  HTTP 200 with a short status string so GitHub does not retry-storm.
  - With `GITHUB_APP_WEBHOOK_SECRET` set: invalid/missing signature → 403.
  - Secret empty and `DJANGO_DEBUG=1`: unsigned deliveries accepted (warning log).
  - Secret empty and `DJANGO_DEBUG=0`: fail closed.
  Manual **Refresh from GitHub** remains available without a tunnel.
- Permission / token failures surface clear next steps (re-connect, install /
  accept permissions, refresh repos) on connect, scan detail, and
  `/accounts/profile/`.
- Logout: `POST /accounts/logout/` (existing session logout).

### How to test GitHub App hardening

1. **Webhook**: with a tunnel and `GITHUB_APP_WEBHOOK_SECRET` set, deliver a
   `ping` (or any subscribed event). Expect HTTP 200 and a `WebhookDeliveryLog`
   row. Wrong signature → 403. Locally without a secret and with `DJANGO_DEBUG=1`,
   unsigned delivery is accepted only for convenience.
2. **Token encryption**: after login with `GITHUB_TOKEN_FERNET_KEY` set,
   `GitHubAccount.access_token` in the DB should look like Fernet ciphertext
   (starts with `gAAAAA`), not a raw `gho_` token. Admin still hides the field.
3. **Permission update**: change an App permission on GitHub, then sync or scan
   without accepting. UI should tell you to accept permissions / re-install.
   Accept on the installation, refresh, retry.
4. **Missing repo access**: remove a tracked repo from the installation on
   GitHub, refresh on `/repositories/connect/`, then try a scan (or clone).
   Expect a friendly permission / refresh message, not a raw token leak.

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
- After clone, the worker calls `run_scanners` in `apps/scans/services/scanners/`.
  Findings are stored on the Scan and shown on scan detail, repo detail, and
  `/findings/`.

### Findings

- Each finding has a workflow status: `open` (default), `resolved`, or `ignored`.
  Triage from the finding detail page or compact actions on the list
  (Mark resolved, Ignore, Reopen). POSTs are CSRF-protected and scoped to the
  signed-in user's tracked repos.
- `/findings/` defaults to **open** findings. Status tabs cover open / resolved /
  ignored / all. Severity tabs still work. Additional filters: category,
  repository, and scan (query params, composed together, preserved in HTMX).
- Dashboard counts are limited to your tracked repos. **Open findings** and
  **Open critical** only include `status=open`.
- When a later scan recreates the same issue (`rule_id` + `file_path`, with a
  title fallback), ignored/resolved triage is carried forward so noise is not
  resurrected as open duplicates.
- Findings with a file path link to GitHub when `commit_sha` or `default_branch`
  is available (`/blob/{ref}/{path}` with optional `#L{line}`). Secrets findings
  may include a line number.
- Empty states on dashboard, repositories, scans, and findings guide the loop:
  connect GitHub -> pick repos -> run a scan -> review findings.

**How to test triage:** run a scan -> open a finding -> mark ignored or resolved
-> confirm dashboard open critical and the default findings list update -> use
the GitHub file link when path/commit exist -> sign in as a fresh user (or clear
installations/selection) to hit guided empty states.

### Scanners

Hook: `apps/scans/services/scanners/__init__.py` → `run_scanners(scan, workspace)`.
One scanner failing is logged and skipped; others continue. Re-running scanners
on the same Scan replaces that scan's findings (no duplicate spam).

| Scanner | What it checks |
|---------|----------------|
| Secrets | Common API keys, tokens, private key blocks, and high-entropy secret-like assignments in source/config. Values are redacted in stored findings. |
| Dependencies | Parses common lockfiles/manifests (`package-lock.json`, `yarn.lock`, `requirements.txt`, `poetry.lock`, `Pipfile.lock`, `go.mod`, `Cargo.lock`, `Gemfile.lock`) and looks up known advisories via the [OSV](https://osv.dev/) API. |
| Configs | Heuristics for floating Docker/`compose` `:latest` tags, dangerous GitHub Actions permissions / `pull_request_target` misuse, privileged compose, hard-coded Django `DEBUG = True`, and similar. |
| Practices | GitHub API branch protection on the default branch (required reviews, status checks, force-push, admin enforcement). Needs Administration: Read on the App. |
| Workflows | Gaps in `.github/workflows` (missing CI, dispatch-only, no test-like jobs, secrets echoed to logs, deploy jobs without Environments). |

Limits and toggles (see `.env.example`): `SCANNER_ENABLE_*`, `SCANNER_TIMEOUT_SECONDS`,
`SCANNER_MAX_FINDINGS_PER_SCANNER`, `SCANNER_MAX_FILE_BYTES`, `SCANNER_MAX_FILES`,
`SCANNER_OSV_ENABLED`, `SCANNER_OSV_TIMEOUT_SECONDS`, `SCANNER_OSV_MAX_PACKAGES`,
`SCANNER_GITHUB_TIMEOUT_SECONDS`.

**Honest limits:** these are high-signal heuristics, not a full SAST/DAST suite.
Expect some false positives and some misses (especially for uncommon ecosystems,
encrypted secrets, or private advisory sources). Dependency CVE lookup needs
outbound HTTPS to `api.osv.dev` and degrades gracefully if the network call fails.
Git history secret scanning is not implemented yet (working tree only). Always
read the Explanation and Recommendation on a finding before rotating credentials
or changing production config.

**How to test:** select a repo -> **Run scan** -> open the scan detail page and
`/findings/` for severity, category, summary, and fix steps.

### Frontend (Tailwind)

- Source: `static/src/input.css` (design tokens, type/spacing scale, shared component classes + `@source` for Django templates)
- Output: `static/css/app.css` (always commit a rebuilt `app.css` with UI changes)
- Shared classes: `btn-primary` / `btn-secondary` / `btn-ghost` / `btn-danger`, `field`, `panel` / `notice`, `page-header`, `empty-state`, `data-table` / `table-wrap`, `filter-tab`, severity/status badges, `app-nav-link`, marketing `site-wrap`
- The `frontend` Compose service runs `npm install && npm run watch` so CSS rebuilds when templates or the input CSS change.
- One-shot production build:

  ```bash
  docker compose run --rm frontend npm run build
  ```

Fonts are system UI stacks (`-apple-system` / `Segoe UI` / `system-ui`, with Consolas / `ui-monospace` for code). No webfont CDN. HTMX is pinned via CDN; CSRF is sent on HTMX requests via `hx-headers` on `<body>`.

### Useful URLs

| Path | Notes |
|------|--------|
| `/` | Landing |
| `/privacy/` | Privacy |
| `/terms/` | Terms |
| `/status/` | Health status page |
| `/health/` | JSON health |
| `/accounts/profile/` | Account / GitHub connection health |
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
| `/findings/` | Findings (`?status=`, `?severity=`, `?category=`, `?repository=`, `?scan=`) |
| `/findings/<id>/status/` | POST: resolve / ignore / reopen |
| `/admin/` | Django admin (models registered) |

## License

Source-available. Free for individuals, open-source projects, non-profits, education, and companies with fewer than 10 employees.

Larger companies and anyone offering The Lockfile as a commercial product or hosted service need a commercial license. Contact via [thelockfile.com](https://thelockfile.com).

See [LICENSE](LICENSE) for the full terms.
