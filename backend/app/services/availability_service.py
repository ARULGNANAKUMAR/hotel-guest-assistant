import json
import os
from datetime import date, datetime
from typing import List

from app.schemas.availability import AvailabilityResponse, RoomAvailability

_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "availability_data.json")


def _load_inventory() -> List[dict]:
    with open(_DATA_PATH, "r") as f:
        data = json.load(f)
    return data["rooms"]


def _parse_date(date_str: str) -> date:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"Invalid date: '{date_str}'. Use YYYY-MM-DD format.")


def checkAvailability(checkIn: str, checkOut: str, adults: int) -> AvailabilityResponse:
    """
    Validate inputs and return a deterministic room availability result.
    """
    # Parse dates
    try:
        check_in_date = _parse_date(checkIn)
    except ValueError:
        raise ValueError(f"Invalid check-in date: '{checkIn}'. Use YYYY-MM-DD format.")

    try:
        check_out_date = _parse_date(checkOut)
    except ValueError:
        raise ValueError(f"Invalid check-out date: '{checkOut}'. Use YYYY-MM-DD format.")

    # Validate check-in is not in the past
    today = date.today()
    if check_in_date < today:
        raise ValueError(
            f"Check-in date '{checkIn}' is in the past. Please choose today or a future date."
        )

    # Validate check-out is after check-in (same day rejected)
    if check_out_date <= check_in_date:
        raise ValueError(
            "Check-out date must be after check-in date. Same-day check-in/check-out is not allowed."
        )

    # Validate adults
    if adults <= 0:
        raise ValueError("Number of adults must be greater than 0.")

    # Load inventory and filter by capacity
    inventory = _load_inventory()
    eligible = [
        RoomAvailability(
            room_type=room["room_type"],
            max_adults=room["max_adults"],
            available_rooms=room["available_rooms"],
        )
        for room in inventory
        if room["max_adults"] >= adults
    ]

    return AvailabilityResponse(
        available=len(eligible) > 0,
        check_in=checkIn,
        check_out=checkOut,
        adults=adults,
        rooms=eligible,
    )
