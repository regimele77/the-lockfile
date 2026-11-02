# The Lockfile

**Know what's inside your code.**

Self-hosted open-source software security platform.

[thelockfile.dev](https://thelockfile.dev)

## What it does

The Lockfile scans your GitHub repositories for security problems, insecure configs, missing security practices, vulnerable dependencies, exposed secrets, and weak spots in your development workflow.

Findings come with clear explanations and recommendations, so you don't need to be a security expert to act on them.

## Why self-hosted

Everything runs on your own infrastructure. Repo data, scan results, and reports stay with you. You connect a GitHub App, pick which repos to scan, and go.

Supports public and private repos. Private access goes through GitHub's normal permission system.

## Stack

- Python / Django
- PostgreSQL
- Celery + Redis
- Docker

## License

Source-available. Free for individuals, open-source projects, non-profits, education, and companies with fewer than 10 employees.

Larger companies and anyone offering The Lockfile as a commercial product or hosted service need a commercial license — contact via [thelockfile.dev](https://thelockfile.dev).

See [LICENSE](LICENSE) for the full terms.
