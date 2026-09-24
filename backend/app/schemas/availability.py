from typing import List
from pydantic import BaseModel, field_validator


class AvailabilityRequest(BaseModel):
    checkIn: str
    checkOut: str
    adults: int

    @field_validator("checkIn", "checkOut")
    @classmethod
    def date_must_be_valid_format(cls, v: str) -> str:
        import re
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            raise ValueError("Date must be in YYYY-MM-DD format")
        return v

    @field_validator("adults")
    @classmethod
    def adults_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("adults must be greater than 0")
        return v


class RoomAvailability(BaseModel):
    room_type: str
    max_adults: int
    available_rooms: int


class AvailabilityResponse(BaseModel):
    available: bool
    check_in: str
    check_out: str
    adults: int
    rooms: List[RoomAvailability]
