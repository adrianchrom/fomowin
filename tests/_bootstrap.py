"""Test isolation: every test run uses a throw-away data directory.

Without this the tests wrote their fixtures (test clients, tasks, expenses, sessions) into the real
user data files. Import this module FIRST in every test file.
"""
import atexit
import os
import shutil
import sys
import tempfile

_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

if not os.environ.get("FOMO_DATA_DIR"):
    _tmp = tempfile.mkdtemp(prefix="fomo_test_data_")
    os.environ["FOMO_DATA_DIR"] = _tmp
    atexit.register(shutil.rmtree, _tmp, ignore_errors=True)
