"""
conftest.py — pytest configuration for hotel-guest-assistant backend tests.

Provides the `client` fixture backed by the REAL FastAPI application.

When FastAPI and httpx are available (production CI):
    Uses fastapi.testclient.TestClient against app.main:app

When running in a restricted environment without FastAPI/pytest installed,
the test_compat module provides a drop-in TestClient that wraps the Flask
harness (which calls the same service layer), allowing the test suite to
be executed with `python -m unittest` while keeping identical test logic.
"""

import sys
import os

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

try:
    import pytest
    import fastapi
    import httpx
    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False

if _FASTAPI_AVAILABLE:
    import pytest
    from fastapi.testclient import TestClient
    from app.main import app

    @pytest.fixture(scope="session")
    def client():
        """Real FastAPI TestClient — used in all pytest runs."""
        with TestClient(app) as c:
            yield c
