#!/usr/bin/env bash
# Run all tests: backend (Python unittest) + frontend (Node.js) + E2E (Playwright).
# Exit non-zero if any suite fails.

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
E2E="$ROOT/e2e"

echo "=================================================="
echo " Hotel Guest Assistant — Test Suite (Phase 7D-3A)"
echo "=================================================="

echo ""
echo "── Backend tests (Python unittest) ──"
cd "$BACKEND"
python3 tests/run_tests.py

echo ""
echo "── Frontend integration tests (Node.js) ──"
cd "$FRONTEND"
node tests/test_frontend_integration.mjs

echo ""
echo "── Browser E2E tests (Playwright / Chromium) ──"
cd "$ROOT"
PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 e2e/test_e2e_browser.py

echo ""
echo "=================================================="
echo " All test suites passed."
echo "=================================================="
