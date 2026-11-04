from urllib.parse import urlencode

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

SEVERITY_CLASSES = {
    "critical": "badge-critical",
    "high": "badge-high",
    "medium": "badge-medium",
    "low": "badge-low",
    "info": "badge-info",
}

STATUS_CLASSES = {
    "queued": "status-queued",
    "running": "status-running",
    "completed": "status-completed",
    "failed": "status-failed",
    "open": "status-open",
    "resolved": "status-resolved",
    "ignored": "status-ignored",
}


@register.inclusion_tag("partials/severity_badge.html")
def severity_badge(severity: str):
    key = (severity or "").lower()
    return {
        "severity": key,
        "label": key.capitalize() if key else "Unknown",
        "css_class": SEVERITY_CLASSES.get(key, "badge-info"),
    }


STATUS_LABELS = {
    "queued": "Queued",
    "running": "Running",
    "completed": "Completed",
    "failed": "Failed",
    "open": "Open",
    "resolved": "Resolved",
    "ignored": "Ignored",
}


@register.inclusion_tag("partials/status_badge.html")
def status_badge(status: str):
    key = (status or "").lower()
    return {
        "status": key,
        "label": STATUS_LABELS.get(key, key.capitalize() if key else "Unknown"),
        "css_class": STATUS_CLASSES.get(key, "status-queued"),
    }


@register.simple_tag
def nav_active(request, *url_names: str) -> str:
    """Return 'active' when the current URL name matches one of the given names."""
    if request is None or not hasattr(request, "resolver_match") or request.resolver_match is None:
        return ""
    current = request.resolver_match.view_name
    return "active" if current in url_names else ""


@register.simple_tag(takes_context=True)
def findings_filter_qs(context, **overrides) -> str:
    """
    Build a findings list query string, preserving active filters.

    Pass clear_<name>=1 (or an empty override) to drop a filter. Default status
    is open and is omitted from the URL.
    """
    request = context.get("request")
    get = request.GET if request is not None else {}
    params = {}
    for key in ("status", "severity", "category", "repository", "scan"):
        if key in overrides:
            value = overrides[key]
        else:
            value = get.get(key, "")
        value = ("" if value is None else str(value)).strip()
        if key == "status":
            if not value:
                value = "open"
            if value == "open":
                continue
        if value:
            params[key] = value
    return urlencode(params)


@register.filter
def severity_bar_width(severity: str) -> str:
    widths = {
        "critical": "100%",
        "high": "80%",
        "medium": "55%",
        "low": "30%",
        "info": "15%",
    }
    return widths.get((severity or "").lower(), "10%")


@register.simple_tag(takes_context=True)
def scan_number(context, scan) -> int:
    """1-based scan ordinal for the signed-in user (1 = newest). Not a DB id."""
    request = context.get("request")
    if request is None or not getattr(request, "user", None):
        return 0
    if not request.user.is_authenticated or scan is None:
        return 0
    from apps.scans.services.display import scan_ordinal

    return scan_ordinal(request.user, scan)


@register.simple_tag
def lockfile_mark() -> str:
    """Inline SVG mark: document + lock (inherits currentColor)."""
    return mark_safe(
        '<svg class="lockfile-mark" viewBox="0 0 32 32" aria-hidden="true" focusable="false">'
        '<path fill="currentColor" d="M7 4h12l6 6v18H7V4z"/>'
        '<path fill="#fff" fill-opacity="0.92" d="M19 4v6h6"/>'
        '<path fill="#fff" d="M12 14.5V12a4 4 0 0 1 8 0v2.5h-1.8V12a2.2 2.2 0 0 0-4.4 0v2.5H12z"/>'
        '<rect x="11" y="14.5" width="10" height="9" rx="1.2" fill="#fff"/>'
        '<circle cx="16" cy="18.2" r="1.35" fill="currentColor"/>'
        '<rect x="15.35" y="18.8" width="1.3" height="2.4" rx="0.4" fill="currentColor"/>'
        "</svg>"
    )
