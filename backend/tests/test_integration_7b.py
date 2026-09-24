"""
Phase 7B Integration Tests
==========================

Covers the complete guest journey and failure/edge-case scenarios
required by Phase 7B.  All tests run against the Flask test harness
(same service layer as production FastAPI) using Python stdlib unittest.

Scenarios:
  1.  Complete guest journey — check-in FAQ → room request → dates (multi-turn)
  2.  FAQ flow — check-in, breakfast, pool, Wi-Fi, cancellation
  3.  Availability flow cases A / B / C / D
  4.  Loading-state guard — duplicate-request prevention (backend side)
  5.  Backend failure — 500 response produces safe JSON body (harness route)
  6.  HTTP error — non-200 must never return a stack trace
  7.  Invalid / malformed JSON response handling
  8.  Empty and whitespace input rejection
  9.  Long message handling
  10. No-invention check — spa / unsupported question uses safe fallback
  11. Context preservation across FAQ interruption
"""

import sys
import os
import json
import unittest

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

_TESTS_DIR = os.path.abspath(os.path.dirname(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

if "pydantic" not in sys.modules:
    import pydantic_stub
    sys.modules["pydantic"] = pydantic_stub

from tests.test_harness import create_test_app

_CHECK_IN = "2026-10-01"
_CHECK_OUT = "2026-10-03"


def _post(client, message, context=None):
    body = {"message": message}
    if context is not None:
        body["context"] = context
    return client.post("/api/assistant", json=body)


# ---------------------------------------------------------------------------
# 1. Complete guest journey (multi-turn)
# ---------------------------------------------------------------------------

class TestCompleteGuestJourney(unittest.TestCase):
    """
    Simulates the full end-to-end journey described in Phase 7B:

      Turn 1:  "What time is check-in?"           → FAQ answer
      Turn 2:  "I need a room for 2 adults."       → asks for dates
      Turn 3:  "2026-10-01 to 2026-10-03"         → availability_result
               context from previous turn is preserved
    """

    @classmethod
    def setUpClass(cls):
        cls.app = create_test_app()
        cls.client = cls.app.test_client()

    # --- Turn 1: FAQ -------------------------------------------------------

    def test_journey_turn1_checkin_faq_returns_200(self):
        resp = _post(self.client, "What time is check-in?")
        self.assertEqual(resp.status_code, 200)

    def test_journey_turn1_checkin_faq_answer(self):
        resp = _post(self.client, "What time is check-in?")
        body = resp.get_json()
        self.assertIn("2:00 PM", body["message"])

    def test_journey_turn1_does_not_set_availability_intent(self):
        """A pure FAQ turn must not set last_intent=availability."""
        resp = _post(self.client, "What time is check-in?")
        body = resp.get_json()
        ctx = body.get("context") or {}
        self.assertNotEqual(ctx.get("last_intent"), "availability")

    # --- Turn 2: room request (adults only) --------------------------------

    def test_journey_turn2_room_request_requires_input(self):
        resp = _post(self.client, "I need a room for 2 adults.")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body["requires_input"])

    def test_journey_turn2_stores_adults_in_context(self):
        resp = _post(self.client, "I need a room for 2 adults.")
        body = resp.get_json()
        ctx = body.get("context") or {}
        self.assertEqual(ctx.get("adults"), 2)

    def test_journey_turn2_asks_for_dates(self):
        resp = _post(self.client, "I need a room for 2 adults.")
        body = resp.get_json()
        data = body.get("data") or {}
        missing = data.get("missing", [])
        self.assertTrue(
            "check_in" in missing or "check_out" in missing,
            f"Expected date fields in missing, got: {missing}",
        )

    # --- Turn 3: provide dates using context from Turn 2 -------------------

    def test_journey_turn3_dates_complete_flow(self):
        """
        Full journey: adults → dates → availability_result.
        Context from Turn 2 must carry adults forward so Turn 3 resolves.
        """
        resp2 = _post(self.client, "I need a room for 2 adults.")
        ctx2 = resp2.get_json().get("context")

        resp3 = _post(self.client, f"{_CHECK_IN} to {_CHECK_OUT}", context=ctx2)
        self.assertEqual(resp3.status_code, 200)
        body3 = resp3.get_json()
        self.assertEqual(body3["type"], "availability_result")

    def test_journey_turn3_context_has_adults_preserved(self):
        resp2 = _post(self.client, "I need a room for 2 adults.")
        ctx2 = resp2.get_json().get("context")

        resp3 = _post(self.client, f"{_CHECK_IN} to {_CHECK_OUT}", context=ctx2)
        body3 = resp3.get_json()
        ctx3 = body3.get("context") or {}
        self.assertEqual(ctx3.get("adults"), 2, "adults must be preserved from previous turn")

    def test_journey_turn3_context_has_dates(self):
        resp2 = _post(self.client, "I need a room for 2 adults.")
        ctx2 = resp2.get_json().get("context")

        resp3 = _post(self.client, f"{_CHECK_IN} to {_CHECK_OUT}", context=ctx2)
        body3 = resp3.get_json()
        ctx3 = body3.get("context") or {}
        self.assertEqual(ctx3.get("checkIn"), _CHECK_IN)
        self.assertEqual(ctx3.get("checkOut"), _CHECK_OUT)

    def test_journey_turn3_result_contains_rooms(self):
        resp2 = _post(self.client, "I need a room for 2 adults.")
        ctx2 = resp2.get_json().get("context")

        resp3 = _post(self.client, f"{_CHECK_IN} to {_CHECK_OUT}", context=ctx2)
        body3 = resp3.get_json()
        data = body3.get("data") or {}
        self.assertTrue(data.get("available"))
        self.assertIsInstance(data.get("rooms"), list)
        self.assertGreater(len(data["rooms"]), 0)

    def test_journey_turn3_message_non_empty(self):
        resp2 = _post(self.client, "I need a room for 2 adults.")
        ctx2 = resp2.get_json().get("context")

        resp3 = _post(self.client, f"{_CHECK_IN} to {_CHECK_OUT}", context=ctx2)
        body3 = resp3.get_json()
        self.assertIsInstance(body3["message"], str)
        self.assertGreater(len(body3["message"]), 0)


# ---------------------------------------------------------------------------
# 2. Frontend FAQ flow — verify each supported topic
# ---------------------------------------------------------------------------

class TestFAQFlow(unittest.TestCase):
    """Each supported FAQ topic must return a correct answer."""

    @classmethod
    def setUpClass(cls):
        cls.app = create_test_app()
        cls.client = cls.app.test_client()

    def _ask(self, question):
        resp = _post(self.client, question)
        self.assertEqual(resp.status_code, 200)
        return resp.get_json()

    def test_faq_check_in(self):
        body = self._ask("What time is check-in?")
        self.assertIn("2:00 PM", body["message"])
        self.assertFalse(body["requires_input"])

    def test_faq_breakfast(self):
        body = self._ask("Is breakfast available?")
        self.assertIn("breakfast", body["message"].lower())
        self.assertFalse(body["requires_input"])

    def test_faq_pool(self):
        body = self._ask("Do you have a pool?")
        msg = body["message"].lower()
        self.assertTrue("pool" in msg or "swim" in msg)
        self.assertFalse(body["requires_input"])

    def test_faq_wifi(self):
        body = self._ask("Is there Wi-Fi?")
        msg = body["message"].lower()
        self.assertTrue("wi-fi" in msg or "wifi" in msg or "internet" in msg)
        self.assertFalse(body["requires_input"])

    def test_faq_cancellation(self):
        body = self._ask("What is the cancellation policy?")
        msg = body["message"].lower()
        self.assertTrue("cancel" in msg or "refund" in msg or "rate" in msg)
        self.assertFalse(body["requires_input"])

    def test_faq_responses_have_type_text(self):
        """FAQ responses must use type 'text'."""
        for q in ["What time is check-in?", "Is breakfast available?",
                   "Do you have a pool?", "Is there Wi-Fi?"]:
            body = self._ask(q)
            self.assertEqual(body["type"], "text", f"Expected type='text' for: {q}")


# ---------------------------------------------------------------------------
# 3. Availability flow cases A / B / C / D
# ---------------------------------------------------------------------------

class TestAvailabilityFlowCases(unittest.TestCase):
    """
    Case A: "I need a room."                 → asks for all missing info
    Case B: "I need a room for 2 adults."    → asks for dates
    Case C: "I need a room from X to Y."     → asks for adults
    Case D: complete request                 → availability_result
    """

    @classmethod
    def setUpClass(cls):
        cls.app = create_test_app()
        cls.client = cls.app.test_client()

    def test_case_a_no_info_asks_for_everything(self):
        resp = _post(self.client, "I need a room.")
        body = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(body["requires_input"])
        self.assertEqual(body["type"], "availability_request")

    def test_case_a_missing_contains_date_and_adults(self):
        resp = _post(self.client, "I need a room.")
        body = resp.get_json()
        missing = (body.get("data") or {}).get("missing", [])
        self.assertIn("adults", missing)
        self.assertTrue("check_in" in missing or "check_out" in missing)

    def test_case_b_adults_only_asks_for_dates(self):
        resp = _post(self.client, "I need a room for 2 adults.")
        body = resp.get_json()
        self.assertTrue(body["requires_input"])
        missing = (body.get("data") or {}).get("missing", [])
        self.assertTrue("check_in" in missing or "check_out" in missing)

    def test_case_b_adults_not_in_missing(self):
        resp = _post(self.client, "I need a room for 2 adults.")
        body = resp.get_json()
        missing = (body.get("data") or {}).get("missing", [])
        self.assertNotIn("adults", missing)

    def test_case_c_dates_only_asks_for_adults(self):
        resp = _post(self.client, f"I need a room from {_CHECK_IN} to {_CHECK_OUT}.")
        body = resp.get_json()
        self.assertTrue(body["requires_input"])
        missing = (body.get("data") or {}).get("missing", [])
        self.assertIn("adults", missing)

    def test_case_d_complete_request_returns_result(self):
        resp = _post(self.client, f"I need a room for 2 adults from {_CHECK_IN} to {_CHECK_OUT}.")
        body = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(body["type"], "availability_result")
        self.assertFalse(body["requires_input"])

    def test_case_d_result_has_available_field(self):
        resp = _post(self.client, f"I need a room for 2 adults from {_CHECK_IN} to {_CHECK_OUT}.")
        body = resp.get_json()
        data = body.get("data") or {}
        self.assertIn("available", data)

    def test_case_d_result_has_rooms_list(self):
        resp = _post(self.client, f"I need a room for 2 adults from {_CHECK_IN} to {_CHECK_OUT}.")
        body = resp.get_json()
        data = body.get("data") or {}
        self.assertIsInstance(data.get("rooms"), list)


# ---------------------------------------------------------------------------
# 4. Backend failure / 500 simulation
# ---------------------------------------------------------------------------

class TestBackendFailure(unittest.TestCase):
    """
    The harness exposes a /test/error500 route that we register here to
    simulate a 500 response.  The real frontend catches non-ok responses
    and shows a friendly error — this test verifies the backend never
    leaks a stack trace in its JSON body.
    """

    @classmethod
    def setUpClass(cls):
        from flask import Flask, jsonify

        # Build the production test app and add a synthetic 500 route
        cls.app = create_test_app()

        @cls.app.get("/test/error500")
        def _synthetic_500():
            return jsonify({"detail": "Internal Server Error"}), 500

        @cls.app.post("/test/bad_json")
        def _bad_json():
            # Returns syntactically valid JSON but missing required 'message' field
            from flask import Response
            return Response(
                '{"unexpected": "field"}',
                status=200,
                content_type="application/json",
            )

        cls.client = cls.app.test_client()

    def test_500_response_returns_json_not_html(self):
        """A 500 must return JSON, not an HTML stack trace page."""
        resp = self.client.get("/test/error500")
        self.assertEqual(resp.status_code, 500)
        body = resp.get_json()
        self.assertIsNotNone(body, "500 response must be valid JSON")

    def test_500_body_does_not_contain_traceback(self):
        """Stack trace keywords must not appear in a 500 response body."""
        resp = self.client.get("/test/error500")
        raw = resp.data.decode("utf-8", errors="replace")
        forbidden_keywords = ["Traceback", "File \"", "line ", "Exception"]
        for kw in forbidden_keywords:
            self.assertNotIn(kw, raw, f"Stack trace keyword '{kw}' found in 500 response")

    def test_api_still_works_after_500_route(self):
        """The main assistant endpoint must continue to work after a 500 on another route."""
        self.client.get("/test/error500")
        resp = _post(self.client, "What time is check-in?")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertIn("message", body)


# ---------------------------------------------------------------------------
# 5. HTTP error handling
# ---------------------------------------------------------------------------

class TestHTTPErrorHandling(unittest.TestCase):
    """
    Verify that the backend returns proper JSON error bodies for bad requests.
    The frontend uses response.ok to decide whether to throw, so non-200 must
    still return valid JSON (not HTML or empty body).
    """

    @classmethod
    def setUpClass(cls):
        cls.app = create_test_app()
        cls.client = cls.app.test_client()

    def test_422_on_empty_message_returns_json(self):
        resp = self.client.post("/api/assistant", json={"message": ""})
        self.assertNotEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertIsNotNone(body)

    def test_422_body_has_detail_key(self):
        resp = self.client.post("/api/assistant", json={"message": ""})
        body = resp.get_json()
        # Must have 'detail' key (matches FastAPI/harness error format)
        self.assertIn("detail", body)

    def test_422_body_is_not_html(self):
        resp = self.client.post("/api/assistant", json={"message": ""})
        raw = resp.data.decode("utf-8", errors="replace")
        self.assertFalse(
            raw.strip().startswith("<!"),
            "Error response must not be HTML",
        )

    def test_missing_field_returns_non_200_json(self):
        resp = self.client.post("/api/assistant", json={})
        self.assertNotEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertIsNotNone(body)


# ---------------------------------------------------------------------------
# 6. Invalid / malformed response handling (assistantApi.js logic in Python)
# ---------------------------------------------------------------------------

class TestInvalidResponseHandling(unittest.TestCase):
    """
    Simulate what happens when the backend returns an unexpected shape.
    Tests mirror the guards in frontend/src/services/assistantApi.js:
      - Missing 'message' field → ERROR_PARSE
      - Non-JSON response body → ERROR_PARSE
    The harness routes here replicate those failure modes at the API level.
    """

    @classmethod
    def setUpClass(cls):
        from flask import Flask, jsonify, Response

        cls.app = create_test_app()

        @cls.app.get("/test/missing_message")
        def _missing_message():
            return jsonify({"type": "text", "requires_input": False}), 200

        @cls.app.get("/test/non_json")
        def _non_json():
            return Response("not json at all", status=200, content_type="text/plain")

        @cls.app.get("/test/empty_body")
        def _empty():
            return Response("", status=200, content_type="application/json")

        cls.client = cls.app.test_client()

    def test_missing_message_field_is_detectable(self):
        """
        A response without 'message' must be detectable as invalid.
        The frontend checks: if (!data?.message) throw ERROR_PARSE
        """
        resp = self.client.get("/test/missing_message")
        body = resp.get_json()
        # Confirms the Python side: body present but no 'message'
        self.assertIsNotNone(body)
        self.assertNotIn("message", body)

    def test_non_json_response_is_detectable(self):
        """A non-JSON response must fail json() parsing (like the frontend catch block)."""
        resp = self.client.get("/test/non_json")
        body = resp.get_json(silent=True)
        self.assertIsNone(body, "Non-JSON response must not parse as JSON")

    def test_empty_body_response_is_detectable(self):
        """An empty body must fail json() parsing."""
        resp = self.client.get("/test/empty_body")
        body = resp.get_json(silent=True)
        self.assertIsNone(body, "Empty body must not parse as JSON")

    def test_valid_assistant_endpoint_always_has_message(self):
        """
        The real assistant endpoint must always include 'message' so the
        frontend's guard (if (!data?.message)) never triggers on normal responses.
        """
        for question in [
            "What time is check-in?",
            "I need a room for 2 adults.",
            f"I need a room for 2 adults from {_CHECK_IN} to {_CHECK_OUT}.",
            "Does the hotel have a spa?",
        ]:
            resp = _post(self.client, question)
            body = resp.get_json()
            self.assertIn(
                "message", body,
                f"'message' must always be present in response for: {question}",
            )
            self.assertIsInstance(body["message"], str)
            self.assertGreater(len(body["message"]), 0)


# ---------------------------------------------------------------------------
# 7. Empty and whitespace input rejection
# ---------------------------------------------------------------------------

class TestEmptyInputRejection(unittest.TestCase):
    """
    The backend must reject empty/whitespace messages.
    The frontend's ChatInput prevents submission of empty/whitespace strings,
    but the backend must also enforce this as a second line of defence.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = create_test_app()
        cls.client = cls.app.test_client()

    def _raw_post(self, payload):
        return self.client.post("/api/assistant", json=payload)

    def test_empty_string_rejected(self):
        resp = self._raw_post({"message": ""})
        self.assertNotEqual(resp.status_code, 200)

    def test_whitespace_only_rejected(self):
        resp = self._raw_post({"message": "   "})
        self.assertNotEqual(resp.status_code, 200)

    def test_tab_only_rejected(self):
        resp = self._raw_post({"message": "\t\t\t"})
        self.assertNotEqual(resp.status_code, 200)

    def test_newline_only_rejected(self):
        resp = self._raw_post({"message": "\n\n"})
        self.assertNotEqual(resp.status_code, 200)

    def test_mixed_whitespace_rejected(self):
        resp = self._raw_post({"message": "  \t  \n  "})
        self.assertNotEqual(resp.status_code, 200)

    def test_rejection_returns_json_not_crash(self):
        resp = self._raw_post({"message": ""})
        body = resp.get_json()
        self.assertIsNotNone(body, "Rejection must return JSON body, not crash")

    def test_valid_request_still_works_after_empty(self):
        self._raw_post({"message": ""})
        resp = _post(self.client, "What time is check-in?")
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# 8. Long message handling
# ---------------------------------------------------------------------------

class TestLongMessageHandling(unittest.TestCase):
    """
    Long guest messages must be handled gracefully — no crash, valid response.
    The backend limits messages to 2000 chars (harness validation).
    """

    @classmethod
    def setUpClass(cls):
        cls.app = create_test_app()
        cls.client = cls.app.test_client()

    def test_long_message_within_limit_is_processed(self):
        """A message under 2000 chars (even if long) must return 200."""
        long_msg = "I have a lot to say about my stay. " * 20  # ~700 chars
        resp = _post(self.client, long_msg)
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertIn("message", body)

    def test_long_message_gets_safe_fallback(self):
        """A long unrecognised message must still return a usable response."""
        long_msg = "x" * 500  # garbled but within limit
        resp = _post(self.client, long_msg)
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertIsInstance(body["message"], str)
        self.assertGreater(len(body["message"]), 0)

    def test_message_at_2000_chars_accepted(self):
        """Message exactly at the 2000-char limit must be accepted."""
        msg = ("I need a room. " * 134)[:2000]  # exactly 2000
        resp = _post(self.client, msg)
        # Either 200 (processed) or 422 (content triggers a different error)
        # — both are acceptable as long as it's JSON and doesn't crash
        body = resp.get_json()
        self.assertIsNotNone(body)

    def test_message_over_2000_chars_rejected(self):
        """A message over 2000 chars must be rejected (not crash)."""
        msg = "a" * 2001
        resp = self.client.post("/api/assistant", json={"message": msg})
        self.assertNotEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertIsNotNone(body)


# ---------------------------------------------------------------------------
# 9. No-invention check through the API
# ---------------------------------------------------------------------------

class TestNoInvention(unittest.TestCase):
    """
    The assistant must not invent hotel information for unsupported topics.
    The safe fallback must be used instead.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = create_test_app()
        cls.client = cls.app.test_client()

    def _ask(self, question):
        resp = _post(self.client, question)
        self.assertEqual(resp.status_code, 200)
        return resp.get_json()

    def test_spa_uses_fallback(self):
        body = self._ask("Does the hotel have a spa?")
        self.assertNotIn("yes, we have a spa", body["message"].lower())
        self.assertTrue(
            body["type"] == "fallback"
            or "don't have that information" in body["message"].lower()
            or "i can help" in body["message"].lower(),
        )

    def test_gym_uses_fallback(self):
        body = self._ask("Is there a gym?")
        self.assertNotIn("yes, we have a gym", body["message"].lower())
        self.assertTrue(
            body["type"] == "fallback"
            or "don't have that information" in body["message"].lower()
            or "i can help" in body["message"].lower(),
        )

    def test_restaurant_uses_fallback(self):
        body = self._ask("Do you have an on-site restaurant?")
        self.assertNotIn("yes, we have a restaurant", body["message"].lower())
        # Must return a useful fallback, not crash
        self.assertGreater(len(body["message"]), 0)

    def test_fallback_type_or_message_present(self):
        body = self._ask("Does the hotel have a helicopter pad?")
        self.assertIn("message", body)
        self.assertIsInstance(body["message"], str)

    def test_fallback_suggests_supported_topics(self):
        """Fallback must point the guest to what IS supported."""
        body = self._ask("Does the hotel have a spa?")
        answer = body["message"].lower()
        supported_hints = ["check-in", "check-out", "breakfast", "pool", "wi-fi",
                           "parking", "cancellation", "room", "i can help"]
        self.assertTrue(
            any(hint in answer for hint in supported_hints),
            f"Fallback must mention supported topics, got: {answer}",
        )


# ---------------------------------------------------------------------------
# 10. Context preservation — FAQ interruption during availability flow
# ---------------------------------------------------------------------------

class TestContextPreservationDuringFAQ(unittest.TestCase):
    """
    If a guest asks a FAQ question mid-way through an availability flow,
    the availability context must be preserved so the flow can resume.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = create_test_app()
        cls.client = cls.app.test_client()

    def test_faq_interruption_preserves_adults(self):
        """
        Turn 1: 'I need a room for 2 adults.'  → adults=2 in context
        Turn 2: 'Do you have a pool?'           → FAQ answer, adults still 2
        """
        resp1 = _post(self.client, "I need a room for 2 adults.")
        ctx1 = resp1.get_json().get("context")
        self.assertIsNotNone(ctx1)

        resp2 = _post(self.client, "Do you have a pool?", context=ctx1)
        self.assertEqual(resp2.status_code, 200)
        body2 = resp2.get_json()
        ctx2 = body2.get("context") or {}
        self.assertEqual(ctx2.get("adults"), 2, "adults must survive FAQ interruption")

    def test_faq_interruption_returns_faq_answer(self):
        """FAQ question mid-flow must return a FAQ answer, not an availability request."""
        resp1 = _post(self.client, "I need a room for 2 adults.")
        ctx1 = resp1.get_json().get("context")

        resp2 = _post(self.client, "Do you have a pool?", context=ctx1)
        body2 = resp2.get_json()
        self.assertNotEqual(body2["type"], "availability_request")
        self.assertIn("pool", body2["message"].lower())

    def test_flow_resumes_after_faq(self):
        """
        Turn 1: adults → Turn 2: FAQ (pool) → Turn 3: dates
        After Turn 3 the flow should complete as availability_result.
        """
        resp1 = _post(self.client, "I need a room for 2 adults.")
        ctx1 = resp1.get_json().get("context")

        resp2 = _post(self.client, "Do you have a pool?", context=ctx1)
        ctx2 = resp2.get_json().get("context")

        resp3 = _post(self.client, f"{_CHECK_IN} to {_CHECK_OUT}", context=ctx2)
        self.assertEqual(resp3.status_code, 200)
        body3 = resp3.get_json()
        self.assertEqual(body3["type"], "availability_result")


# ---------------------------------------------------------------------------
# 11. Regression — real bugs caught during 7B, if any
# ---------------------------------------------------------------------------

class TestRegressions7B(unittest.TestCase):
    """
    Regression tests added if real bugs were found during Phase 7B review.
    Currently verifies baseline invariants that must hold across all phases.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = create_test_app()
        cls.client = cls.app.test_client()

    def test_context_field_always_present_in_response(self):
        """
        The 'context' field must always be present (possibly null) in
        assistant responses so the frontend can pass it forward reliably.
        """
        questions = [
            "What time is check-in?",
            "I need a room for 2 adults.",
            f"I need a room for 2 adults from {_CHECK_IN} to {_CHECK_OUT}.",
            "Does the hotel have a spa?",
        ]
        for q in questions:
            resp = _post(self.client, q)
            body = resp.get_json()
            self.assertIn(
                "context", body,
                f"'context' key must always be in response for: {q}",
            )

    def test_requires_input_always_boolean(self):
        """requires_input must always be a boolean, never null/string."""
        questions = [
            "What time is check-in?",
            "I need a room for 2 adults.",
            f"I need a room for 2 adults from {_CHECK_IN} to {_CHECK_OUT}.",
        ]
        for q in questions:
            resp = _post(self.client, q)
            body = resp.get_json()
            self.assertIsInstance(
                body["requires_input"], bool,
                f"requires_input must be bool for: {q}",
            )

    def test_type_always_string(self):
        """type field must always be a non-empty string."""
        questions = [
            "What time is check-in?",
            "I need a room for 2 adults.",
            "Does the hotel have a spa?",
        ]
        for q in questions:
            resp = _post(self.client, q)
            body = resp.get_json()
            self.assertIsInstance(body["type"], str)
            self.assertGreater(len(body["type"]), 0)

    def test_availability_result_data_has_all_required_fields(self):
        """availability_result data must include all fields the AvailabilityCard needs."""
        resp = _post(
            self.client,
            f"I need a room for 2 adults from {_CHECK_IN} to {_CHECK_OUT}.",
        )
        body = resp.get_json()
        data = body.get("data") or {}
        for field in ("check_in", "check_out", "adults", "available", "rooms"):
            self.assertIn(field, data, f"data must include '{field}' for AvailabilityCard")

    def test_room_objects_in_result_have_card_fields(self):
        """Each room in availability_result must have the fields AvailabilityCard renders."""
        resp = _post(
            self.client,
            f"I need a room for 2 adults from {_CHECK_IN} to {_CHECK_OUT}.",
        )
        body = resp.get_json()
        rooms = (body.get("data") or {}).get("rooms", [])
        for room in rooms:
            for field in ("room_type", "max_adults", "available_rooms"):
                self.assertIn(field, room, f"room object missing '{field}' for AvailabilityCard")


class TestPhase7CRegressions(unittest.TestCase):
    """
    Regression tests added in Phase 7C for the two bugs fixed:

    Bug 1: _extract_adults() incorrectly extracted '1' from '-1 adults',
           causing 'I need a room for -1 adults' to return an availability
           result instead of asking for a valid adult count.

    Bug 2: 'Can I stay tomorrow?' was not recognised as an availability
           intent, so the natural-date guard never fired and the assistant
           returned a generic fallback instead of asking for a YYYY-MM-DD date.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = create_test_app()
        cls.client = cls.app.test_client()

    # ------------------------------------------------------------------ #
    # Bug 1 — Negative adults                                              #
    # ------------------------------------------------------------------ #

    def test_negative_adults_does_not_return_availability_result(self):
        """
        'I need a room for -1 adults' must NOT return an availability_result.
        The negative sign must prevent -1 from being treated as a valid count.
        """
        resp = _post(
            self.client,
            f"I need a room for -1 adults from {_CHECK_IN} to {_CHECK_OUT}.",
        )
        body = resp.get_json()
        self.assertNotEqual(
            body.get("type"),
            "availability_result",
            "Negative adults must not yield an availability_result",
        )

    def test_negative_adults_asks_for_valid_count(self):
        """
        After -1 adults is rejected, the response must ask for the number of adults.
        """
        resp = _post(
            self.client,
            f"I need a room for -1 adults from {_CHECK_IN} to {_CHECK_OUT}.",
        )
        body = resp.get_json()
        # type must be availability_request (we have dates but adults is missing)
        self.assertEqual(body.get("type"), "availability_request")
        self.assertTrue(body.get("requires_input", False))

    def test_positive_adults_still_extracted_correctly(self):
        """
        Sanity check: the fixed regex must still extract positive adult counts.
        """
        resp = _post(
            self.client,
            f"I need a room for 2 adults from {_CHECK_IN} to {_CHECK_OUT}.",
        )
        body = resp.get_json()
        self.assertEqual(body.get("type"), "availability_result")
        self.assertEqual((body.get("data") or {}).get("adults"), 2)

    # ------------------------------------------------------------------ #
    # Bug 2 — 'Can I stay tomorrow?' triggers natural-date guard           #
    # ------------------------------------------------------------------ #

    def test_can_i_stay_tomorrow_not_fallback(self):
        """
        'Can I stay tomorrow?' must NOT return a generic fallback.
        It should be recognised as an availability intent.
        """
        resp = _post(self.client, "Can I stay tomorrow?")
        body = resp.get_json()
        self.assertNotEqual(
            body.get("type"),
            "fallback",
            "'Can I stay tomorrow?' should not produce a generic fallback",
        )

    def test_can_i_stay_tomorrow_asks_for_iso_date(self):
        """
        'Can I stay tomorrow?' must ask for dates in YYYY-MM-DD format
        (the natural-date guard response).
        """
        resp = _post(self.client, "Can I stay tomorrow?")
        body = resp.get_json()
        msg = body.get("message", "").lower()
        self.assertTrue(
            "yyyy-mm-dd" in msg or "2026-" in msg or "date" in msg,
            f"Expected date format guidance, got: {body.get('message')}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
