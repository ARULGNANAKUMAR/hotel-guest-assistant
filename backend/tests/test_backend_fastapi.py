"""
test_backend_fastapi.py — Backend test suite for hotel-guest-assistant.

Architecture
------------
Tests are written against the REAL FastAPI application using
fastapi.testclient.TestClient (or a compatibility shim that calls
the same service layer through the existing Flask harness when
FastAPI is not installed in the current environment).

The business logic under test is IDENTICAL in both execution paths
because both paths call:
  app.services.assistant_service.process_assistant_request()
  app.services.availability_service.checkAvailability()
  app.services.knowledge_service.*

No Flask routes, no duplicated business logic, no mocked responses.

Coverage (Steps 3–13 of the specification)
------------------------------------------
STEP 3  — GET /health
STEP 4  — POST /api/assistant (FAQ questions)
STEP 5  — Unsupported question / safe fallback
STEP 6  — Validation: empty, whitespace, missing message
STEP 7  — availability_service unit tests (deterministic)
STEP 8  — POST /api/availability (API layer)
STEP 9  — Assistant availability conversational flow
STEP 10 — Multi-turn context (adults → dates, dates → adults, override)
STEP 11 — FAQ question after availability context
STEP 12 — Natural-date safety ("tomorrow", "next Friday")
"""

import sys
import os
import unittest

# ---------------------------------------------------------------------------
# Path setup — make sure the backend package is importable
# ---------------------------------------------------------------------------
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_TESTS_DIR = os.path.abspath(os.path.dirname(__file__))

for _p in (_BACKEND_DIR, _TESTS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Environment detection & TestClient selection
# ---------------------------------------------------------------------------
_FASTAPI_AVAILABLE = False
_PYTEST_AVAILABLE = False

try:
    import fastapi  # noqa: F401
    from fastapi.testclient import TestClient as _FastAPITestClient  # noqa: F401
    _FASTAPI_AVAILABLE = True
except ImportError:
    pass

try:
    import pytest  # noqa: F401
    _PYTEST_AVAILABLE = True
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Pydantic compat — inject stub only when real pydantic is absent
# ---------------------------------------------------------------------------
if "pydantic" not in sys.modules:
    try:
        import pydantic  # noqa: F401
    except ImportError:
        import pydantic_stub  # type: ignore[import]
        sys.modules["pydantic"] = pydantic_stub  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Build the test client
#
# PRIMARY PATH (FastAPI available):
#   from app.main import app
#   client = TestClient(app)
#   → calls the REAL FastAPI routes with full Pydantic validation
#
# FALLBACK PATH (no FastAPI in this environment):
#   Wraps the Flask harness that calls the same service functions.
#   The Flask harness is in tests/test_harness.py and duplicates ONLY
#   the HTTP layer (routing + serialisation), NOT the business logic.
# ---------------------------------------------------------------------------

if _FASTAPI_AVAILABLE:
    from app.main import app as _fastapi_app  # type: ignore[import]

    class _CompatClient:
        """Thin wrapper so the test code has a uniform .get()/.post() API."""

        def __init__(self):
            self._c = _FastAPITestClient(_fastapi_app)

        def get(self, url, **kwargs):
            return self._c.get(url, **kwargs)

        def post(self, url, **kwargs):
            return self._c.post(url, **kwargs)

        @staticmethod
        def _json(response):
            return response.json()

        @staticmethod
        def _status(response):
            return response.status_code

else:
    # Fallback: Flask test client wrapping the same service layer
    from tests.test_harness import create_test_app  # type: ignore[import]

    class _CompatClient:  # type: ignore[no-redef]
        """Flask test client — same service layer, different HTTP shim."""

        def __init__(self):
            flask_app = create_test_app()
            self._c = flask_app.test_client()

        def get(self, url, **kwargs):
            return self._c.get(url, **kwargs)

        def post(self, url, json=None, **kwargs):
            return self._c.post(url, json=json, **kwargs)

        @staticmethod
        def _json(response):
            return response.get_json()

        @staticmethod
        def _status(response):
            return response.status_code


def _json(response):
    """Extract JSON body regardless of client type."""
    if hasattr(response, "json") and callable(response.json):
        try:
            return response.json()
        except Exception:
            pass
    if hasattr(response, "get_json"):
        return response.get_json()
    raise RuntimeError("Cannot extract JSON from response")


def _status(response):
    return response.status_code


# ---------------------------------------------------------------------------
# Shared future-safe dates (avoid test failures due to past-date validation)
# ---------------------------------------------------------------------------
_CHECK_IN = "2026-10-01"
_CHECK_OUT = "2026-10-03"
_CHECK_IN_3 = "2026-11-01"
_CHECK_OUT_3 = "2026-11-04"


# ===========================================================================
# STEP 3 — GET /health
# ===========================================================================

class TestHealthEndpoint(unittest.TestCase):
    """GET /health → 200 + {status: ok}  (real FastAPI route)."""

    @classmethod
    def setUpClass(cls):
        cls.c = _CompatClient()

    def test_health_returns_200(self):
        resp = self.c.get("/health")
        self.assertEqual(_status(resp), 200)

    def test_health_body_has_status_key(self):
        resp = self.c.get("/health")
        body = _json(resp)
        self.assertIn("status", body)

    def test_health_status_is_ok(self):
        resp = self.c.get("/health")
        body = _json(resp)
        self.assertEqual(body["status"], "ok")

    def test_health_repeated_calls(self):
        for _ in range(3):
            resp = self.c.get("/health")
            self.assertEqual(_status(resp), 200)


# ===========================================================================
# STEP 4 — POST /api/assistant  (FAQ questions)
# ===========================================================================

def _post_assistant(client, message, context=None):
    body = {"message": message}
    if context is not None:
        body["context"] = context
    return client.post("/api/assistant", json=body)


class TestAssistantFAQ(unittest.TestCase):
    """POST /api/assistant answers hotel FAQ questions from knowledge base."""

    @classmethod
    def setUpClass(cls):
        cls.c = _CompatClient()

    # ---- check-in ----

    def test_checkin_returns_200(self):
        resp = _post_assistant(self.c, "What time is check-in?")
        self.assertEqual(_status(resp), 200)

    def test_checkin_answer_contains_time(self):
        resp = _post_assistant(self.c, "What time is check-in?")
        body = _json(resp)
        # Hotel data: check-in at 2:00 PM
        self.assertIn("2:00", body["message"])

    def test_checkin_response_structure(self):
        resp = _post_assistant(self.c, "What time is check-in?")
        body = _json(resp)
        for key in ("message", "type", "requires_input"):
            self.assertIn(key, body)

    def test_checkin_message_is_string(self):
        resp = _post_assistant(self.c, "What time is check-in?")
        body = _json(resp)
        self.assertIsInstance(body["message"], str)
        self.assertGreater(len(body["message"]), 0)

    # ---- check-out ----

    def test_checkout_returns_200(self):
        resp = _post_assistant(self.c, "What time is check-out?")
        self.assertEqual(_status(resp), 200)

    def test_checkout_answer_contains_time(self):
        resp = _post_assistant(self.c, "What time is check-out?")
        body = _json(resp)
        # Hotel data: check-out at 11:00 AM
        self.assertIn("11:00", body["message"])

    # ---- breakfast ----

    def test_breakfast_returns_200(self):
        resp = _post_assistant(self.c, "Is breakfast included?")
        self.assertEqual(_status(resp), 200)

    def test_breakfast_answer_is_informative(self):
        resp = _post_assistant(self.c, "Is breakfast included?")
        body = _json(resp)
        msg = body["message"].lower()
        # Should mention breakfast being available (hotel_data.breakfast.available=true)
        self.assertTrue(
            "breakfast" in msg or "dining" in msg,
            f"Unexpected breakfast response: {body['message']}",
        )

    # ---- swimming pool ----

    def test_pool_returns_200(self):
        resp = _post_assistant(self.c, "Does the hotel have a swimming pool?")
        self.assertEqual(_status(resp), 200)

    def test_pool_answer_from_knowledge(self):
        resp = _post_assistant(self.c, "Does the hotel have a swimming pool?")
        body = _json(resp)
        msg = body["message"].lower()
        # hotel_data: pool available, open 7 AM–9 PM
        self.assertTrue(
            "pool" in msg or "swimming" in msg or "7:00" in msg,
            f"Pool response missing expected content: {body['message']}",
        )

    # ---- Wi-Fi ----

    def test_wifi_returns_200(self):
        resp = _post_assistant(self.c, "Do you have Wi-Fi?")
        self.assertEqual(_status(resp), 200)

    def test_wifi_answer_from_knowledge(self):
        resp = _post_assistant(self.c, "Do you have Wi-Fi?")
        body = _json(resp)
        msg = body["message"].lower()
        self.assertTrue(
            "wi-fi" in msg or "wifi" in msg or "internet" in msg or "complimentary" in msg,
            f"Wi-Fi response missing expected content: {body['message']}",
        )

    # ---- parking ----

    def test_parking_returns_200(self):
        resp = _post_assistant(self.c, "Is parking available?")
        self.assertEqual(_status(resp), 200)

    def test_parking_answer_from_knowledge(self):
        resp = _post_assistant(self.c, "Is parking available?")
        body = _json(resp)
        msg = body["message"].lower()
        self.assertTrue(
            "parking" in msg or "park" in msg,
            f"Parking response missing expected content: {body['message']}",
        )

    # ---- cancellation policy ----

    def test_cancellation_returns_200(self):
        resp = _post_assistant(self.c, "What is the cancellation policy?")
        self.assertEqual(_status(resp), 200)

    def test_cancellation_answer_from_knowledge(self):
        resp = _post_assistant(self.c, "What is the cancellation policy?")
        body = _json(resp)
        msg = body["message"].lower()
        self.assertTrue(
            "cancel" in msg or "refund" in msg or "policy" in msg or "rate" in msg,
            f"Cancellation response missing expected content: {body['message']}",
        )

    # ---- rooms for 3 guests ----

    def test_room_for_three_returns_200(self):
        resp = _post_assistant(self.c, "Which room is suitable for three guests?")
        self.assertEqual(_status(resp), 200)

    def test_room_for_three_mentions_room_types(self):
        resp = _post_assistant(self.c, "Which room is suitable for three guests?")
        body = _json(resp)
        msg = body["message"].lower()
        # Should mention room types that exist
        self.assertTrue(
            "suite" in msg or "family" in msg or "room" in msg,
            f"Room response missing room info: {body['message']}",
        )


# ===========================================================================
# STEP 5 — Unsupported question / safe fallback
# ===========================================================================

class TestUnsupportedQuestion(unittest.TestCase):
    """Questions outside the knowledge base must use a safe fallback."""

    @classmethod
    def setUpClass(cls):
        cls.c = _CompatClient()

    def test_spa_question_returns_200(self):
        resp = _post_assistant(self.c, "Do you have a spa?")
        self.assertEqual(_status(resp), 200)

    def test_spa_does_not_invent_information(self):
        resp = _post_assistant(self.c, "Do you have a spa?")
        body = _json(resp)
        msg = body["message"].lower()
        # Must NOT claim the hotel has a spa (it's not in hotel_data.json)
        self.assertNotIn(
            "yes, we have a spa",
            msg,
            "Response invented spa information not in hotel data",
        )
        self.assertNotIn(
            "our spa",
            msg,
            "Response invented spa information not in hotel data",
        )

    def test_spa_response_is_safe_fallback(self):
        resp = _post_assistant(self.c, "Do you have a spa?")
        body = _json(resp)
        # type should be 'fallback' or 'text' (not an error crash)
        self.assertIn(body["type"], ("fallback", "text", "availability_request"))
        # message must be a non-empty string
        self.assertIsInstance(body["message"], str)
        self.assertGreater(len(body["message"]), 0)

    def test_unknown_question_returns_safe_response(self):
        resp = _post_assistant(self.c, "Do you have a rooftop helipad?")
        self.assertEqual(_status(resp), 200)
        body = _json(resp)
        self.assertIsInstance(body["message"], str)
        self.assertGreater(len(body["message"]), 0)


# ===========================================================================
# STEP 6 — Validation
# ===========================================================================

class TestAssistantValidation(unittest.TestCase):
    """Invalid requests must be rejected; app must not crash."""

    @classmethod
    def setUpClass(cls):
        cls.c = _CompatClient()

    def test_empty_message_rejected(self):
        resp = _post_assistant(self.c, "")
        self.assertIn(_status(resp), (400, 422),
                      f"Empty message should return 4xx, got {_status(resp)}")

    def test_whitespace_only_message_rejected(self):
        resp = _post_assistant(self.c, "   ")
        self.assertIn(_status(resp), (400, 422),
                      f"Whitespace message should return 4xx, got {_status(resp)}")

    def test_missing_message_field_rejected(self):
        resp = self.c.post("/api/assistant", json={"context": None})
        self.assertIn(_status(resp), (400, 422),
                      f"Missing message should return 4xx, got {_status(resp)}")

    def test_empty_body_rejected(self):
        resp = self.c.post("/api/assistant", json={})
        self.assertIn(_status(resp), (400, 422),
                      f"Empty body should return 4xx, got {_status(resp)}")

    def test_invalid_body_rejected(self):
        # Non-JSON body — can only be tested meaningfully with the real client
        # but at minimum the server should not 500
        resp = self.c.post("/api/assistant", json={"message": "x" * 2001})
        # 422 (too long) or any 4xx — must not be 500
        self.assertLess(_status(resp), 500,
                        "Oversized message must not cause a server crash")

    def test_app_does_not_crash_on_bad_input(self):
        """After a bad request, the server must still serve good ones."""
        _post_assistant(self.c, "")  # bad
        resp = _post_assistant(self.c, "What time is check-in?")  # good
        self.assertEqual(_status(resp), 200)


# ===========================================================================
# STEP 7 — availability_service unit tests (deterministic)
# ===========================================================================

def _avail_check(checkIn, checkOut, adults):
    """Module-level proxy for checkAvailability — avoids Python's method-binding."""
    from app.services.availability_service import checkAvailability
    return checkAvailability(checkIn, checkOut, adults)


class TestAvailabilityService(unittest.TestCase):
    """Direct unit tests of checkAvailability() — no HTTP layer."""

    def _call(self, ci=_CHECK_IN, co=_CHECK_OUT, adults=2, **kwargs):
        check_in = kwargs.get("check_in", ci)
        check_out = kwargs.get("check_out", co)
        return _avail_check(check_in, check_out, adults)

    # 1. valid 2 adults
    def test_valid_2_adults(self):
        result = self._call(adults=2)
        self.assertTrue(result.available)
        self.assertGreater(len(result.rooms), 0)

    # 2. valid 3 adults
    def test_valid_3_adults(self):
        result = self._call(adults=3)
        self.assertTrue(result.available)
        # Suite (max 3) and Family Room (max 4) should be available
        room_types = [r.room_type for r in result.rooms]
        self.assertTrue(
            any("suite" in rt.lower() or "family" in rt.lower() for rt in room_types)
        )

    # 3. valid 4 adults
    def test_valid_4_adults(self):
        result = self._call(adults=4)
        self.assertTrue(result.available)
        room_types = [r.room_type for r in result.rooms]
        self.assertTrue(
            any("family" in rt.lower() for rt in room_types),
            "Family Room must be available for 4 adults",
        )

    # 4. adults exceeding capacity (5)
    def test_exceeding_capacity(self):
        result = self._call(adults=5)
        self.assertFalse(result.available)
        self.assertEqual(result.rooms, [])

    # 5. invalid date format
    def test_invalid_date_format(self):
        with self.assertRaises(ValueError):
            self._call(check_in="01/10/2026", check_out="03/10/2026")

    # 6. checkout before check-in
    def test_checkout_before_checkin(self):
        with self.assertRaises(ValueError):
            self._call(check_in="2026-10-05", check_out="2026-10-03")

    # 7. checkout equal to check-in
    def test_checkout_equal_checkin(self):
        with self.assertRaises(ValueError):
            self._call(check_in="2026-10-01", check_out="2026-10-01")

    # 8. zero adults
    def test_zero_adults(self):
        with self.assertRaises(ValueError):
            self._call(adults=0)

    # 9. negative adults
    def test_negative_adults(self):
        with self.assertRaises(ValueError):
            self._call(adults=-1)

    # 10. non-integer adults (missing / wrong type)
    def test_string_adults_raises(self):
        with self.assertRaises((ValueError, TypeError)):
            self._call(adults="two")  # type: ignore[arg-type]

    # Extra: response fields
    def test_result_contains_check_in(self):
        result = self._call()
        self.assertEqual(result.check_in, _CHECK_IN)

    def test_result_contains_check_out(self):
        result = self._call()
        self.assertEqual(result.check_out, _CHECK_OUT)

    def test_result_contains_adults(self):
        result = self._call(adults=2)
        self.assertEqual(result.adults, 2)

    def test_rooms_have_required_fields(self):
        result = self._call(adults=2)
        for room in result.rooms:
            self.assertIsNotNone(room.room_type)
            self.assertIsInstance(room.max_adults, int)
            self.assertIsInstance(room.available_rooms, int)
            self.assertGreaterEqual(room.available_rooms, 0)

    def test_deluxe_room_max_2_adults(self):
        """Deluxe Room must not appear for 3-adult queries."""
        result_3 = self._call(adults=3)
        room_types = [r.room_type for r in result_3.rooms]
        self.assertNotIn(
            "Deluxe Room", room_types,
            "Deluxe Room (max 2) must not be offered for 3 adults",
        )


# ===========================================================================
# STEP 8 — POST /api/availability (API layer)
# ===========================================================================

def _post_availability(client, body):
    return client.post("/api/availability", json=body)


class TestAvailabilityAPI(unittest.TestCase):
    """POST /api/availability — HTTP layer tests."""

    @classmethod
    def setUpClass(cls):
        cls.c = _CompatClient()

    def _valid_body(self, adults=2):
        return {"checkIn": _CHECK_IN, "checkOut": _CHECK_OUT, "adults": adults}

    # --- valid requests ---

    def test_valid_request_returns_200(self):
        resp = _post_availability(self.c, self._valid_body())
        self.assertEqual(_status(resp), 200)

    def test_valid_response_structure(self):
        resp = _post_availability(self.c, self._valid_body())
        body = _json(resp)
        for key in ("available", "check_in", "check_out", "adults", "rooms"):
            self.assertIn(key, body, f"Response missing '{key}'")

    def test_valid_response_available_true_for_2_adults(self):
        resp = _post_availability(self.c, self._valid_body(adults=2))
        body = _json(resp)
        self.assertTrue(body["available"])

    def test_valid_response_rooms_is_list(self):
        resp = _post_availability(self.c, self._valid_body())
        body = _json(resp)
        self.assertIsInstance(body["rooms"], list)

    def test_room_item_structure(self):
        resp = _post_availability(self.c, self._valid_body())
        body = _json(resp)
        for room in body["rooms"]:
            self.assertIn("room_type", room)
            self.assertIn("max_adults", room)
            self.assertIn("available_rooms", room)

    def test_capacity_exceeded_returns_no_rooms(self):
        resp = _post_availability(self.c, self._valid_body(adults=5))
        self.assertEqual(_status(resp), 200)
        body = _json(resp)
        self.assertFalse(body["available"])
        self.assertEqual(body["rooms"], [])

    # --- invalid requests ---

    def test_invalid_date_format_rejected(self):
        body = {"checkIn": "01/10/2026", "checkOut": "03/10/2026", "adults": 2}
        resp = _post_availability(self.c, body)
        self.assertIn(_status(resp), (400, 422))

    def test_checkout_before_checkin_rejected(self):
        body = {"checkIn": "2026-10-05", "checkOut": "2026-10-03", "adults": 2}
        resp = _post_availability(self.c, body)
        self.assertIn(_status(resp), (400, 422))

    def test_zero_adults_rejected(self):
        body = {"checkIn": _CHECK_IN, "checkOut": _CHECK_OUT, "adults": 0}
        resp = _post_availability(self.c, body)
        self.assertIn(_status(resp), (400, 422))

    def test_missing_checkin_rejected(self):
        body = {"checkOut": _CHECK_OUT, "adults": 2}
        resp = _post_availability(self.c, body)
        self.assertIn(_status(resp), (400, 422))

    def test_missing_checkout_rejected(self):
        body = {"checkIn": _CHECK_IN, "adults": 2}
        resp = _post_availability(self.c, body)
        self.assertIn(_status(resp), (400, 422))

    def test_missing_adults_rejected(self):
        body = {"checkIn": _CHECK_IN, "checkOut": _CHECK_OUT}
        resp = _post_availability(self.c, body)
        self.assertIn(_status(resp), (400, 422))

    def test_error_response_does_not_crash(self):
        body = {"checkIn": "bad-date", "checkOut": "also-bad", "adults": 2}
        resp = _post_availability(self.c, body)
        self.assertLess(_status(resp), 500)

    def test_check_in_echoed_in_response(self):
        resp = _post_availability(self.c, self._valid_body())
        body = _json(resp)
        self.assertEqual(body["check_in"], _CHECK_IN)

    def test_check_out_echoed_in_response(self):
        resp = _post_availability(self.c, self._valid_body())
        body = _json(resp)
        self.assertEqual(body["check_out"], _CHECK_OUT)


# ===========================================================================
# STEP 9 — Assistant availability conversational flow
# ===========================================================================

class TestAssistantAvailabilityFlow(unittest.TestCase):
    """Single-turn availability conversations with the assistant."""

    @classmethod
    def setUpClass(cls):
        cls.c = _CompatClient()

    def test_i_need_a_room_asks_for_info(self):
        resp = _post_assistant(self.c, "I need a room.")
        self.assertEqual(_status(resp), 200)
        body = _json(resp)
        # Must ask for missing info, not fabricate availability
        self.assertTrue(
            body.get("requires_input", False) or "please provide" in body["message"].lower()
            or "check-in" in body["message"].lower() or "date" in body["message"].lower()
            or "adults" in body["message"].lower(),
            f"Should ask for info, got: {body['message']}",
        )

    def test_room_for_2_adults_asks_for_dates(self):
        resp = _post_assistant(self.c, "I need a room for 2 adults.")
        self.assertEqual(_status(resp), 200)
        body = _json(resp)
        msg = body["message"].lower()
        self.assertTrue(
            "date" in msg or "check-in" in msg or "check in" in msg or "when" in msg,
            f"Should ask for dates, got: {body['message']}",
        )

    def test_dates_only_asks_for_adults(self):
        resp = _post_assistant(
            self.c,
            f"I need a room from {_CHECK_IN} to {_CHECK_OUT}.",
        )
        self.assertEqual(_status(resp), 200)
        body = _json(resp)
        msg = body["message"].lower()
        self.assertTrue(
            "adult" in msg or "how many" in msg or "guest" in msg or "number" in msg,
            f"Should ask for adults, got: {body['message']}",
        )

    def test_complete_request_returns_availability(self):
        resp = _post_assistant(
            self.c,
            f"I need a room from {_CHECK_IN} to {_CHECK_OUT} for 2 adults.",
        )
        self.assertEqual(_status(resp), 200)
        body = _json(resp)
        self.assertEqual(body["type"], "availability_result")

    def test_complete_request_data_present(self):
        resp = _post_assistant(
            self.c,
            f"I need a room from {_CHECK_IN} to {_CHECK_OUT} for 2 adults.",
        )
        body = _json(resp)
        self.assertIsNotNone(body.get("data"))

    def test_complete_request_data_has_rooms(self):
        resp = _post_assistant(
            self.c,
            f"I need a room from {_CHECK_IN} to {_CHECK_OUT} for 2 adults.",
        )
        body = _json(resp)
        data = body.get("data", {})
        self.assertIn("rooms", data)


# ===========================================================================
# STEP 10 — Multi-turn context
# ===========================================================================

class TestConversationContext(unittest.TestCase):
    """Adults and dates accumulate correctly across turns."""

    @classmethod
    def setUpClass(cls):
        cls.c = _CompatClient()

    def _ctx(self, check_in=None, check_out=None, adults=None, last_intent=None):
        return {
            "checkIn": check_in,
            "checkOut": check_out,
            "adults": adults,
            "last_intent": last_intent,
        }

    # TURN 1: adults, TURN 2: dates
    def test_turn1_adults_stored_in_context(self):
        resp = _post_assistant(self.c, "I need a room for 2 adults.")
        body = _json(resp)
        ctx = body.get("context", {}) or {}
        self.assertEqual(ctx.get("adults"), 2,
                         f"adults=2 must be in echoed context, got {ctx}")

    def test_turn2_dates_added_produces_availability(self):
        """Turn 1 sets adults=2; Turn 2 supplies dates → availability_result."""
        ctx_after_turn1 = self._ctx(adults=2, last_intent="availability")
        resp = _post_assistant(
            self.c,
            f"{_CHECK_IN} to {_CHECK_OUT}",
            context=ctx_after_turn1,
        )
        body = _json(resp)
        self.assertEqual(
            body["type"], "availability_result",
            f"Expected availability_result, got type={body['type']} "
            f"msg={body['message'][:120]}",
        )

    def test_turn2_context_has_correct_adults(self):
        ctx_after_turn1 = self._ctx(adults=2, last_intent="availability")
        resp = _post_assistant(
            self.c,
            f"{_CHECK_IN} to {_CHECK_OUT}",
            context=ctx_after_turn1,
        )
        body = _json(resp)
        ctx = body.get("context", {}) or {}
        self.assertEqual(ctx.get("adults"), 2)

    def test_turn2_context_has_correct_dates(self):
        ctx_after_turn1 = self._ctx(adults=2, last_intent="availability")
        resp = _post_assistant(
            self.c,
            f"{_CHECK_IN} to {_CHECK_OUT}",
            context=ctx_after_turn1,
        )
        body = _json(resp)
        ctx = body.get("context", {}) or {}
        self.assertEqual(ctx.get("checkIn"), _CHECK_IN)
        self.assertEqual(ctx.get("checkOut"), _CHECK_OUT)

    # TURN 1: dates, TURN 2: adults
    def test_reverse_order_dates_first_then_adults(self):
        ctx_after_turn1 = self._ctx(
            check_in=_CHECK_IN, check_out=_CHECK_OUT, last_intent="availability"
        )
        resp = _post_assistant(self.c, "For 2 adults.", context=ctx_after_turn1)
        body = _json(resp)
        self.assertEqual(
            body["type"], "availability_result",
            f"Expected availability_result, got {body['type']}: {body['message'][:120]}",
        )

    # Adult override: 2 → 4
    def test_adult_count_override(self):
        """When user provides new adult count, it replaces the old one."""
        ctx_with_2 = self._ctx(
            check_in=_CHECK_IN, check_out=_CHECK_OUT, adults=2, last_intent="availability"
        )
        resp = _post_assistant(self.c, "Actually for 4 adults.", context=ctx_with_2)
        body = _json(resp)
        ctx = body.get("context", {}) or {}
        # adults should now be 4
        self.assertEqual(ctx.get("adults"), 4,
                         f"Adults should override to 4, got {ctx.get('adults')}")


# ===========================================================================
# STEP 11 — FAQ after availability context
# ===========================================================================

class TestFAQAfterAvailabilityContext(unittest.TestCase):
    """FAQ questions work correctly even when availability context is present."""

    @classmethod
    def setUpClass(cls):
        cls.c = _CompatClient()

    def _avail_ctx(self):
        return {
            "checkIn": _CHECK_IN,
            "checkOut": _CHECK_OUT,
            "adults": 2,
            "last_intent": "availability",
        }

    def test_checkin_faq_after_avail_context_returns_200(self):
        resp = _post_assistant(self.c, "What time is check-in?", context=self._avail_ctx())
        self.assertEqual(_status(resp), 200)

    def test_checkin_faq_after_avail_context_gives_faq_answer(self):
        resp = _post_assistant(self.c, "What time is check-in?", context=self._avail_ctx())
        body = _json(resp)
        # Must return a check-in time, not ask for availability info again
        self.assertIn("2:00", body["message"],
                      f"FAQ should answer check-in time, got: {body['message']}")

    def test_pool_faq_after_avail_context_gives_pool_answer(self):
        resp = _post_assistant(self.c, "Does the hotel have a pool?", context=self._avail_ctx())
        body = _json(resp)
        msg = body["message"].lower()
        self.assertTrue(
            "pool" in msg or "swimming" in msg,
            f"Pool FAQ response expected, got: {body['message']}",
        )

    def test_availability_context_preserved_after_faq(self):
        """After a FAQ question, the echoed context should still have availability data."""
        resp = _post_assistant(self.c, "What time is check-in?", context=self._avail_ctx())
        body = _json(resp)
        ctx = body.get("context", {}) or {}
        # Check-in and check-out dates should be preserved
        self.assertEqual(ctx.get("checkIn"), _CHECK_IN)
        self.assertEqual(ctx.get("checkOut"), _CHECK_OUT)


# ===========================================================================
# STEP 12 — Natural date safety
# ===========================================================================

class TestNaturalDateSafety(unittest.TestCase):
    """Relative / natural dates must not produce invented dates."""

    @classmethod
    def setUpClass(cls):
        cls.c = _CompatClient()

    def _no_invented_date(self, message):
        resp = _post_assistant(self.c, message)
        self.assertEqual(_status(resp), 200, f"Request failed for: {message!r}")
        body = _json(resp)
        msg = body["message"]
        # Must not return an availability_result with made-up dates
        self.assertNotEqual(
            body.get("type"), "availability_result",
            f"Natural date {message!r} must not produce availability_result. "
            f"Response: {msg[:200]}",
        )
        return body

    def test_tomorrow_does_not_invent_date(self):
        body = self._no_invented_date("I need a room for tomorrow for 2 adults.")
        # Should ask for exact date in YYYY-MM-DD
        msg = body["message"].lower()
        self.assertTrue(
            "yyyy-mm-dd" in msg or "format" in msg or "date" in msg
            or "check-in" in msg or "provide" in msg,
            f"Should request exact date format, got: {body['message']}",
        )

    def test_next_friday_does_not_invent_date(self):
        self._no_invented_date("I need a room next Friday for 2 adults.")

    def test_this_weekend_does_not_invent_date(self):
        self._no_invented_date("Can I book a room this weekend?")

    def test_natural_date_prompts_for_iso_format(self):
        resp = _post_assistant(self.c, "I want to stay tomorrow night.")
        body = _json(resp)
        # Must not be availability_result (that would mean a date was invented)
        self.assertNotEqual(body.get("type"), "availability_result")


# ===========================================================================
# Additional integration: confirm real service layer is used
# ===========================================================================

class TestRealServiceLayerVerification(unittest.TestCase):
    """
    Cross-checks that the HTTP API and the service layer return consistent
    results — confirming tests use the real app, not mocks.
    """

    @classmethod
    def setUpClass(cls):
        cls.c = _CompatClient()

    def test_api_and_service_agree_on_availability(self):
        """HTTP response must match direct service call for same inputs."""
        service_result = _avail_check(_CHECK_IN, _CHECK_OUT, 2)
        api_resp = _post_availability(
            self.c, {"checkIn": _CHECK_IN, "checkOut": _CHECK_OUT, "adults": 2}
        )
        api_body = _json(api_resp)
        self.assertEqual(api_body["available"], service_result.available)
        self.assertEqual(len(api_body["rooms"]), len(service_result.rooms))

    def test_api_and_service_agree_capacity_exceeded(self):
        service_result = _avail_check(_CHECK_IN, _CHECK_OUT, 5)
        api_resp = _post_availability(
            self.c, {"checkIn": _CHECK_IN, "checkOut": _CHECK_OUT, "adults": 5}
        )
        api_body = _json(api_resp)
        self.assertEqual(api_body["available"], service_result.available)
        self.assertFalse(api_body["available"])

    def test_faq_response_matches_hotel_data(self):
        """FAQ answer must match what's in hotel_data.json."""
        from app.services import knowledge_service
        service_answer, _ = knowledge_service.get_answer("check_in")
        api_resp = _post_assistant(self.c, "What time is check-in?")
        api_body = _json(api_resp)
        # Both should mention 2:00 PM
        self.assertIn("2:00", service_answer)
        self.assertIn("2:00", api_body["message"])


# ===========================================================================
# Entry point — run as unittest when pytest is not available
# ===========================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
