import json
import re
from pathlib import Path
from typing import Any, Optional

# Load hotel data once at module import time, relative to this file's location.
_DATA_FILE = Path(__file__).parent.parent / "data" / "hotel_data.json"

_hotel_data: Optional[dict] = None
_load_error: Optional[str] = None

try:
    with open(_DATA_FILE, encoding="utf-8") as f:
        _hotel_data = json.load(f)
except FileNotFoundError:
    _load_error = f"Hotel data file not found: {_DATA_FILE}"
except json.JSONDecodeError as e:
    _load_error = f"Hotel data file is not valid JSON: {e}"


# ---------------------------------------------------------------------------
# Intent keywords — order matters: more specific entries come first.
# ---------------------------------------------------------------------------
_INTENT_KEYWORDS: list[tuple[str, list[str]]] = [
    ("check_in",      ["check in", "check-in", "checkin", "arrival time", "arrive"]),
    ("check_out",     ["check out", "check-out", "checkout", "departure time", "depart", "leave by"]),
    ("breakfast",     ["breakfast", "morning meal", "dining hours", "restaurant hours"]),
    ("pool",          ["pool", "swimming", "swim"]),
    ("wifi",          ["wifi", "wi-fi", "internet", "wireless"]),
    ("parking",       ["parking", "car park", "park my car"]),
    ("cancellation",  ["cancel", "cancellation", "refund policy", "booking policy"]),
    ("rooms",         ["room type", "room types", "types of room", "available rooms",
                       "what rooms", "which rooms", "accommodation", "suite", "deluxe"]),
    ("hotel_info",    ["about the hotel", "tell me about", "hotel name", "what hotel"]),
    ("availability",  ["available tomorrow", "available tonight", "available on", "book a room",
                       "reserve a room", "room available", "any rooms available"]),
]


def _normalize(text: str) -> str:
    """Lowercase, strip, collapse whitespace, remove trailing punctuation."""
    text = text.lower().strip()
    text = re.sub(r"[?!.,;:]+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def detect_intent(message: str) -> str:
    """Return the detected intent string, or 'unknown'."""
    normalized = _normalize(message)
    for intent, keywords in _INTENT_KEYWORDS:
        for kw in keywords:
            if kw in normalized:
                return intent
    return "unknown"


def get_answer(intent: str) -> tuple[str, str]:
    """
    Return (response_message, response_type) for the given intent.
    Falls back gracefully if hotel data failed to load.
    """
    if _load_error or _hotel_data is None:
        return (
            "I'm sorry, the hotel information is temporarily unavailable. Please try again later.",
            "error",
        )

    hotel = _hotel_data

    if intent == "check_in":
        t = hotel["check_in"]["time"]
        d = hotel["check_in"]["details"]
        return f"Check-in starts at {t}. {d}", "text"

    if intent == "check_out":
        t = hotel["check_out"]["time"]
        d = hotel["check_out"]["details"]
        return f"Check-out is at {t}. {d}", "text"

    if intent == "breakfast":
        b = hotel["breakfast"]
        if b["available"]:
            return (
                f"Yes, breakfast is available. {b['details']}",
                "text",
            )
        return "Breakfast is not currently offered at this hotel.", "text"

    if intent == "pool":
        p = hotel["amenities"]["pool"]
        if p["available"]:
            return p["details"], "text"
        return "The hotel does not currently have a swimming pool.", "text"

    if intent == "wifi":
        w = hotel["amenities"]["wifi"]
        if w["available"]:
            return w["details"], "text"
        return "Wi-Fi is not available at this hotel.", "text"

    if intent == "parking":
        p = hotel["amenities"]["parking"]
        if p["available"]:
            return p["details"], "text"
        return "Parking is not available at this hotel.", "text"

    if intent == "cancellation":
        c = hotel["cancellation_policy"]
        return f"{c['summary']} {c['details']}", "text"

    if intent == "rooms":
        names = [r["name"] for r in hotel["rooms"]]
        room_list = ", ".join(names[:-1]) + f", and {names[-1]}" if len(names) > 1 else names[0]
        return (
            f"We offer the following room types: {room_list}. "
            "Please contact the hotel or check our booking page for more details on each room.",
            "text",
        )

    if intent == "hotel_info":
        h = hotel["hotel"]
        return f"{h['name']} — {h['description']}", "text"

    if intent == "availability":
        return (
            "Room availability checking is not yet available through this assistant. "
            "Please contact the hotel directly or use the booking page to check availability.",
            "text",
        )

    # unknown
    return (
        "I don't have that information in the hotel knowledge base yet. "
        "I can help with check-in, check-out, breakfast, swimming pool, Wi-Fi, "
        "parking, cancellation policy, and room types.",
        "fallback",
    )


def get_data() -> Optional[dict[str, Any]]:
    """Return the raw hotel data dict (for internal use)."""
    return _hotel_data
