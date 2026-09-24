"""
Test runner for hotel-guest-assistant backend core tests.

Run from the backend/ directory:

    python3 tests/run_tests.py

Or use the standard unittest discovery (equivalent):

    python3 -m unittest discover -s tests -p "test_*.py" -v

Note: pytest is the preferred runner when available. In environments
without pip access, this script and unittest discovery both work out
of the box with Python's stdlib.
"""

import sys
import os
import unittest

# Ensure the backend package root is on the path
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

if __name__ == "__main__":
    loader = unittest.TestLoader()
    tests_dir = os.path.dirname(__file__)
    suite = loader.discover(start_dir=tests_dir, pattern="test_*.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Exit with non-zero status if any tests failed
    sys.exit(0 if result.wasSuccessful() else 1)
