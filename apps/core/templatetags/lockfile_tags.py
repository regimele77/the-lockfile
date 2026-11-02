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
}


@register.inclusion_tag("partials/severity_badge.html")
def severity_badge(severity: str):
    key = (severity or "").lower()
    return {
        "severity": key,
        "label": key.capitalize() if key else "Unknown",
        "css_class": SEVERITY_CLASSES.get(key, "badge-info"),
    }


@register.inclusion_tag("partials/status_badge.html")
def status_badge(status: str):
    key = (status or "").lower()
    return {
        "status": key,
        "label": key.capitalize() if key else "Unknown",
        "css_class": STATUS_CLASSES.get(key, "status-queued"),
    }


@register.simple_tag
def nav_active(request, *url_names: str) -> str:
    """Return 'active' when the current URL name matches one of the given names."""
    if request is None or not hasattr(request, "resolver_match") or request.resolver_match is None:
        return ""
    current = request.resolver_match.view_name
    return "active" if current in url_names else ""


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
