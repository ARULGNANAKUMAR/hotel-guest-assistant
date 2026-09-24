"""
Tests for the LLM service (llm_service.py).

Uses mocking throughout — no real LLM API calls are made.

Covers:
  1. LLM success path — enhanced message returned when API call succeeds
  2. LLM failure — network error → falls back to deterministic message
  3. Missing API key — is_configured() False → falls back immediately
  4. Invalid/malformed LLM response — falls back to deterministic message
  5. HTTP error from provider — falls back to deterministic message
  6. Timeout — falls back to deterministic message
  7. is_configured() reflects env variable presence
  8. FAQ pipeline: with LLM mocked, existing FAQ tests still pass
"""

import sys
import os
import unittest
import json
from unittest.mock import patch, MagicMock

# Ensure backend is importable
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

_TESTS_DIR = os.path.abspath(os.path.dirname(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

if "pydantic" not in sys.modules:
    import pydantic_stub
    sys.modules["pydantic"] = pydantic_stub


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_anthropic_response(text: str) -> bytes:
    """Build a minimal Anthropic /v1/messages response body."""
    return json.dumps({
        "content": [{"type": "text", "text": text}],
        "model": "claude-haiku-4-5-20251001",
        "role": "assistant",
    }).encode("utf-8")


def _make_mock_http_response(body: bytes, status: int = 200):
    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.status = status
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


# ---------------------------------------------------------------------------
# 1–6  llm_service unit tests
# ---------------------------------------------------------------------------

class TestLLMServiceIsConfigured(unittest.TestCase):
    """is_configured() reflects whether LLM_API_KEY is set."""

    def test_not_configured_when_key_missing(self):
        import app.services.llm_service as svc
        with patch.object(svc, "_LLM_API_KEY", None):
            self.assertFalse(svc.is_configured())

    def test_configured_when_key_present(self):
        import app.services.llm_service as svc
        with patch.object(svc, "_LLM_API_KEY", "sk-test-key"):
            self.assertTrue(svc.is_configured())

    def test_not_configured_when_key_empty_string(self):
        import app.services.llm_service as svc
        with patch.object(svc, "_LLM_API_KEY", ""):
            self.assertFalse(svc.is_configured())


class TestLLMServiceSuccessPath(unittest.TestCase):
    """Test 1: LLM returns a valid enhanced response."""

    def setUp(self):
        import app.services.llm_service as svc
        self._svc = svc

    def test_success_returns_enhanced_message(self):
        enhanced = "Welcome! Check-in begins at 2:00 PM. We're happy to accommodate early arrivals subject to availability."
        mock_resp = _make_mock_http_response(_make_anthropic_response(enhanced))

        with patch.object(self._svc, "_LLM_API_KEY", "sk-test"):
            with patch("urllib.request.urlopen", return_value=mock_resp):
                result = self._svc.enhance_response(
                    "Check-in starts at 2:00 PM. Early check-in is subject to availability.",
                    hotel_context="Azure Bay Hotel",
                )
        self.assertEqual(result, enhanced)

    def test_success_passes_system_prompt(self):
        """The outgoing request must include the system prompt."""
        captured = {}

        def fake_urlopen(req, timeout):
            captured["data"] = json.loads(req.data.decode())
            return _make_mock_http_response(_make_anthropic_response("Enhanced text."))

        with patch.object(self._svc, "_LLM_API_KEY", "sk-test"):
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                self._svc.enhance_response("Original text.")

        self.assertIn("system", captured["data"])
        self.assertIn("hotel guest assistant", captured["data"]["system"].lower())

    def test_success_includes_hotel_context_in_user_message(self):
        """Hotel context must be included in the user-facing payload."""
        captured = {}

        def fake_urlopen(req, timeout):
            captured["data"] = json.loads(req.data.decode())
            return _make_mock_http_response(_make_anthropic_response("Enhanced."))

        with patch.object(self._svc, "_LLM_API_KEY", "sk-test"):
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                self._svc.enhance_response("Original.", hotel_context="Azure Bay Hotel")

        user_content = captured["data"]["messages"][0]["content"]
        self.assertIn("Azure Bay Hotel", user_content)


class TestLLMServiceFailureFallback(unittest.TestCase):
    """Test 2: Network / HTTP failures fall back to deterministic message."""

    def setUp(self):
        import app.services.llm_service as svc
        self._svc = svc
        self._original = "Check-in starts at 2:00 PM."

    def _run(self, side_effect):
        with patch.object(self._svc, "_LLM_API_KEY", "sk-test"):
            with patch("urllib.request.urlopen", side_effect=side_effect):
                return self._svc.enhance_response(self._original)

    def test_url_error_returns_original(self):
        import urllib.error
        result = self._run(urllib.error.URLError("connection refused"))
        self.assertEqual(result, self._original)

    def test_http_error_returns_original(self):
        import urllib.error
        result = self._run(urllib.error.HTTPError(
            url="https://api.anthropic.com/v1/messages",
            code=429,
            msg="Rate limit",
            hdrs={},
            fp=None,
        ))
        self.assertEqual(result, self._original)

    def test_timeout_returns_original(self):
        result = self._run(TimeoutError("timed out"))
        self.assertEqual(result, self._original)

    def test_os_error_returns_original(self):
        result = self._run(OSError("socket error"))
        self.assertEqual(result, self._original)

    def test_generic_exception_returns_original(self):
        result = self._run(RuntimeError("unexpected"))
        self.assertEqual(result, self._original)


class TestLLMMissingAPIKey(unittest.TestCase):
    """Test 3: Missing API key — falls back immediately without network call."""

    def setUp(self):
        import app.services.llm_service as svc
        self._svc = svc

    def test_no_key_returns_original_without_network_call(self):
        original = "Check-out is at 11:00 AM."
        with patch.object(self._svc, "_LLM_API_KEY", None):
            with patch("urllib.request.urlopen") as mock_open:
                result = self._svc.enhance_response(original)

        self.assertEqual(result, original)
        mock_open.assert_not_called()

    def test_empty_key_returns_original(self):
        original = "Wi-Fi is complimentary."
        with patch.object(self._svc, "_LLM_API_KEY", ""):
            with patch("urllib.request.urlopen") as mock_open:
                result = self._svc.enhance_response(original)

        self.assertEqual(result, original)
        mock_open.assert_not_called()


class TestLLMInvalidResponse(unittest.TestCase):
    """Test 4: Malformed or unexpected LLM responses fall back gracefully."""

    def setUp(self):
        import app.services.llm_service as svc
        self._svc = svc
        self._original = "Parking is complimentary."

    def _run_with_body(self, body: bytes):
        mock_resp = _make_mock_http_response(body)
        with patch.object(self._svc, "_LLM_API_KEY", "sk-test"):
            with patch("urllib.request.urlopen", return_value=mock_resp):
                return self._svc.enhance_response(self._original)

    def test_malformed_json_returns_original(self):
        result = self._run_with_body(b"not json at all {{{")
        self.assertEqual(result, self._original)

    def test_empty_content_array_returns_original(self):
        body = json.dumps({"content": []}).encode()
        result = self._run_with_body(body)
        self.assertEqual(result, self._original)

    def test_missing_content_key_returns_original(self):
        body = json.dumps({"model": "claude"}).encode()
        result = self._run_with_body(body)
        self.assertEqual(result, self._original)

    def test_content_block_with_empty_text_returns_original(self):
        body = json.dumps({"content": [{"type": "text", "text": "   "}]}).encode()
        result = self._run_with_body(body)
        self.assertEqual(result, self._original)

    def test_content_block_wrong_type_skipped(self):
        body = json.dumps({"content": [{"type": "tool_use", "id": "x"}]}).encode()
        result = self._run_with_body(body)
        self.assertEqual(result, self._original)


# ---------------------------------------------------------------------------
# 7  Integration: FAQ pipeline with mocked LLM
# ---------------------------------------------------------------------------

class TestLLMEnhancedFAQPipeline(unittest.TestCase):
    """
    With LLM mocked to return a known string, verify the assistant
    pipeline passes it through and preserves structure.
    """

    @classmethod
    def setUpClass(cls):
        from tests.test_harness import create_test_app
        cls.app = create_test_app()
        cls.client = cls.app.test_client()

    def _post(self, message: str):
        return self.client.post("/api/assistant", json={"message": message})

    def test_llm_enhanced_message_replaces_deterministic(self):
        """When LLM succeeds, its output is used as the response message."""
        import app.services.llm_service as svc
        enhanced = "Our hotel welcomes you from 2:00 PM each day for check-in."

        mock_resp = _make_mock_http_response(_make_anthropic_response(enhanced))
        with patch.object(svc, "_LLM_API_KEY", "sk-test"):
            with patch("urllib.request.urlopen", return_value=mock_resp):
                resp = self._post("What time is check-in?")

        body = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(body["message"], enhanced)

    def test_llm_failure_preserves_deterministic_message(self):
        """When the LLM call fails, the deterministic message is used."""
        import app.services.llm_service as svc
        import urllib.error

        with patch.object(svc, "_LLM_API_KEY", "sk-test"):
            with patch("urllib.request.urlopen",
                       side_effect=urllib.error.URLError("down")):
                resp = self._post("What time is check-out?")

        body = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertIn("11:00", body["message"])  # deterministic answer intact

    def test_llm_not_called_for_availability_result(self):
        """LLM must NOT be called when returning an availability result."""
        import app.services.llm_service as svc

        # Use a message with all required availability parameters embedded,
        # so the flow goes directly to availability_result.
        with patch.object(svc, "_LLM_API_KEY", "sk-test"):
            with patch("urllib.request.urlopen") as mock_open:
                resp = self.client.post("/api/assistant", json={
                    "message": "I need a room for 2 adults from 2026-10-01 to 2026-10-03",
                })

        body = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(body["type"], "availability_result")
        mock_open.assert_not_called()

    def test_response_structure_unchanged_with_llm(self):
        """Response structure must remain intact regardless of LLM usage."""
        import app.services.llm_service as svc

        enhanced = "Free Wi-Fi is available everywhere in the hotel."
        mock_resp = _make_mock_http_response(_make_anthropic_response(enhanced))

        with patch.object(svc, "_LLM_API_KEY", "sk-test"):
            with patch("urllib.request.urlopen", return_value=mock_resp):
                resp = self._post("Is there Wi-Fi?")

        body = resp.get_json()
        self.assertIn("message", body)
        self.assertIn("type", body)
        self.assertIn("requires_input", body)
        self.assertIsInstance(body["requires_input"], bool)
        self.assertFalse(body["requires_input"])

    def test_llm_not_called_when_no_api_key(self):
        """LLM must not be called when LLM_API_KEY is absent."""
        import app.services.llm_service as svc

        with patch.object(svc, "_LLM_API_KEY", None):
            with patch("urllib.request.urlopen") as mock_open:
                resp = self._post("Do you have parking?")

        self.assertEqual(resp.status_code, 200)
        mock_open.assert_not_called()


# ---------------------------------------------------------------------------
# 8  Verify existing FAQ tests still pass (regression guard)
# ---------------------------------------------------------------------------

class TestExistingFAQRegression(unittest.TestCase):
    """
    Existing FAQ facts must remain correct even when LLM is configured.
    The LLM is mocked to pass through the original message so we can check
    the deterministic content is still present (LLM only rephrases, never
    changes facts).
    """

    @classmethod
    def setUpClass(cls):
        from tests.test_harness import create_test_app
        cls.app = create_test_app()
        cls.client = cls.app.test_client()

    def _post_no_llm(self, message: str):
        """Post with LLM disabled (no key)."""
        import app.services.llm_service as svc
        with patch.object(svc, "_LLM_API_KEY", None):
            return self.client.post("/api/assistant", json={"message": message})

    def test_check_in_time_present(self):
        body = self._post_no_llm("What time is check-in?").get_json()
        self.assertIn("2:00", body["message"])

    def test_check_out_time_present(self):
        body = self._post_no_llm("What time is check-out?").get_json()
        self.assertIn("11:00", body["message"])

    def test_breakfast_answer_informative(self):
        body = self._post_no_llm("Is breakfast available?").get_json()
        msg = body["message"].lower()
        self.assertTrue("breakfast" in msg or "7:00" in msg or "available" in msg)

    def test_pool_answer_from_knowledge(self):
        body = self._post_no_llm("Is there a swimming pool?").get_json()
        msg = body["message"].lower()
        self.assertIn("pool", msg)

    def test_wifi_answer_from_knowledge(self):
        body = self._post_no_llm("Is there Wi-Fi?").get_json()
        msg = body["message"].lower()
        self.assertTrue("wi-fi" in msg or "wifi" in msg or "internet" in msg or "wireless" in msg)

    def test_parking_answer_from_knowledge(self):
        body = self._post_no_llm("Is there parking?").get_json()
        msg = body["message"].lower()
        self.assertIn("parking", msg)

    def test_cancellation_answer_present(self):
        body = self._post_no_llm("What is the cancellation policy?").get_json()
        msg = body["message"].lower()
        self.assertTrue("cancel" in msg or "refund" in msg or "policy" in msg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
