"""
test_e2e_browser.py — Real browser E2E tests for hotel-guest-assistant.

Phase 7D-3A: REAL browser → REAL static frontend → REAL HTTP → REAL Flask
             backend (real service layer) → REAL response → REAL UI update.

Framework: Python Playwright (playwright==1.56.0, pre-installed)
Browser:   Chromium headless (pre-installed at /opt/pw-browsers)

Architecture
------------
One pair of servers is started at module load (setUpModule) and torn down
at module exit (tearDownModule).  This avoids port-conflict failures that
occur when multiple test classes each try to bind the same ports.

Tests
-----
E2E-1  Chat interface loads (page title, header, input, send button)
E2E-2  Basic guest question — "What time is check-in?" travels through
       the real backend and the response appears in the UI.
E2E-3  Availability flow — multi-turn conversation:
         Turn 1: "I need a room for 2 adults." → backend asks for dates
         Turn 2: "2026-10-01 to 2026-10-03"   → backend returns rooms
       Verifies context is preserved across turns (not a new conversation).
E2E-4  Loading state — send button is disabled while request is in flight.
E2E-5  Backend-unavailable error — when the backend is down the frontend
       shows a friendly message without exposing stack traces / internals.

Run:
    cd hotel-guest-assistant-v7d3a
    python3 e2e/test_e2e_browser.py

Environment variable:
    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers  (set automatically below)
"""

import os
import sys
import time
import threading
import unittest

# Point Playwright at the pre-installed browser bundle
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")

# ── Path bootstrap ────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
_BACKEND_DIR = os.path.join(_PROJECT_ROOT, "backend")
_TESTS_DIR = os.path.join(_BACKEND_DIR, "tests")

for p in (_BACKEND_DIR, _TESTS_DIR, _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

# Inject pydantic stub before any service imports
if "pydantic" not in sys.modules:
    import pydantic_stub
    sys.modules["pydantic"] = pydantic_stub

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
import e2e_server

FRONTEND_URL = f"http://127.0.0.1:{e2e_server.FRONTEND_PORT}"

# ── Timeouts ──────────────────────────────────────────────────────────────────
RESPONSE_TIMEOUT_MS = 12_000
LOAD_TIMEOUT_MS = 8_000

# ── Module-level server + browser lifecycle ───────────────────────────────────
# One server pair and one browser shared across ALL test classes.
# This avoids port-bind failures when classes each try to start servers.

_pw = None
_browser = None


def setUpModule():
    global _pw, _browser
    e2e_server.start()
    _pw = sync_playwright().start()
    _browser = _pw.chromium.launch(headless=True)


def tearDownModule():
    global _pw, _browser
    if _browser:
        _browser.close()
        _browser = None
    if _pw:
        _pw.stop()
        _pw = None
    e2e_server.stop()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _count_assistant_messages(page):
    return page.locator(".message-bubble--assistant").count()


def _send_chat_message(page, text):
    textarea = page.locator("#chat-input")
    textarea.fill(text)
    page.locator("#send-btn").click()


def _wait_for_new_assistant_message(page, before_count, timeout_ms=RESPONSE_TIMEOUT_MS):
    page.wait_for_function(
        f"document.querySelectorAll('.message-bubble--assistant').length > {before_count}",
        timeout=timeout_ms,
    )


def _last_assistant_text(page):
    bubbles = page.locator(".message-bubble--assistant")
    return bubbles.last.inner_text()


# ── Base test class ───────────────────────────────────────────────────────────

class E2ETestBase(unittest.TestCase):
    """Each test gets a fresh browser context + page from the shared browser."""

    def setUp(self):
        self.context = _browser.new_context()
        self.page = self.context.new_page()

    def tearDown(self):
        self.page.close()
        self.context.close()


# ── E2E-1: Page loads ─────────────────────────────────────────────────────────

class TestPageLoads(E2ETestBase):

    def test_e2e_1_chat_interface_loads(self):
        """E2E-1: The chat UI renders with header, input, and send button."""
        self.page.goto(FRONTEND_URL, wait_until="domcontentloaded")

        self.assertEqual(self.page.title(), "Hotel Guest Assistant")

        header = self.page.locator(".chat-header")
        self.assertTrue(header.is_visible(), "Chat header must be visible")

        title_el = self.page.locator(".chat-header-title")
        self.assertTrue(title_el.is_visible())
        self.assertIn("Guest Services", title_el.inner_text())

        subtitle_el = self.page.locator(".chat-header-subtitle")
        self.assertTrue(subtitle_el.is_visible())
        self.assertIn("Azure Bay", subtitle_el.inner_text())

        textarea = self.page.locator("#chat-input")
        self.assertTrue(textarea.is_visible(), "Chat textarea must be visible")
        self.assertFalse(textarea.is_disabled(), "Textarea must not be disabled initially")

        send_btn = self.page.locator("#send-btn")
        self.assertTrue(send_btn.is_visible(), "Send button must be visible")

        self.page.wait_for_selector(".empty-state", timeout=LOAD_TIMEOUT_MS)
        empty = self.page.locator(".empty-state")
        self.assertTrue(empty.is_visible(), "Welcome/empty state must show on load")

        print("\n  ✓ E2E-1: Chat interface loads correctly")


# ── E2E-2: Basic guest question ───────────────────────────────────────────────

class TestBasicGuestQuestion(E2ETestBase):

    def test_e2e_2_check_in_question(self):
        """
        E2E-2: Real browser → frontend → backend → assistant service.

        "What time is check-in?" travels through the real HTTP stack.
        The response must contain the check-in time from hotel_data.json.
        """
        self.page.goto(FRONTEND_URL, wait_until="domcontentloaded")
        self.page.wait_for_selector("#chat-input", timeout=LOAD_TIMEOUT_MS)

        before = _count_assistant_messages(self.page)
        _send_chat_message(self.page, "What time is check-in?")

        self.page.wait_for_selector(".message-bubble--user", timeout=LOAD_TIMEOUT_MS)
        user_bubbles = self.page.locator(".message-bubble--user")
        self.assertGreater(user_bubbles.count(), 0)
        self.assertIn("What time is check-in?", user_bubbles.last.inner_text())

        _wait_for_new_assistant_message(self.page, before)
        reply = _last_assistant_text(self.page).lower()

        # hotel_data.json: check_in.time = "2:00 PM"
        self.assertTrue(
            "2:00" in reply or "2 pm" in reply or "14:00" in reply or "2pm" in reply,
            f"Reply must contain check-in time '2:00 PM'. Got: {reply!r}",
        )
        self.assertNotIn("traceback", reply)
        self.assertNotIn("file \"", reply)
        self.assertNotIn("exception", reply)

        print(f"\n  ✓ E2E-2: Check-in question answered. Reply: {reply[:80]!r}…")


# ── E2E-3: Availability multi-turn + context preservation ─────────────────────

class TestAvailabilityFlow(E2ETestBase):

    def test_e2e_3_availability_multi_turn(self):
        """
        E2E-3: Multi-turn availability flow with context preserved.

        Turn 1: "I need a room for 2 adults." → backend asks for dates
        Turn 2: "2026-10-01 to 2026-10-03"   → backend uses context from
                                               turn 1 (adults=2) and returns
                                               an availability result.

        Verifies 4 message bubbles total (2 user + 2 assistant) confirming
        the conversation was NOT restarted between turns.
        """
        self.page.goto(FRONTEND_URL, wait_until="domcontentloaded")
        self.page.wait_for_selector("#chat-input", timeout=LOAD_TIMEOUT_MS)

        # Turn 1
        before_1 = _count_assistant_messages(self.page)
        _send_chat_message(self.page, "I need a room for 2 adults.")
        _wait_for_new_assistant_message(self.page, before_1)

        reply_1 = _last_assistant_text(self.page).lower()
        self.assertTrue(
            "date" in reply_1 or "check-in" in reply_1 or "check in" in reply_1
            or "when" in reply_1 or "provide" in reply_1,
            f"Turn 1 reply should ask for dates. Got: {reply_1!r}",
        )

        print(f"\n  ✓ E2E-3 Turn 1: Backend asked for dates. Reply: {reply_1[:80]!r}…")

        # Turn 2
        before_2 = _count_assistant_messages(self.page)
        _send_chat_message(self.page, "2026-10-01 to 2026-10-03")
        _wait_for_new_assistant_message(self.page, before_2)

        reply_2 = _last_assistant_text(self.page).lower()
        self.assertTrue(
            "available" in reply_2 or "room" in reply_2
            or "deluxe" in reply_2 or "suite" in reply_2
            or "family" in reply_2 or "no rooms" in reply_2,
            f"Turn 2 reply should contain availability info. Got: {reply_2!r}",
        )

        page_text = self.page.content().lower()
        room_names = ["deluxe", "family", "suite"]
        found_room = any(name in page_text for name in room_names)
        no_rooms = "no rooms" in reply_2 or "not available" in reply_2

        self.assertTrue(
            found_room or no_rooms,
            f"Turn 2 must show backend-derived room info or no-rooms message.\n"
            f"Page text excerpt: {page_text[:400]!r}",
        )

        # Context preserved: 4 bubbles total
        user_count = self.page.locator(".message-bubble--user").count()
        asst_count = self.page.locator(".message-bubble--assistant").count()
        self.assertEqual(user_count, 2, "Should have 2 user messages")
        self.assertEqual(asst_count, 2, "Should have 2 assistant messages")

        print(f"  ✓ E2E-3 Turn 2: Availability result returned. Reply: {reply_2[:80]!r}…")
        if found_room:
            print(f"  ✓ E2E-3: Backend-derived room names found in UI")
        else:
            print(f"  ✓ E2E-3: Backend returned no-rooms result (also valid)")


# ── E2E-4: Loading state ──────────────────────────────────────────────────────

class TestLoadingState(E2ETestBase):

    def test_e2e_4_send_button_disabled_while_loading(self):
        """
        E2E-4: Send button and textarea are disabled while a request is in flight.

        Playwright route interception (registered BEFORE navigation, using **
        glob pattern) adds latency so there is a reliable window to observe
        the disabled state before the response arrives.
        """
        delay_applied = threading.Event()
        resume = threading.Event()

        def slow_route(route):
            delay_applied.set()
            resume.wait(timeout=3.0)
            route.continue_()

        # Register route BEFORE navigation (** glob required for full URL match)
        self.page.route("**/api/assistant", slow_route)
        self.page.goto(FRONTEND_URL, wait_until="domcontentloaded")
        self.page.wait_for_selector("#chat-input", timeout=LOAD_TIMEOUT_MS)

        _send_chat_message(self.page, "What time is check-in?")

        self.assertTrue(
            delay_applied.wait(timeout=5.0),
            "Route interception did not fire within 5 s",
        )

        send_btn = self.page.locator("#send-btn")
        self.assertTrue(
            send_btn.is_disabled(),
            "Send button must be disabled while backend request is in flight",
        )

        textarea = self.page.locator("#chat-input")
        self.assertTrue(
            textarea.is_disabled(),
            "Chat textarea must be disabled while backend request is in flight",
        )

        resume.set()
        self.page.unroute("**/api/assistant")

        _wait_for_new_assistant_message(self.page, 0)

        self.assertFalse(
            textarea.is_disabled(),
            "Chat textarea must be re-enabled after response arrives",
        )

        print("\n  ✓ E2E-4: Send button disabled during request, re-enabled after response")


# ── E2E-5: Backend unavailable error ─────────────────────────────────────────

class TestBackendUnavailableError(E2ETestBase):
    """
    E2E-5: Frontend shows a friendly error when the backend is unreachable.

    Playwright route abort (registered BEFORE navigation) simulates a network
    failure without stopping the shared backend server.
    """

    def test_e2e_5_friendly_error_when_backend_down(self):
        # Register abort BEFORE navigation
        self.page.route("**/api/assistant", lambda route: route.abort("failed"))
        self.page.goto(FRONTEND_URL, wait_until="domcontentloaded")
        self.page.wait_for_selector("#chat-input", timeout=LOAD_TIMEOUT_MS)

        before = _count_assistant_messages(self.page)
        _send_chat_message(self.page, "What time is check-in?")

        _wait_for_new_assistant_message(self.page, before, timeout_ms=RESPONSE_TIMEOUT_MS)

        error_bubbles = self.page.locator(".message-bubble--error")
        self.assertGreater(
            error_bubbles.count(), 0,
            "An error message bubble must appear when the backend is unavailable",
        )

        error_text = error_bubbles.last.inner_text().lower()

        self.assertTrue(
            "unable" in error_text or "trouble" in error_text
            or "connection" in error_text or "try again" in error_text
            or "something went wrong" in error_text,
            f"Error message must be friendly. Got: {error_text!r}",
        )

        self.assertNotIn("traceback", error_text)
        self.assertNotIn("file \"", error_text)
        self.assertNotIn("econnrefused", error_text)
        self.assertNotIn("api_key", error_text)
        self.assertNotIn("llm_api_key", error_text)
        self.assertLess(len(error_text), 300, "Error message must be short, not a dump")

        self.page.unroute("**/api/assistant")

        print(f"\n  ✓ E2E-5: Friendly error shown when backend unreachable: {error_text[:80]!r}…")


# ── Runner ────────────────────────────────────────────────────────────────────

def run_e2e_tests():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    for cls in [
        TestPageLoads,
        TestBasicGuestQuestion,
        TestAvailabilityFlow,
        TestLoadingState,
        TestBackendUnavailableError,
    ]:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    print("=" * 60)
    print(" Hotel Guest Assistant — Browser E2E Tests (Phase 7D-3A)")
    print("=" * 60)
    ok = run_e2e_tests()
    sys.exit(0 if ok else 1)
