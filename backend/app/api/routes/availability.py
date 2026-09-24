from fastapi import APIRouter, HTTPException

from app.schemas.availability import AvailabilityRequest, AvailabilityResponse
from app.services.availability_service import checkAvailability

router = APIRouter()


@router.post("/availability", response_model=AvailabilityResponse)
def check_availability(request: AvailabilityRequest) -> AvailabilityResponse:
    """
    Check room availability for the given check-in, check-out dates and number of adults.
    Returns a deterministic list of eligible room types.
    """
    try:
        result = checkAvailability(
            checkIn=request.checkIn,
            checkOut=request.checkOut,
            adults=request.adults,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return result
