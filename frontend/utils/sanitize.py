"""HTML sanitization utilities to prevent XSS."""

import html
from typing import Any

try:
    import bleach
    HAS_BLEACH = True
except ImportError:
    HAS_BLEACH = False


# Allowed tags for directive content (no scripts, no event handlers)
ALLOWED_TAGS = [
    "p", "br", "strong", "em", "u", "b", "i",
    "ul", "ol", "li", "blockquote", "code", "pre",
    "h1", "h2", "h3", "h4", "h5", "h6",
]

# Allowed attributes (none for security)
ALLOWED_ATTRIBUTES = {}


def escape_text(value: Any) -> str:
    """Escape text for safe HTML embedding."""
    if value is None:
        return ""
    return html.escape(str(value)).replace("\n", "<br>")


def escape_attr(value: Any) -> str:
    """Escape text for use inside an HTML attribute value.

    Newlines are preserved (not converted to <br>), and quotes are escaped.
    """
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def sanitize_html(value: Any) -> str:
    """Sanitize HTML content to prevent XSS.

    Uses bleach if available, otherwise falls back to escaping.
    """
    text = str(value or "")
    if HAS_BLEACH:
        return bleach.clean(
            text,
            tags=ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
            strip=True,
        )
    # Fallback: escape everything
    return escape_text(text)


def sanitize_directive_content(value: Any) -> str:
    """Sanitize directive section content - allows basic formatting."""
    return sanitize_html(value)


def safe_member_value(member: dict[str, Any], key: str, fallback: str = "Not provided") -> str:
    """Safely get and escape a member dictionary value."""
    return escape_text(member.get(key, fallback))
