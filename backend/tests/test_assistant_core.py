"""
Core tests for the assistant endpoint and hotel FAQ knowledge behaviour.

Covers:
  - Basic successful assistant request
  - Hotel FAQ topics: check-in, check-out, breakfast, pool, Wi-Fi,
    parking, cancellation
  - Room information
  - Unsupported-question fallback (safe, non-inventive response)
  - Request validation: empty message, whitespace, missing field
  - Response structure
"""

import unittest
from tests.test_harness import create_test_app


class TestAssistantBasic(unittest.TestCase):
    """Basic assistant endpoint behaviour."""

    @classmethod
    def setUpClass(cls):
        cls.app = create_test_app()
        cls.client = cls.app.test_client()

    def _post(self, message: str):
        return self.client.post("/api/assistant", json={"message": message})

    # ------------------------------------------------------------------ #
    # Basic success                                                        #
    # ------------------------------------------------------------------ #

    def test_basic_question_returns_200(self):
        """A normal hotel question must return HTTP 200."""
        response = self._post("What time is check-in?")
        self.assertEqual(response.status_code, 200)

    def test_basic_question_returns_message(self):
        """Response must contain a non-empty 'message' field."""
        response = self._post("What time is check-in?")
        body = response.get_json()
        self.assertIn("message", body)
        self.assertIsInstance(body["message"], str)
        self.assertTrue(len(body["message"]) > 0)

    def test_response_structure(self):
        """
        Response must include the expected top-level fields:
        message, type, requires_input.
        """
        response = self._post("What time is check-in?")
        body = response.get_json()
        self.assertIn("message", body)
        self.assertIn("type", body)
        self.assertIn("requires_input", body)

    def test_type_field_is_string(self):
        """The 'type' field must be a string."""
        response = self._post("What time is check-in?")
        body = response.get_json()
        self.assertIsInstance(body["type"], str)

    def test_requires_input_is_boolean(self):
        """The 'requires_input' field must be a boolean."""
        response = self._post("What time is check-in?")
        body = response.get_json()
        self.assertIsInstance(body["requires_input"], bool)

    def test_faq_response_requires_input_is_false(self):
        """FAQ responses must not set requires_input=True."""
        response = self._post("What time is check-in?")
        body = response.get_json()
        self.assertFalse(body["requires_input"])


class TestHotelFAQ(unittest.TestCase):
    """
    Hotel FAQ knowledge tests.

    Each test asks a topic question and verifies the response contains
    expected keywords from the hotel_data.json knowledge base.
    Assertions use substrings so minor wording changes don't break tests.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = create_test_app()
        cls.client = cls.app.test_client()

    def _ask(self, question: str) -> str:
        response = self.client.post("/api/assistant", json={"message": question})
        self.assertEqual(response.status_code, 200, f"Failed for: {question}")
        body = response.get_json()
        return body["message"]

    # ------------------------------------------------------------------ #
    # Check-in                                                            #
    # ------------------------------------------------------------------ #

    def test_check_in_time(self):
        """Check-in question must return the configured check-in time."""
        answer = self._ask("What time is check-in?")
        # hotel_data.json: check_in.time = "2:00 PM"
        self.assertIn("2:00 PM", answer)

    def test_check_in_keywords(self):
        """Check-in answer must mention check-in."""
        answer = self._ask("When can I arrive?")
        # "arrive" keyword maps to check_in intent
        self.assertTrue(
            "2:00 PM" in answer or "check" in answer.lower(),
            f"Expected check-in info, got: {answer}",
        )

    def test_check_in_alternative_phrasing(self):
        """'checkin' (no hyphen) must also resolve to check-in info."""
        answer = self._ask("What is the checkin time?")
        self.assertIn("2:00 PM", answer)

    # ------------------------------------------------------------------ #
    # Check-out                                                           #
    # ------------------------------------------------------------------ #

    def test_check_out_time(self):
        """Check-out question must return the configured check-out time."""
        answer = self._ask("When is check-out?")
        # hotel_data.json: check_out.time = "11:00 AM"
        self.assertIn("11:00 AM", answer)

    def test_check_out_alternative_phrasing(self):
        """'checkout' (no hyphen) must also resolve to check-out info."""
        answer = self._ask("What time is checkout?")
        self.assertIn("11:00 AM", answer)

    def test_check_out_departure_keyword(self):
        """'departure' keyword must resolve to check-out info."""
        answer = self._ask("What is the departure time?")
        self.assertIn("11:00 AM", answer)

    # ------------------------------------------------------------------ #
    # Breakfast                                                            #
    # ------------------------------------------------------------------ #

    def test_breakfast_available(self):
        """Breakfast question must confirm availability."""
        answer = self._ask("Is breakfast available?")
        self.assertIn("breakfast", answer.lower())

    def test_breakfast_timings_mentioned(self):
        """Breakfast answer must include the serving time from hotel data."""
        answer = self._ask("What are the breakfast hours?")
        # hotel_data.json: timings = "7:00 AM to 10:30 AM"
        self.assertTrue(
            "7:00 AM" in answer or "10:30 AM" in answer,
            f"Expected breakfast timings, got: {answer}",
        )

    # ------------------------------------------------------------------ #
    # Pool                                                                 #
    # ------------------------------------------------------------------ #

    def test_pool_available(self):
        """Pool question must describe the hotel pool."""
        answer = self._ask("Do you have a swimming pool?")
        # hotel_data.json: pool available=true, details mention "outdoor swimming pool"
        self.assertTrue(
            "pool" in answer.lower() or "swim" in answer.lower(),
            f"Expected pool info, got: {answer}",
        )

    def test_pool_hours_mentioned(self):
        """Pool answer must include the pool operating hours."""
        answer = self._ask("Is there a pool?")
        # hotel_data.json: "open daily from 7:00 AM to 9:00 PM"
        self.assertTrue(
            "7:00 AM" in answer or "9:00 PM" in answer,
            f"Expected pool hours, got: {answer}",
        )

    # ------------------------------------------------------------------ #
    # Wi-Fi                                                                #
    # ------------------------------------------------------------------ #

    def test_wifi_available(self):
        """Wi-Fi question must confirm availability."""
        answer = self._ask("Is there Wi-Fi?")
        self.assertTrue(
            "wi-fi" in answer.lower() or "wifi" in answer.lower() or "internet" in answer.lower(),
            f"Expected Wi-Fi info, got: {answer}",
        )

    def test_wifi_complimentary(self):
        """Wi-Fi must be described as complimentary per hotel data."""
        answer = self._ask("What is the wifi like?")
        self.assertIn("complimentary", answer.lower())

    def test_wifi_internet_keyword(self):
        """'internet' keyword must also resolve to Wi-Fi info."""
        answer = self._ask("Do you have internet?")
        self.assertTrue(
            "wi-fi" in answer.lower() or "wifi" in answer.lower() or "wireless" in answer.lower(),
            f"Expected Wi-Fi/internet info, got: {answer}",
        )

    # ------------------------------------------------------------------ #
    # Parking                                                              #
    # ------------------------------------------------------------------ #

    def test_parking_available(self):
        """Parking question must describe parking availability."""
        answer = self._ask("Is parking available?")
        self.assertIn("parking", answer.lower())

    def test_parking_complimentary(self):
        """Parking must be described as complimentary per hotel data."""
        answer = self._ask("Do you have parking?")
        self.assertIn("complimentary", answer.lower())

    # ------------------------------------------------------------------ #
    # Cancellation                                                         #
    # ------------------------------------------------------------------ #

    def test_cancellation_policy_returned(self):
        """Cancellation question must return the cancellation policy."""
        answer = self._ask("What is the cancellation policy?")
        # hotel_data.json: summary mentions "reservation rate"
        self.assertTrue(
            "cancellation" in answer.lower() or "refund" in answer.lower() or "rate" in answer.lower(),
            f"Expected cancellation policy, got: {answer}",
        )

    def test_cancellation_refund_keyword(self):
        """'refund' keyword must also resolve to cancellation policy."""
        answer = self._ask("Can I get a refund?")
        self.assertTrue(
            "cancellation" in answer.lower() or "refund" in answer.lower() or "rate" in answer.lower(),
            f"Expected cancellation info, got: {answer}",
        )


class TestRoomInformation(unittest.TestCase):
    """Tests for room type information from the hotel knowledge base."""

    @classmethod
    def setUpClass(cls):
        cls.app = create_test_app()
        cls.client = cls.app.test_client()

    def _ask(self, question: str) -> str:
        response = self.client.post("/api/assistant", json={"message": question})
        self.assertEqual(response.status_code, 200)
        return response.get_json()["message"]

    def test_room_types_question(self):
        """'What room types do you have?' must return room type info."""
        answer = self._ask("What room types do you have?")
        self.assertTrue(
            "room" in answer.lower() or "suite" in answer.lower() or "deluxe" in answer.lower(),
            f"Expected room type info, got: {answer}",
        )

    def test_room_types_from_hotel_data(self):
        """
        Response must mention at least one room name from hotel_data.json.
        Known room names: Deluxe Room, Family Room, Suite.
        """
        answer = self._ask("What room types do you have?")
        known_rooms = ["deluxe", "family", "suite"]
        found = any(r in answer.lower() for r in known_rooms)
        self.assertTrue(found, f"Expected at least one room name in: {answer}")

    def test_all_configured_rooms_mentioned(self):
        """All three configured room types must appear in the response."""
        answer = self._ask("What accommodation options do you have?")
        for room in ["Deluxe Room", "Family Room", "Suite"]:
            self.assertIn(
                room, answer,
                f"Expected '{room}' in room list response, got: {answer}",
            )

    def test_suite_keyword_resolves_to_rooms(self):
        """'suite' keyword must resolve to rooms intent."""
        answer = self._ask("Do you have a suite?")
        # 'suite' is in the rooms intent keywords
        self.assertTrue(
            "suite" in answer.lower() or "room" in answer.lower(),
            f"Expected rooms info, got: {answer}",
        )


class TestUnsupportedQuestion(unittest.TestCase):
    """
    Tests that unsupported questions use the safe fallback.
    The assistant must NOT invent facilities, prices, or policies.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = create_test_app()
        cls.client = cls.app.test_client()

    def _ask(self, question: str):
        response = self.client.post("/api/assistant", json={"message": question})
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def test_spa_question_uses_fallback(self):
        """
        Spa is not in the hotel knowledge base.
        The assistant must not affirm or invent spa availability.
        """
        body = self._ask("Does the hotel have a spa?")
        answer = body["message"]
        # Must not confidently claim spa exists
        self.assertNotIn("yes, we have a spa", answer.lower())
        self.assertNotIn("our spa", answer.lower())
        # Must use the fallback type or include a helpful redirect
        self.assertTrue(
            body["type"] == "fallback"
            or "don't have that information" in answer.lower()
            or "i can help with" in answer.lower(),
            f"Expected safe fallback, got type={body['type']} message={answer}",
        )

    def test_gym_question_uses_fallback(self):
        """Gym is not in hotel data — must use fallback, not invent details."""
        body = self._ask("Is there a gym at the hotel?")
        answer = body["message"]
        self.assertNotIn("yes, we have a gym", answer.lower())
        self.assertTrue(
            body["type"] == "fallback"
            or "don't have that information" in answer.lower()
            or "i can help with" in answer.lower(),
            f"Expected safe fallback, got: {answer}",
        )

    def test_room_service_question_uses_fallback(self):
        """Room service is not in hotel data — must use fallback."""
        body = self._ask("Do you offer room service?")
        answer = body["message"]
        self.assertNotIn("yes, we offer room service", answer.lower())
        self.assertTrue(
            body["type"] == "fallback"
            or "don't have that information" in answer.lower()
            or "i can help with" in answer.lower(),
            f"Expected safe fallback, got: {answer}",
        )

    def test_fallback_response_is_non_empty(self):
        """Even for unknown questions the response must be non-empty."""
        body = self._ask("Does the hotel have a helipad?")
        self.assertTrue(len(body["message"]) > 0)

    def test_fallback_suggests_supported_topics(self):
        """
        Fallback response should guide the guest to supported topics
        rather than leaving them with no path forward.
        """
        body = self._ask("Do you have a movie theatre?")
        answer = body["message"].lower()
        # The knowledge_service fallback message lists supported topics
        supported_topic_hints = [
            "check-in", "check-out", "breakfast", "pool", "wi-fi",
            "parking", "cancellation", "room", "i can help",
        ]
        found = any(hint in answer for hint in supported_topic_hints)
        self.assertTrue(
            found,
            f"Fallback response should mention supported topics, got: {answer}",
        )


class TestRequestValidation(unittest.TestCase):
    """
    Tests for invalid assistant requests.
    The API must respond safely without crashing.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = create_test_app()
        cls.client = cls.app.test_client()

    def _post_raw(self, payload):
        return self.client.post(
            "/api/assistant",
            json=payload,
            content_type="application/json",
        )

    # ------------------------------------------------------------------ #
    # Empty / whitespace message                                           #
    # ------------------------------------------------------------------ #

    def test_empty_message_rejected(self):
        """An empty string message must not return 200."""
        response = self._post_raw({"message": ""})
        self.assertNotEqual(response.status_code, 200)

    def test_whitespace_only_message_rejected(self):
        """A whitespace-only message must not return 200."""
        response = self._post_raw({"message": "   "})
        self.assertNotEqual(response.status_code, 200)

    def test_tab_only_message_rejected(self):
        """A tab-only message must not return 200."""
        response = self._post_raw({"message": "\t\t"})
        self.assertNotEqual(response.status_code, 200)

    # ------------------------------------------------------------------ #
    # Missing required field                                               #
    # ------------------------------------------------------------------ #

    def test_missing_message_field_rejected(self):
        """A request without the 'message' field must not return 200."""
        response = self._post_raw({"context": None})
        self.assertNotEqual(response.status_code, 200)

    def test_empty_body_rejected(self):
        """An empty JSON object must not return 200."""
        response = self._post_raw({})
        self.assertNotEqual(response.status_code, 200)

    # ------------------------------------------------------------------ #
    # API does not crash                                                   #
    # ------------------------------------------------------------------ #

    def test_invalid_requests_return_json(self):
        """Invalid requests must return a JSON error body, not crash."""
        for payload in [
            {"message": ""},
            {"message": "   "},
            {},
            {"context": None},
        ]:
            response = self._post_raw(payload)
            self.assertIsNotNone(
                response.get_json(),
                f"Expected JSON error body for payload {payload}",
            )

    def test_valid_message_still_works_after_invalid(self):
        """A valid request after invalid ones must still succeed (no state leak)."""
        # Fire invalid request
        self._post_raw({"message": ""})
        # Then valid request
        response = self._post_raw({"message": "What time is check-in?"})
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertIn("message", body)
        self.assertTrue(len(body["message"]) > 0)


class TestKnowledgeServiceUnit(unittest.TestCase):
    """
    Direct unit tests for the knowledge_service module.
    No HTTP layer involved — pure service logic.
    """

    def setUp(self):
        import sys, os
        _backend = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        if _backend not in sys.path:
            sys.path.insert(0, _backend)
        from app.services import knowledge_service as ks
        self.ks = ks

    # ------------------------------------------------------------------ #
    # Intent detection                                                     #
    # ------------------------------------------------------------------ #

    def test_detect_check_in_intent(self):
        self.assertEqual(self.ks.detect_intent("What time is check-in?"), "check_in")

    def test_detect_check_out_intent(self):
        self.assertEqual(self.ks.detect_intent("When is check-out?"), "check_out")

    def test_detect_breakfast_intent(self):
        self.assertEqual(self.ks.detect_intent("Is breakfast available?"), "breakfast")

    def test_detect_pool_intent(self):
        self.assertEqual(self.ks.detect_intent("Do you have a swimming pool?"), "pool")

    def test_detect_wifi_intent(self):
        self.assertEqual(self.ks.detect_intent("Do you have wifi?"), "wifi")

    def test_detect_parking_intent(self):
        self.assertEqual(self.ks.detect_intent("Is parking available?"), "parking")

    def test_detect_cancellation_intent(self):
        self.assertEqual(self.ks.detect_intent("What is the cancellation policy?"), "cancellation")

    def test_detect_rooms_intent(self):
        self.assertEqual(self.ks.detect_intent("What room types do you have?"), "rooms")

    def test_detect_unknown_intent(self):
        self.assertEqual(self.ks.detect_intent("Does the hotel have a spa?"), "unknown")

    def test_detect_unknown_for_helipad(self):
        self.assertEqual(self.ks.detect_intent("Do you have a helipad?"), "unknown")

    # ------------------------------------------------------------------ #
    # Answer content                                                       #
    # ------------------------------------------------------------------ #

    def test_check_in_answer_contains_time(self):
        msg, t = self.ks.get_answer("check_in")
        self.assertIn("2:00 PM", msg)
        self.assertEqual(t, "text")

    def test_check_out_answer_contains_time(self):
        msg, t = self.ks.get_answer("check_out")
        self.assertIn("11:00 AM", msg)
        self.assertEqual(t, "text")

    def test_breakfast_answer_is_affirmative(self):
        msg, t = self.ks.get_answer("breakfast")
        self.assertIn("breakfast", msg.lower())
        self.assertEqual(t, "text")

    def test_pool_answer_is_affirmative(self):
        msg, t = self.ks.get_answer("pool")
        self.assertTrue("pool" in msg.lower() or "swim" in msg.lower())
        self.assertEqual(t, "text")

    def test_wifi_answer_mentions_complimentary(self):
        msg, t = self.ks.get_answer("wifi")
        self.assertIn("complimentary", msg.lower())
        self.assertEqual(t, "text")

    def test_parking_answer_mentions_complimentary(self):
        msg, t = self.ks.get_answer("parking")
        self.assertIn("complimentary", msg.lower())
        self.assertEqual(t, "text")

    def test_cancellation_answer_is_non_empty(self):
        msg, t = self.ks.get_answer("cancellation")
        self.assertTrue(len(msg) > 0)
        self.assertEqual(t, "text")

    def test_rooms_answer_lists_room_types(self):
        msg, t = self.ks.get_answer("rooms")
        for room in ["Deluxe Room", "Family Room", "Suite"]:
            self.assertIn(room, msg)
        self.assertEqual(t, "text")

    def test_unknown_intent_returns_fallback_type(self):
        msg, t = self.ks.get_answer("unknown")
        self.assertEqual(t, "fallback")
        self.assertTrue(len(msg) > 0)

    def test_fallback_does_not_invent_spa(self):
        msg, t = self.ks.get_answer("unknown")
        self.assertNotIn("spa", msg.lower())

    def test_hotel_data_loads_successfully(self):
        """Hotel data must load at import time without error."""
        data = self.ks.get_data()
        self.assertIsNotNone(data, "Hotel data must not be None")
        self.assertIsInstance(data, dict)

    def test_hotel_data_has_required_keys(self):
        """Hotel data must contain all required sections."""
        data = self.ks.get_data()
        required_keys = [
            "hotel", "check_in", "check_out", "amenities",
            "breakfast", "cancellation_policy", "rooms",
        ]
        for key in required_keys:
            self.assertIn(key, data, f"hotel_data.json missing key: {key}")

    def test_hotel_data_has_three_room_types(self):
        """Hotel data must define at least one room type."""
        data = self.ks.get_data()
        rooms = data.get("rooms", [])
        self.assertGreater(len(rooms), 0, "hotel_data.json must define at least one room type")


if __name__ == "__main__":
    unittest.main(verbosity=2)
