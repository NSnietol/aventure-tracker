"""Shared utilities for email templates."""

from datetime import datetime, timedelta, timezone

# Colombia timezone: UTC-5 (no DST)
_TZ_COLOMBIA = timezone(timedelta(hours=-5))

# Sender address used in all outgoing emails
RESEND_FROM = "Adventure Tracker <onboarding@resend.dev>"

# Event accent colors cycling
EVENT_COLORS = ["#e65100", "#7b1fa2", "#0277bd", "#2d6a4f", "#c62828", "#00695c"]

# Emojis by keyword match (best-effort)
_EVENT_EMOJIS: dict[str, str] = {
    "salto": "🧗",
    "canyoning": "💦",
    "torrentismo": "💦",
    "rafting": "🌊",
    "nocturno": "🌙",
    "río": "🏞",
    "rio": "🏞",
    "paramo": "🌿",
    "páramo": "🌿",
    "nevado": "🏔",
    "bosque": "🌲",
    "caverna": "🕳",
    "ciclismo": "🚵",
    "playa": "🏖",
    "isla": "🏝",
    "mar": "⛵",
    "pueblo": "🏘",
}


def now_colombia() -> datetime:
    """Return current datetime in Colombia timezone (UTC-5)."""
    return datetime.now(_TZ_COLOMBIA)


def event_emoji(name: str) -> str:
    """Return a best-effort emoji for the given event name.

    Args:
        name: Event name to match against known keywords.

    Returns:
        Matching emoji string, or the default camping emoji.
    """
    name_lower = name.lower()
    for key, emoji in _EVENT_EMOJIS.items():
        if key in name_lower:
            return emoji
    return "🏕"
