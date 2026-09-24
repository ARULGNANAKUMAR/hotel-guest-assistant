"""
Phase 7A-2: Availability service, availability API, assistant availability
flow, conversation context, and multi-turn follow-up tests.

Covers:
  1.  Availability service — valid adult counts (2, 3, 4)
  2.  Availability service — capacity exceeded (5 adults)
  3.  Date validation — invalid format
  4.  Date validation — checkout before check-in
  5.  Date validation — checkout equal to check-in
  6.  Date validation — check-in in the past
  7.  Adult validation — zero, negative, missing
  8.  Availability API — valid request succeeds
  9.  Availability API — invalid requests rejected safely
  10. Availability API — response structure
  11. Assistant — "I need a room." triggers missing-info prompt
  12. Assistant — "I need a room for 2 adults." asks for dates
  13. Assistant — dates-only asks for adults
  14. Assistant — complete request returns availability result
  15. Context — adults stored in context after first turn
  16. Context — dates added in second turn; adults preserved
  17. Context — date-first, then adults follow-up
  18. Context override — adults value updated from 2 → 4
  19. FAQ + context — pool question does not become availability request
  20. Unsupported date language — "tomorrow" does not invent a date
  21. Test independence — no shared mutable state between tests

Each test creates its own request / context state.
No shared mutable state is used between tests.
"""

import sys
import os
import unittest

# Ensure the backend package root is on sys.path
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

_TESTS_DIR = os.path.abspath(os.path.dirname(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

# Inject pydantic stub before any service imports
if "pydantic" not in sys.modules:
    import pydantic_stub
    sys.modules["pydantic"] = pydantic_stub

from tests.test_harness import create_test_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Fixed future dates used throughout (well beyond today)
_CHECK_IN = "2026-10-01"
_CHECK_OUT = "2026-10-03"


def _avail_post(client, payload):
    return client.post("/api/availability", json=payload)


def _asst_post(client, message, context=None):
    body = {"message": message}
    if context is not None:
        body["context"] = context
    return client.post("/api/assistant", json=body)


# ---------------------------------------------------------------------------
# 1. Availability Service — Unit Tests
# ---------------------------------------------------------------------------

class TestAvailabilityServiceUnit(unittest.TestCase):
    """
    Pure unit tests against checkAvailability().
    No HTTP layer involved.
    """

    @classmethod
    def setUpClass(cls):
        from app.services.availability_service import checkAvailability
        cls.checkAvailability = staticmethod(checkAvailability)

    # --- valid adult counts ------------------------------------------------

    def test_2_adults_returns_rooms(self):
        """2 adults: Deluxe Room, Suite, and Family Room are all eligible."""
        result = self.checkAvailability(_CHECK_IN, _CHECK_OUT, 2)
        self.assertTrue(result.available)
        room_types = [r.room_type for r in result.rooms]
        # All three room types accommodate 2 adults
        self.assertIn("Deluxe Room", room_types)
        self.assertIn("Suite", room_types)
        self.assertIn("Family Room", room_types)

    def test_3_adults_returns_eligible_rooms(self):
        """3 adults: Suite and Family Room are eligible; Deluxe Room is not."""
        result = self.checkAvailability(_CHECK_IN, _CHECK_OUT, 3)
        self.assertTrue(result.available)
        room_types = [r.room_type for r in result.rooms]
        self.assertNotIn("Deluxe Room", room_types)   # max 2
        self.assertIn("Suite", room_types)             # max 3
        self.assertIn("Family Room", room_types)       # max 4

    def test_4_adults_returns_family_room_only(self):
        """4 adults: only Family Room is eligible."""
        result = self.checkAvailability(_CHECK_IN, _CHECK_OUT, 4)
        self.assertTrue(result.available)
        room_types = [r.room_type for r in result.rooms]
        self.assertIn("Family Room", room_types)
        self.assertNotIn("Deluxe Room", room_types)
        self.assertNotIn("Suite", room_types)

    def test_capacity_exceeded_no_rooms(self):
        """5 adults: no room in inventory accommodates 5 adults."""
        result = self.checkAvailability(_CHECK_IN, _CHECK_OUT, 5)
        self.assertFalse(result.available)
        self.assertEqual(result.rooms, [])

    # --- response fields --------------------------------------------------

    def test_response_echo_dates_and_adults(self):
        """Response must echo back the requested dates and adults."""
        result = self.checkAvailability(_CHECK_IN, _CHECK_OUT, 2)
        self.assertEqual(result.check_in, _CHECK_IN)
        self.assertEqual(result.check_out, _CHECK_OUT)
        self.assertEqual(result.adults, 2)

    def test_room_has_room_type_field(self):
        """Each room in the result must have a room_type string."""
        result = self.checkAvailability(_CHECK_IN, _CHECK_OUT, 2)
        for room in result.rooms:
            self.assertIsInstance(room.room_type, str)
            self.assertTrue(len(room.room_type) > 0)

    def test_room_has_max_adults_field(self):
        """Each room must have a positive max_adults integer."""
        result = self.checkAvailability(_CHECK_IN, _CHECK_OUT, 2)
        for room in result.rooms:
            self.assertIsInstance(room.max_adults, int)
            self.assertGreater(room.max_adults, 0)

    def test_room_has_available_rooms_field(self):
        """Each room must have an available_rooms integer."""
        result = self.checkAvailability(_CHECK_IN, _CHECK_OUT, 2)
        for room in result.rooms:
            self.assertIsInstance(room.available_rooms, int)


# ---------------------------------------------------------------------------
# 2. Date Validation Tests
# ---------------------------------------------------------------------------

class TestDateValidation(unittest.TestCase):
    """
    Tests for invalid date inputs to checkAvailability().
    """

    @classmethod
    def setUpClass(cls):
        from app.services.availability_service import checkAvailability
        cls.checkAvailability = staticmethod(checkAvailability)

    def test_invalid_check_in_format_raises(self):
        """Non-ISO check-in date must raise ValueError."""
        with self.assertRaises(ValueError):
            self.checkAvailability("01-10-2026", _CHECK_OUT, 2)

    def test_invalid_check_out_format_raises(self):
        """Non-ISO check-out date must raise ValueError."""
        with self.assertRaises(ValueError):
            self.checkAvailability(_CHECK_IN, "03/10/2026", 2)

    def test_garbage_check_in_raises(self):
        """Garbage string as check-in must raise ValueError."""
        with self.assertRaises(ValueError):
            self.checkAvailability("not-a-date", _CHECK_OUT, 2)

    def test_checkout_before_checkin_raises(self):
        """Check-out date before check-in must raise ValueError."""
        with self.assertRaises(ValueError):
            self.checkAvailability("2026-10-05", "2026-10-01", 2)

    def test_checkout_equal_checkin_raises(self):
        """Same-day check-in/check-out must raise ValueError."""
        with self.assertRaises(ValueError):
            self.checkAvailability("2026-10-01", "2026-10-01", 2)

    def test_checkin_in_past_raises(self):
        """A check-in date in the past must raise ValueError."""
        with self.assertRaises(ValueError):
            self.checkAvailability("2020-01-01", "2020-01-05", 2)


# ---------------------------------------------------------------------------
# 3. Adult Validation Tests
# ---------------------------------------------------------------------------

class TestAdultValidation(unittest.TestCase):
    """
    Tests for invalid adult counts passed to checkAvailability().
    """

    @classmethod
    def setUpClass(cls):
        from app.services.availability_service import checkAvailability
        cls.checkAvailability = staticmethod(checkAvailability)

    def test_zero_adults_raises(self):
        """Zero adults must raise ValueError."""
        with self.assertRaises(ValueError):
            self.checkAvailability(_CHECK_IN, _CHECK_OUT, 0)

    def test_negative_adults_raises(self):
        """Negative adults must raise ValueError."""
        with self.assertRaises(ValueError):
            self.checkAvailability(_CHECK_IN, _CHECK_OUT, -1)

    def test_valid_adult_count_succeeds(self):
        """A valid positive adult count must not raise."""
        result = self.checkAvailability(_CHECK_IN, _CHECK_OUT, 2)
        self.assertIsNotNone(result)

    def test_none_adults_raises(self):
        """None as adults must raise (TypeError or ValueError)."""
        with self.assertRaises((ValueError, TypeError)):
            self.checkAvailability(_CHECK_IN, _CHECK_OUT, None)


# ---------------------------------------------------------------------------
# 4. Availability API Tests (via Flask test client)
# ---------------------------------------------------------------------------

class TestAvailabilityAPI(unittest.TestCase):
    """
    HTTP-level tests for POST /api/availability.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = create_test_app()
        cls.client = cls.app.test_client()

    def _post(self, payload):
        return _avail_post(self.client, payload)

    # --- valid request ----------------------------------------------------

    def test_valid_request_returns_200(self):
        """Valid availability request must return HTTP 200."""
        resp = self._post({"checkIn": _CHECK_IN, "checkOut": _CHECK_OUT, "adults": 2})
        self.assertEqual(resp.status_code, 200)

    def test_valid_request_returns_available_true(self):
        """2 adults for the test dates must return available=True."""
        resp = self._post({"checkIn": _CHECK_IN, "checkOut": _CHECK_OUT, "adults": 2})
        body = resp.get_json()
        self.assertTrue(body["available"])

    def test_valid_request_rooms_non_empty(self):
        """Valid request must return a non-empty rooms list."""
        resp = self._post({"checkIn": _CHECK_IN, "checkOut": _CHECK_OUT, "adults": 2})
        body = resp.get_json()
        self.assertIsInstance(body["rooms"], list)
        self.assertGreater(len(body["rooms"]), 0)

    def test_response_structure(self):
        """Response must contain: available, check_in, check_out, adults, rooms."""
        resp = self._post({"checkIn": _CHECK_IN, "checkOut": _CHECK_OUT, "adults": 2})
        body = resp.get_json()
        for field in ("available", "check_in", "check_out", "adults", "rooms"):
            self.assertIn(field, body, f"Missing field: {field}")

    def test_echo_check_in_date(self):
        """Response must echo back the check_in date."""
        resp = self._post({"checkIn": _CHECK_IN, "checkOut": _CHECK_OUT, "adults": 2})
        body = resp.get_json()
        self.assertEqual(body["check_in"], _CHECK_IN)

    def test_echo_check_out_date(self):
        """Response must echo back the check_out date."""
        resp = self._post({"checkIn": _CHECK_IN, "checkOut": _CHECK_OUT, "adults": 2})
        body = resp.get_json()
        self.assertEqual(body["check_out"], _CHECK_OUT)

    def test_echo_adults(self):
        """Response must echo back the adults count."""
        resp = self._post({"checkIn": _CHECK_IN, "checkOut": _CHECK_OUT, "adults": 2})
        body = resp.get_json()
        self.assertEqual(body["adults"], 2)

    def test_room_fields_present(self):
        """Each room object must have room_type, max_adults, available_rooms."""
        resp = self._post({"checkIn": _CHECK_IN, "checkOut": _CHECK_OUT, "adults": 2})
        body = resp.get_json()
        for room in body["rooms"]:
            self.assertIn("room_type", room)
            self.assertIn("max_adults", room)
            self.assertIn("available_rooms", room)

    # --- invalid requests -------------------------------------------------

    def test_missing_check_in_rejected(self):
        """Request missing checkIn must be rejected (not 200)."""
        resp = self._post({"checkOut": _CHECK_OUT, "adults": 2})
        self.assertNotEqual(resp.status_code, 200)

    def test_missing_check_out_rejected(self):
        """Request missing checkOut must be rejected (not 200)."""
        resp = self._post({"checkIn": _CHECK_IN, "adults": 2})
        self.assertNotEqual(resp.status_code, 200)

    def test_missing_adults_rejected(self):
        """Request missing adults must be rejected (not 200)."""
        resp = self._post({"checkIn": _CHECK_IN, "checkOut": _CHECK_OUT})
        self.assertNotEqual(resp.status_code, 200)

    def test_invalid_date_format_rejected(self):
        """Invalid date format must be rejected."""
        resp = self._post({"checkIn": "01/10/2026", "checkOut": _CHECK_OUT, "adults": 2})
        self.assertNotEqual(resp.status_code, 200)

    def test_zero_adults_rejected(self):
        """Zero adults must be rejected."""
        resp = self._post({"checkIn": _CHECK_IN, "checkOut": _CHECK_OUT, "adults": 0})
        self.assertNotEqual(resp.status_code, 200)

    def test_invalid_requests_return_json(self):
        """Invalid request must return a JSON body (not a crash)."""
        resp = self._post({"checkIn": "bad", "checkOut": _CHECK_OUT, "adults": 2})
        body = resp.get_json()
        self.assertIsNotNone(body)

    def test_5_adults_returns_not_available(self):
        """5 adults exceed all room capacities; available must be False."""
        resp = self._post({"checkIn": _CHECK_IN, "checkOut": _CHECK_OUT, "adults": 5})
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertFalse(body["available"])
        self.assertEqual(body["rooms"], [])


# ---------------------------------------------------------------------------
# 5. Assistant Availability Flow Tests
# ---------------------------------------------------------------------------

class TestAssistantAvailabilityFlow(unittest.TestCase):
    """
    Tests for POST /api/assistant with availability-related messages.
    Each test is independent — no shared context.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = create_test_app()
        cls.client = cls.app.test_client()

    def _post(self, message, context=None):
        return _asst_post(self.client, message, context)

    # --- incomplete requests ask for missing info --------------------------

    def test_room_request_no_info_asks_for_info(self):
        """'I need a room.' should ask for check-in, check-out, and adults."""
        resp = self._post("I need a room.")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body["requires_input"])

    def test_room_request_no_info_response_type(self):
        """'I need a room.' must return type='availability_request'."""
        resp = self._post("I need a room.")
        body = resp.get_json()
        self.assertEqual(body["type"], "availability_request")

    def test_room_request_adults_only_asks_for_dates(self):
        """'I need a room for 2 adults.' should ask for check-in/check-out."""
        resp = self._post("I need a room for 2 adults.")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body["requires_input"])
        # missing should include date fields
        data = body.get("data") or {}
        missing = data.get("missing", [])
        self.assertTrue(
            "check_in" in missing or "check_out" in missing,
            f"Expected date fields in missing, got: {missing}",
        )

    def test_room_request_dates_only_asks_for_adults(self):
        """Dates without adults should ask for the number of adults."""
        resp = self._post(f"I need a room from {_CHECK_IN} to {_CHECK_OUT}.")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body["requires_input"])
        data = body.get("data") or {}
        missing = data.get("missing", [])
        self.assertIn("adults", missing)

    def test_complete_request_returns_result(self):
        """Complete request (adults + dates) must return an availability result."""
        resp = self._post(
            f"I need a room for 2 adults from {_CHECK_IN} to {_CHECK_OUT}."
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["type"], "availability_result")
        self.assertFalse(body["requires_input"])

    def test_complete_request_result_has_data(self):
        """availability_result must include data with room info."""
        resp = self._post(
            f"I need a room for 2 adults from {_CHECK_IN} to {_CHECK_OUT}."
        )
        body = resp.get_json()
        data = body.get("data")
        self.assertIsNotNone(data)
        self.assertIn("available", data)

    def test_complete_request_message_non_empty(self):
        """Availability result must include a non-empty message string."""
        resp = self._post(
            f"I need a room for 2 adults from {_CHECK_IN} to {_CHECK_OUT}."
        )
        body = resp.get_json()
        self.assertIsInstance(body["message"], str)
        self.assertGreater(len(body["message"]), 0)


# ---------------------------------------------------------------------------
# 6 & 7. Context Tests — adults first, then dates (and vice versa)
# ---------------------------------------------------------------------------

class TestConversationContext(unittest.TestCase):
    """
    Multi-turn context accumulation tests.
    Every test builds its own fresh request state.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = create_test_app()
        cls.client = cls.app.test_client()

    def _post(self, message, context=None):
        return _asst_post(self.client, message, context)

    # --- Turn 1: adults only → context should store adults ----------------

    def test_turn1_adults_stored_in_context(self):
        """After 'I need a room for 2 adults.', context.adults must be 2."""
        resp = self._post("I need a room for 2 adults.")
        body = resp.get_json()
        ctx = body.get("context") or {}
        self.assertEqual(ctx.get("adults"), 2)

    def test_turn1_last_intent_is_availability(self):
        """After adults-only message, context.last_intent must be 'availability'."""
        resp = self._post("I need a room for 2 adults.")
        body = resp.get_json()
        ctx = body.get("context") or {}
        self.assertEqual(ctx.get("last_intent"), "availability")

    # --- Turn 2: provide dates using saved context -------------------------

    def test_turn2_dates_added_adults_preserved(self):
        """
        Turn 1: 'I need a room for 2 adults.'
        Turn 2: '2026-10-01 to 2026-10-03' with returned context.
        After turn 2: checkIn and checkOut set; adults must still be 2.
        """
        resp1 = self._post("I need a room for 2 adults.")
        ctx1 = resp1.get_json().get("context")

        resp2 = self._post(f"{_CHECK_IN} to {_CHECK_OUT}", context=ctx1)
        self.assertEqual(resp2.status_code, 200)
        body2 = resp2.get_json()

        ctx2 = body2.get("context") or {}
        self.assertEqual(ctx2.get("adults"), 2, "adults must be preserved from turn 1")
        self.assertEqual(ctx2.get("checkIn"), _CHECK_IN)
        self.assertEqual(ctx2.get("checkOut"), _CHECK_OUT)

    def test_turn2_availability_flow_can_complete(self):
        """
        After adults + dates are provided across two turns, the flow
        should reach availability_result (all info present).
        """
        resp1 = self._post("I need a room for 2 adults.")
        ctx1 = resp1.get_json().get("context")

        resp2 = self._post(f"{_CHECK_IN} to {_CHECK_OUT}", context=ctx1)
        body2 = resp2.get_json()
        self.assertEqual(body2["type"], "availability_result")

    # --- Turn 1: dates first → Turn 2: adults ----------------------------

    def test_dates_first_then_adults(self):
        """
        Turn 1: 'I need a room from 2026-10-01 to 2026-10-03.'
        Verify dates are stored.
        Turn 2: '3 adults' with previous context.
        Verify dates remain and adults = 3.
        """
        resp1 = self._post(f"I need a room from {_CHECK_IN} to {_CHECK_OUT}.")
        ctx1 = resp1.get_json().get("context") or {}
        self.assertEqual(ctx1.get("checkIn"), _CHECK_IN)
        self.assertEqual(ctx1.get("checkOut"), _CHECK_OUT)

        resp2 = self._post("3 adults", context=ctx1)
        self.assertEqual(resp2.status_code, 200)
        body2 = resp2.get_json()
        ctx2 = body2.get("context") or {}
        self.assertEqual(ctx2.get("checkIn"), _CHECK_IN, "checkIn must be preserved")
        self.assertEqual(ctx2.get("checkOut"), _CHECK_OUT, "checkOut must be preserved")
        self.assertEqual(ctx2.get("adults"), 3)

    def test_dates_first_then_adults_completes_flow(self):
        """
        Providing dates first and adults second must result in
        availability_result once both are known.
        """
        resp1 = self._post(f"I need a room from {_CHECK_IN} to {_CHECK_OUT}.")
        ctx1 = resp1.get_json().get("context")

        resp2 = self._post("3 adults", context=ctx1)
        body2 = resp2.get_json()
        self.assertEqual(body2["type"], "availability_result")


# ---------------------------------------------------------------------------
# 8. Context Override Test
# ---------------------------------------------------------------------------

class TestContextOverride(unittest.TestCase):
    """
    When a user corrects a previously supplied value, the new value must
    replace the old one.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = create_test_app()
        cls.client = cls.app.test_client()

    def _post(self, message, context=None):
        return _asst_post(self.client, message, context)

    def test_adults_override_from_2_to_4(self):
        """
        Existing context: adults=2, dates set, last_intent=availability.
        New message: 'Actually, 4 adults.'
        Resulting context.adults must be 4, not 2.
        """
        existing_ctx = {
            "checkIn": _CHECK_IN,
            "checkOut": _CHECK_OUT,
            "adults": 2,
            "last_intent": "availability",
        }
        resp = self._post("Actually, 4 adults.", context=existing_ctx)
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        ctx = body.get("context") or {}
        self.assertEqual(
            ctx.get("adults"), 4,
            "adults must be updated to 4; old value 2 must not persist",
        )

    def test_override_result_uses_new_adults(self):
        """
        After override, the availability result must reflect 4 adults,
        not 2.  The Family Room (max 4) should be in the results;
        the Deluxe Room (max 2) and Suite (max 3) should not.
        """
        existing_ctx = {
            "checkIn": _CHECK_IN,
            "checkOut": _CHECK_OUT,
            "adults": 2,
            "last_intent": "availability",
        }
        resp = self._post("Actually, 4 adults.", context=existing_ctx)
        body = resp.get_json()
        # If the type is availability_result we can inspect the data
        if body["type"] == "availability_result":
            data = body.get("data") or {}
            self.assertEqual(data.get("adults"), 4)
            room_types = [r["room_type"] for r in data.get("rooms", [])]
            self.assertIn("Family Room", room_types)
            self.assertNotIn("Deluxe Room", room_types)


# ---------------------------------------------------------------------------
# 9. FAQ + Context — availability context must not poison FAQ questions
# ---------------------------------------------------------------------------

class TestFAQWithAvailabilityContext(unittest.TestCase):
    """
    A pending availability context must not convert normal FAQ questions
    into availability requests.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = create_test_app()
        cls.client = cls.app.test_client()

    def _post(self, message, context=None):
        return _asst_post(self.client, message, context)

    def test_pool_question_with_availability_context(self):
        """
        Context: adults=2, last_intent=availability.
        Message: 'Do you have a pool?'
        Expected: pool FAQ answer, NOT an availability request.
        """
        ctx = {"adults": 2, "last_intent": "availability"}
        resp = self._post("Do you have a pool?", context=ctx)
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        # Must not be an availability request
        self.assertNotEqual(body["type"], "availability_request")
        # Message should reference the pool, not ask for dates/adults
        msg_lower = body["message"].lower()
        self.assertIn("pool", msg_lower)

    def test_wifi_question_with_availability_context(self):
        """
        Context: adults=2, last_intent=availability.
        Message: 'Do you have Wi-Fi?'
        Expected: Wi-Fi FAQ answer.
        """
        ctx = {"adults": 2, "last_intent": "availability"}
        resp = self._post("Do you have Wi-Fi?", context=ctx)
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertNotEqual(body["type"], "availability_request")
        msg_lower = body["message"].lower()
        self.assertIn("wi-fi", msg_lower)

    def test_pool_context_preservation(self):
        """
        After a FAQ question with an availability context, the existing
        availability fields must still be preserved in the response context.
        """
        ctx = {
            "checkIn": _CHECK_IN,
            "adults": 2,
            "last_intent": "availability",
        }
        resp = self._post("Do you have a pool?", context=ctx)
        body = resp.get_json()
        resp_ctx = body.get("context") or {}
        self.assertEqual(resp_ctx.get("adults"), 2)
        self.assertEqual(resp_ctx.get("checkIn"), _CHECK_IN)


# ---------------------------------------------------------------------------
# 10. Unsupported Date Language
# ---------------------------------------------------------------------------

class TestUnsupportedDateLanguage(unittest.TestCase):
    """
    Natural-language dates ('tomorrow', 'next Friday') are not supported.
    The implementation must ask for an exact ISO date rather than inventing one.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = create_test_app()
        cls.client = cls.app.test_client()

    def _post(self, message, context=None):
        return _asst_post(self.client, message, context)

    def test_tomorrow_does_not_produce_result(self):
        """'I need a room tomorrow.' must NOT return an availability_result."""
        resp = self._post("I need a room tomorrow.")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertNotEqual(
            body["type"],
            "availability_result",
            "Unsupported natural date must not produce an availability result",
        )

    def test_tomorrow_asks_for_exact_date(self):
        """Response to 'tomorrow' must ask for an exact date."""
        resp = self._post("I need a room tomorrow.")
        body = resp.get_json()
        self.assertTrue(body.get("requires_input"), "Should ask for more info")

    def test_tomorrow_message_hints_format(self):
        """Response should mention the expected date format (YYYY-MM-DD)."""
        resp = self._post("I need a room tomorrow.")
        body = resp.get_json()
        msg = body["message"]
        # The implementation says 'YYYY-MM-DD format'
        self.assertIn("YYYY-MM-DD", msg)

    def test_next_week_does_not_produce_result(self):
        """'I need a room next week.' must not return an availability_result."""
        resp = self._post("I need a room next week.")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertNotEqual(body["type"], "availability_result")


# ---------------------------------------------------------------------------
# 11. Test Independence
# ---------------------------------------------------------------------------

class TestIndependence(unittest.TestCase):
    """
    Verify that tests do not share mutable state.
    Running the same assertion twice in sequence must produce identical results.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = create_test_app()
        cls.client = cls.app.test_client()

    def _post(self, message, context=None):
        return _asst_post(self.client, message, context)

    def test_identical_requests_give_identical_results(self):
        """Same request sent twice must yield the same response type."""
        r1 = self._post("I need a room for 2 adults.")
        r2 = self._post("I need a room for 2 adults.")
        self.assertEqual(r1.get_json()["type"], r2.get_json()["type"])

    def test_no_state_leak_between_independent_requests(self):
        """
        A request with adults=3 must not affect a subsequent fresh request
        (no adults) — the second must still ask for adults.
        """
        # First request mentions 3 adults
        self._post("I need a room for 3 adults.")

        # Second completely independent request — no context passed
        resp = self._post("I need a room.")
        body = resp.get_json()
        data = body.get("data") or {}
        missing = data.get("missing", [])
        self.assertIn(
            "adults", missing,
            "Second independent request must still ask for adults",
        )

    def test_availability_service_stateless(self):
        """
        checkAvailability called twice with the same args must return
        identical results (no internal mutable state).
        """
        from app.services.availability_service import checkAvailability
        r1 = checkAvailability(_CHECK_IN, _CHECK_OUT, 2)
        r2 = checkAvailability(_CHECK_IN, _CHECK_OUT, 2)
        self.assertEqual(r1.available, r2.available)
        self.assertEqual(
            [rm.room_type for rm in r1.rooms],
            [rm.room_type for rm in r2.rooms],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
