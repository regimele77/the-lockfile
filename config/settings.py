from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
)

environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="insecure-dev-key-change-me")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")

SITE_URL = env("SITE_URL", default="https://thelockfile.com")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "django_htmx",
    # Local
    "apps.core",
    "apps.accounts",
    "apps.dashboard",
    "apps.repositories",
    "apps.scans",
    "apps.findings",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.site",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", default="lockfile"),
        "USER": env("POSTGRES_USER", default="lockfile"),
        "PASSWORD": env("POSTGRES_PASSWORD", default="lockfile"),
        "HOST": env("POSTGRES_HOST", default="db"),
        "PORT": env("POSTGRES_PORT", default="5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "accounts:github"
LOGIN_REDIRECT_URL = "dashboard:home"
LOGOUT_REDIRECT_URL = "core:landing"

# GitHub App (user-to-server OAuth + installation groundwork)
# Create an App at https://github.com/settings/apps/new. See README.
GITHUB_APP_ID = env("GITHUB_APP_ID", default="")
GITHUB_APP_CLIENT_ID = env("GITHUB_APP_CLIENT_ID", default="")
GITHUB_APP_CLIENT_SECRET = env("GITHUB_APP_CLIENT_SECRET", default="")
# PEM contents (use literal \n for newlines) or leave blank and set path below.
GITHUB_APP_PRIVATE_KEY = env("GITHUB_APP_PRIVATE_KEY", default="").replace("\\n", "\n")
GITHUB_APP_PRIVATE_KEY_PATH = env("GITHUB_APP_PRIVATE_KEY_PATH", default="")
GITHUB_APP_WEBHOOK_SECRET = env("GITHUB_APP_WEBHOOK_SECRET", default="")
# App slug from the public page URL: https://github.com/apps/<slug>
GITHUB_APP_NAME = env("GITHUB_APP_NAME", default="")
GITHUB_OAUTH_CALLBACK_URL = env(
    "GITHUB_OAUTH_CALLBACK_URL",
    default="http://localhost:8000/accounts/github/callback/",
)
# Fernet key for encrypting GitHubAccount.access_token at rest.
# Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Required outside DEBUG. Do not derive silently from DJANGO_SECRET_KEY.
GITHUB_TOKEN_FERNET_KEY = env("GITHUB_TOKEN_FERNET_KEY", default="")

REDIS_URL = env("REDIS_URL", default="redis://redis:6379/0")
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://redis:6379/1")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True

# Scan pipeline (clone workspace + scheduled re-scans)
SCAN_WORKSPACE_ROOT = env("SCAN_WORKSPACE_ROOT", default="/tmp/lockfile-scans")
SCAN_CLONE_TIMEOUT_SECONDS = env.int("SCAN_CLONE_TIMEOUT_SECONDS", default=300)
SCAN_CLONE_DEPTH = env.int("SCAN_CLONE_DEPTH", default=1)
SCAN_MAX_REPO_SIZE_MB = env.int("SCAN_MAX_REPO_SIZE_MB", default=500)
# Re-scan tracked repos when the last finished scan is older than this many hours.
SCAN_RESCHEDULE_HOURS = env.int("SCAN_RESCHEDULE_HOURS", default=24)
# How often Celery beat checks for due repos (hours).
SCAN_SCHEDULE_CHECK_HOURS = env.int("SCAN_SCHEDULE_CHECK_HOURS", default=1)

# Scanners (run after clone inside the Celery worker)
SCANNER_ENABLE_SECRETS = env.bool("SCANNER_ENABLE_SECRETS", default=True)
SCANNER_ENABLE_DEPENDENCIES = env.bool("SCANNER_ENABLE_DEPENDENCIES", default=True)
SCANNER_ENABLE_CONFIGS = env.bool("SCANNER_ENABLE_CONFIGS", default=True)
SCANNER_ENABLE_PRACTICES = env.bool("SCANNER_ENABLE_PRACTICES", default=True)
SCANNER_ENABLE_WORKFLOWS = env.bool("SCANNER_ENABLE_WORKFLOWS", default=True)
SCANNER_TIMEOUT_SECONDS = env.int("SCANNER_TIMEOUT_SECONDS", default=120)
SCANNER_MAX_FINDINGS_PER_SCANNER = env.int(
    "SCANNER_MAX_FINDINGS_PER_SCANNER", default=50
)
SCANNER_MAX_FILE_BYTES = env.int("SCANNER_MAX_FILE_BYTES", default=512_000)
SCANNER_MAX_FILES = env.int("SCANNER_MAX_FILES", default=8_000)
SCANNER_OSV_ENABLED = env.bool("SCANNER_OSV_ENABLED", default=True)
SCANNER_OSV_TIMEOUT_SECONDS = env.int("SCANNER_OSV_TIMEOUT_SECONDS", default=30)
SCANNER_OSV_MAX_PACKAGES = env.int("SCANNER_OSV_MAX_PACKAGES", default=200)
SCANNER_GITHUB_TIMEOUT_SECONDS = env.int("SCANNER_GITHUB_TIMEOUT_SECONDS", default=20)

CELERY_BEAT_SCHEDULE = {
    "enqueue-due-scans": {
        "task": "apps.scans.tasks.enqueue_due_scans",
        "schedule": timedelta(hours=max(1, SCAN_SCHEDULE_CHECK_HOURS)),
    },
}
