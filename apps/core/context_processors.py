from django.conf import settings


def site(request):
    return {
        "SITE_NAME": "The Lockfile",
        "SITE_TAGLINE": "Know what's inside your code.",
        "SITE_URL": getattr(settings, "SITE_URL", "https://thelockfile.com"),
    }
