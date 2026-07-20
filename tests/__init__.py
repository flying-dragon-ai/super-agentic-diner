"""Test package bootstrap compatibility.

``unittest discover -s tests`` imports ``_test_env`` from the tests directory,
while ``python -m unittest tests.test_x`` imports this package first.  Register
the same module under the top-level name so both entry styles share one safety
bootstrap and one temporary database.
"""
from __future__ import annotations

import sys

if "_test_env" in sys.modules:
    _test_env = sys.modules["_test_env"]
    sys.modules.setdefault(f"{__name__}._test_env", _test_env)
else:
    from . import _test_env

    sys.modules.setdefault("_test_env", _test_env)
