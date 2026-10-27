"""Shared, crash-safe JSON persistence helpers.

Every data file of the app (users, sessions, budgets, quotes, CRM, tasks, ...)
is written through :func:`atomic_write_json`, so a crash, power loss or two
simultaneous requests can never leave a half-written (= corrupted) file.
"""
import copy
import json
import logging
import os
import threading
import time
from typing import Any, Optional

logger = logging.getLogger("Storage")

_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Where all user data lives. Override with FOMO_DATA_DIR to point at a persistent
# disk (e.g. a mounted volume in Docker / Render) or at a temp dir in tests.
DATA_DIR = os.environ.get("FOMO_DATA_DIR") or _APP_DIR
os.makedirs(DATA_DIR, exist_ok=True)

# One process-wide re-entrant lock: file writes are tiny, contention is negligible,
# and it keeps "read-modify-write" sequences consistent across request threads.
LOCK = threading.RLock()


def data_path(filename: str) -> str:
    return os.path.join(DATA_DIR, filename)


def atomic_write_text(path: str, text: str) -> None:
    """Write ``text`` to ``path`` atomically (temp file + fsync + os.replace)."""
    directory = os.path.dirname(path) or "."
    tmp_path = os.path.join(directory, f".{os.path.basename(path)}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def atomic_write_json(path: str, data: Any, indent: Optional[int] = 2) -> bool:
    """Serialise first (so a serialisation error never touches the old file), then write atomically."""
    try:
        payload = json.dumps(data, indent=indent, ensure_ascii=False)
        with LOCK:
            atomic_write_text(path, payload)
        return True
    except Exception as e:  # pragma: no cover - disk full / permissions
        logger.error(f"Error saving {path}: {e}")
        return False


def load_json_file(path: str, default: Any, validator=None) -> Any:
    """Load JSON from ``path``.

    * Missing file  -> write ``default`` and return a deep copy of it.
    * Corrupted file -> the broken file is kept as ``<name>.corrupt-<timestamp>`` (never silently
      overwritten, so data can still be recovered) and ``default`` is used.
    """
    with LOCK:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if validator is None or validator(data):
                    return data
                raise ValueError("unexpected JSON structure")
            except Exception as e:
                backup = f"{path}.corrupt-{int(time.time())}"
                try:
                    os.replace(path, backup)
                    logger.error(f"{path} was unreadable ({e}); kept a copy as {backup}")
                except OSError as move_err:  # pragma: no cover
                    logger.error(f"{path} was unreadable ({e}) and could not be backed up: {move_err}")
        fresh = copy.deepcopy(default)
        atomic_write_json(path, fresh)
        return fresh
