"""
Tests for the /health endpoint.

Verifies:
  - GET /health returns HTTP 200
  - Response body contains {"status": "ok"}
"""

import unittest
from tests.test_harness import create_test_app


class TestHealthEndpoint(unittest.TestCase):
    """Test the /health endpoint via the Flask test client."""

    @classmethod
    def setUpClass(cls):
        cls.app = create_test_app()
        cls.client = cls.app.test_client()

    def test_health_returns_200(self):
        """GET /health must return HTTP 200."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)

    def test_health_returns_ok_status(self):
        """GET /health body must contain status=ok."""
        response = self.client.get("/health")
        body = response.get_json()
        self.assertIsNotNone(body, "Response body must be valid JSON")
        self.assertIn("status", body, "Response must contain 'status' key")
        self.assertEqual(body["status"], "ok")

    def test_health_is_fast(self):
        """GET /health must respond without errors on repeated calls."""
        for _ in range(5):
            response = self.client.get("/health")
            self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
