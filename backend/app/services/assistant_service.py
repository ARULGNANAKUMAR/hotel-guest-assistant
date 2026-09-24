import re
from typing import Optional

from app.schemas.assistant import AssistantRequest, AssistantResponse, ConversationContext
from app.services import knowledge_service
from app.services.availability_service import checkAvailability
from app.services import llm_service

# ---------------------------------------------------------------------------
# Availability intent keywords
# ---------------------------------------------------------------------------
_AVAILABILITY_KEYWORDS = [
    "do you have a room",
    "do you have availability",
    "can i book a room",
    "i need a room",
    "is there a room",
    "check room availability",
    "room available",
    "rooms available",
    "availability",
    "book a room",
    "reserve a room",
    "can i stay",
    "i want to stay",
    "i'd like to stay",
    "i would like to stay",
]

# Natural-language date patterns — not ISO, so we cannot parse them
_NATURAL_DATE_PATTERNS = [
    r"\b(tomorrow|yesterday|today)\b",
    r"\b(next|this|last)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|week|weekend|month)\b",
    r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b",
    r"\b(next week|this weekend|next weekend)\b",
]

_ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
# Negative-lookbehind on '-' prevents matching '-1 adults' as 1 adult.
_ADULTS_RE = re.compile(
    r"(?:for\s+|we\s+are\s+|we\s+have\s+|party\s+of\s+|group\s+of\s+)?(?<!-)(\d+)\s+adults?\b",
    re.IGNORECASE,
)


def _normalize(text: str) -> str:
    t = text.lower().strip()
    t = re.sub(r"[?!.,;:]+", "", t)
    t = re.sub(r"\s+", " ", t)
    return t


def _is_availability_intent(message: str) -> bool:
    norm = _normalize(message)
    return any(kw in norm for kw in _AVAILABILITY_KEYWORDS)


def _has_natural_date(message: str) -> bool:
    norm = _normalize(message)
    return any(re.search(p, norm, re.IGNORECASE) for p in _NATURAL_DATE_PATTERNS)


def _extract_iso_dates(message: str):
    return _ISO_DATE_RE.findall(message)


def _extract_adults(message: str) -> Optional[int]:
    m = _ADULTS_RE.search(message)
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# Context merging
# ---------------------------------------------------------------------------

def _merge_context(
    existing: Optional[ConversationContext],
    message: str,
) -> ConversationContext:
    """
    Merge information extracted from the new message into the existing context.
    New values always override old ones when explicitly present.
    Missing extractions fall back to existing context values.
    """
    base = existing or ConversationContext()

    iso_dates = _extract_iso_dates(message)
    new_adults = _extract_adults(message)
    new_check_in = iso_dates[0] if len(iso_dates) >= 1 else None
    new_check_out = iso_dates[1] if len(iso_dates) >= 2 else None

    return ConversationContext(
        checkIn=new_check_in or base.checkIn,
        checkOut=new_check_out or base.checkOut,
        adults=new_adults if new_adults is not None else base.adults,
        last_intent=base.last_intent,
    )


# ---------------------------------------------------------------------------
# Availability handler
# ---------------------------------------------------------------------------

def _handle_availability(
    message: str,
    ctx: ConversationContext,
) -> AssistantResponse:
    """
    Check if all availability info is present (from merged context); if not,
    ask only for what is still missing.
    """
    # Natural-language date guard — message contains natural date but no ISO date
    if _has_natural_date(message) and not _ISO_DATE_RE.search(message):
        updated_ctx = ConversationContext(
            checkIn=ctx.checkIn,
            checkOut=ctx.checkOut,
            adults=ctx.adults,
            last_intent="availability",
        )
        return AssistantResponse(
            message=(
                "Please provide your check-in and check-out dates in YYYY-MM-DD format "
                "(for example, 2026-10-01)."
            ),
            type="availability_request",
            requires_input=True,
            data={"missing": ["check_in", "check_out"]},
            context=updated_ctx,
        )

    check_in = ctx.checkIn
    check_out = ctx.checkOut
    adults = ctx.adults

    missing = []
    if not check_in:
        missing.append("check_in")
    if not check_out:
        missing.append("check_out")
    if adults is None:
        missing.append("adults")

    updated_ctx = ConversationContext(
        checkIn=check_in,
        checkOut=check_out,
        adults=adults,
        last_intent="availability",
    )

    if missing:
        labels = {
            "check_in": "check-in date",
            "check_out": "check-out date",
            "adults": "number of adults",
        }
        parts = [labels[f] for f in missing]
        if len(parts) == 1:
            ask = parts[0]
        elif len(parts) == 2:
            ask = f"{parts[0]} and {parts[1]}"
        else:
            ask = f"{parts[0]}, {parts[1]}, and {parts[2]}"

        return AssistantResponse(
            message=f"I can check room availability. Please provide your {ask}.",
            type="availability_request",
            requires_input=True,
            data={"missing": missing},
            context=updated_ctx,
        )

    # All info present — call the existing availability engine
    try:
        result = checkAvailability(check_in, check_out, adults)
    except ValueError as e:
        return AssistantResponse(
            message=str(e),
            type="availability_error",
            requires_input=False,
            data=None,
            context=updated_ctx,
        )

    final_ctx = ConversationContext(
        checkIn=check_in,
        checkOut=check_out,
        adults=adults,
        last_intent="availability",
    )

    if result.available:
        # Build a clear list of available room types with capacity info
        room_lines = []
        for room in result.rooms:
            room_lines.append(
                f"  • {room.room_type} (up to {room.max_adults} adults, "
                f"{room.available_rooms} room(s) available)"
            )
        rooms_text = "\n".join(room_lines)
        msg = (
            f"The following rooms are available for {adults} adult(s) "
            f"from {check_in} to {check_out}:\n\n"
            f"{rooms_text}"
        )
    else:
        msg = (
            f"Unfortunately, no rooms are available for {adults} adult(s) "
            f"from {check_in} to {check_out}. Please try different dates or contact the hotel."
        )

    return AssistantResponse(
        message=msg,
        type="availability_result",
        requires_input=False,
        data={
            "check_in": check_in,
            "check_out": check_out,
            "adults": adults,
            "available": result.available,
            "rooms": [r.model_dump() for r in result.rooms],
        },
        context=final_ctx,
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def process_assistant_request(request: AssistantRequest) -> AssistantResponse:
    """
    Merge incoming context with extracted message values, detect intent,
    and route to availability flow or knowledge/FAQ service.
    """
    message = request.message

    # Determine if this is an availability-related turn.
    last_was_availability = (
        request.context is not None
        and request.context.last_intent == "availability"
    )
    is_avail = _is_availability_intent(message)

    # If there's a pending availability context and the new message provides
    # dates, adult counts, or a natural date reference, continue the flow.
    has_iso_dates = bool(_extract_iso_dates(message))
    has_adults = _extract_adults(message) is not None
    has_natural = _has_natural_date(message)

    continuing_avail = (
        last_was_availability
        and not is_avail
        and (has_iso_dates or has_adults or has_natural)
    )

    if is_avail or continuing_avail:
        merged = _merge_context(request.context, message)
        merged.last_intent = "availability"
        return _handle_availability(message, merged)

    # FAQ / knowledge service
    intent = knowledge_service.detect_intent(message)

    if intent == "availability":
        merged = _merge_context(request.context, message)
        merged.last_intent = "availability"
        return _handle_availability(message, merged)

    faq_message, response_type = knowledge_service.get_answer(intent)

    # ---------------------------------------------------------------------------
    # LLM enhancement — conversational phrasing only.
    # The deterministic faq_message is authoritative; the LLM only rephrases it.
    # Availability data, policies, and facts are NEVER decided by the LLM.
    # If the LLM is unconfigured or fails, faq_message is used unchanged.
    # ---------------------------------------------------------------------------
    if response_type not in ("error",):
        hotel_data = knowledge_service.get_data()
        hotel_context = None
        if hotel_data and "hotel" in hotel_data:
            hotel_context = hotel_data["hotel"].get("name", "")
        faq_message = llm_service.enhance_response(faq_message, hotel_context)

    # Preserve any existing availability context so it survives a mid-flow FAQ question.
    # Only preserve last_intent=availability if the previous intent was availability;
    # otherwise set it to the current FAQ intent so the flow doesn't get confused.
    if last_was_availability:
        preserved_last_intent = "availability"
    else:
        preserved_last_intent = intent

    preserved_ctx = ConversationContext(
        checkIn=request.context.checkIn if request.context else None,
        checkOut=request.context.checkOut if request.context else None,
        adults=request.context.adults if request.context else None,
        last_intent=preserved_last_intent,
    )

    return AssistantResponse(
        message=faq_message,
        type=response_type,
        requires_input=False,
        data={"intent": intent},
        context=preserved_ctx,
    )
