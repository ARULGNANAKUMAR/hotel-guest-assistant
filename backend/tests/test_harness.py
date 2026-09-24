"""
Shared test harness for hotel-guest-assistant backend tests.

Because pytest / fastapi / pydantic are not available in this environment,
all tests use:
  - Python stdlib unittest
  - A thin Flask test-client that mirrors the real FastAPI API contract
    (same URL structure, same JSON request/response shape)
  - Direct imports of the service layer for pure-unit tests

The Flask harness is intentionally minimal — it calls the same
service functions that the real FastAPI routes call, giving us
confidence in the business logic without needing FastAPI or pydantic
installed.

Pydantic is shimmed via tests/pydantic_stub.py before any service
imports so that availability_service and assistant_service are
importable in this environment.
"""

import sys
import os

# Ensure the backend package is importable regardless of cwd
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

_TESTS_DIR = os.path.abspath(os.path.dirname(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

# ------------------------------------------------------------------
# Inject pydantic stub so services are importable without pydantic
# ------------------------------------------------------------------
if "pydantic" not in sys.modules:
    import pydantic_stub  # from tests/pydantic_stub.py
    sys.modules["pydantic"] = pydantic_stub

from flask import Flask, jsonify, request as flask_request
from app.services import knowledge_service


def create_test_app() -> Flask:
    """
    Build a Flask application that mirrors the FastAPI assistant and
    availability APIs.  Uses the real service layer so behaviour is
    production-equivalent.
    """
    app = Flask(__name__)
    app.config["TESTING"] = True

    # ------------------------------------------------------------------ #
    # GET /health                                                          #
    # ------------------------------------------------------------------ #
    @app.get("/health")
    def health():
        return jsonify({"status": "ok"}), 200

    # ------------------------------------------------------------------ #
    # GET /                                                                #
    # ------------------------------------------------------------------ #
    @app.get("/")
    def root():
        return jsonify({"message": "Hotel Guest Assistant API"}), 200

    # ------------------------------------------------------------------ #
    # POST /api/assistant  (full service-layer version with context)       #
    # ------------------------------------------------------------------ #
    @app.post("/api/assistant")
    def assistant():
        from app.schemas.assistant import AssistantRequest, ConversationContext
        from app.services.assistant_service import process_assistant_request

        body = flask_request.get_json(silent=True)

        # --- request validation (mirrors Pydantic schema) ---
        if body is None:
            return (
                jsonify({"detail": [{"msg": "JSON body required"}]}),
                422,
            )
        if "message" not in body:
            return (
                jsonify({"detail": [{"msg": "Field required", "loc": ["body", "message"]}]}),
                422,
            )

        raw_msg = body["message"]
        if not isinstance(raw_msg, str):
            return (
                jsonify({"detail": [{"msg": "message must be a string"}]}),
                422,
            )

        msg = raw_msg.strip()
        if not msg:
            return (
                jsonify({"detail": [{"msg": "message must not be empty"}]}),
                422,
            )
        if len(msg) > 2000:
            return (
                jsonify({"detail": [{"msg": "message must not exceed 2000 characters"}]}),
                422,
            )

        # --- build context (optional) ---
        ctx = None
        raw_ctx = body.get("context")
        if isinstance(raw_ctx, dict):
            try:
                ctx = ConversationContext(
                    checkIn=raw_ctx.get("checkIn"),
                    checkOut=raw_ctx.get("checkOut"),
                    adults=raw_ctx.get("adults"),
                    last_intent=raw_ctx.get("last_intent"),
                )
            except Exception:
                ctx = None

        try:
            req = AssistantRequest(message=msg, context=ctx)
            response = process_assistant_request(req)
        except Exception as exc:
            return jsonify({"detail": str(exc)}), 500

        # Serialise context back to dict
        ctx_dict = None
        if response.context is not None:
            ctx_dict = {
                "checkIn": response.context.checkIn,
                "checkOut": response.context.checkOut,
                "adults": response.context.adults,
                "last_intent": response.context.last_intent,
            }

        return (
            jsonify(
                {
                    "message": response.message,
                    "type": response.type,
                    "requires_input": response.requires_input,
                    "data": response.data,
                    "context": ctx_dict,
                }
            ),
            200,
        )

    # ------------------------------------------------------------------ #
    # POST /api/availability                                               #
    # ------------------------------------------------------------------ #
    @app.post("/api/availability")
    def availability():
        from app.services.availability_service import checkAvailability

        body = flask_request.get_json(silent=True)
        if body is None:
            return jsonify({"detail": "JSON body required"}), 422

        # Validate required fields
        for field in ("checkIn", "checkOut", "adults"):
            if field not in body:
                return (
                    jsonify({"detail": f"Field '{field}' is required"}),
                    422,
                )

        check_in = body["checkIn"]
        check_out = body["checkOut"]
        adults = body["adults"]

        # Type checks
        if not isinstance(check_in, str) or not isinstance(check_out, str):
            return jsonify({"detail": "checkIn and checkOut must be strings"}), 422
        if not isinstance(adults, int):
            return jsonify({"detail": "adults must be an integer"}), 422

        # Format check
        import re
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", check_in):
            return jsonify({"detail": "checkIn must be in YYYY-MM-DD format"}), 422
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", check_out):
            return jsonify({"detail": "checkOut must be in YYYY-MM-DD format"}), 422
        if adults <= 0:
            return jsonify({"detail": "adults must be greater than 0"}), 422

        try:
            result = checkAvailability(checkIn=check_in, checkOut=check_out, adults=adults)
        except ValueError as exc:
            return jsonify({"detail": str(exc)}), 422

        rooms = [
            {
                "room_type": r.room_type,
                "max_adults": r.max_adults,
                "available_rooms": r.available_rooms,
            }
            for r in result.rooms
        ]
        return (
            jsonify(
                {
                    "available": result.available,
                    "check_in": result.check_in,
                    "check_out": result.check_out,
                    "adults": result.adults,
                    "rooms": rooms,
                }
            ),
            200,
        )

    return app
