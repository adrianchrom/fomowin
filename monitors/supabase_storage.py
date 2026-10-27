"""Supabase Cloud PostgreSQL storage integration.

Provides transparent cloud persistence across ephemeral server restarts
(e.g. Render free tier restarts) using Supabase's built-in REST API (PostgREST).
"""
import concurrent.futures
import json
import logging
import os
from typing import Any, Optional, Dict
import requests

logger = logging.getLogger("SupabaseStorage")

# Background thread pool for non-blocking asynchronous cloud writes
_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="SupabaseWorker")


class SupabaseStorage:
    def __init__(self):
        self.url: str = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
        self.key: str = (
            os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            or os.environ.get("SUPABASE_SERVICE_KEY")
            or os.environ.get("SUPABASE_KEY")
            or os.environ.get("SUPABASE_ANON_KEY")
            or ""
        ).strip()
        self.table: str = (os.environ.get("SUPABASE_TABLE") or "app_storage").strip()

    def reload_config(self) -> None:
        """Reload configuration from environment variables."""
        self.url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
        self.key = (
            os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            or os.environ.get("SUPABASE_SERVICE_KEY")
            or os.environ.get("SUPABASE_KEY")
            or os.environ.get("SUPABASE_ANON_KEY")
            or ""
        ).strip()
        self.table = (os.environ.get("SUPABASE_TABLE") or "app_storage").strip()

    def is_enabled(self) -> bool:
        """Check whether Supabase cloud storage is configured."""
        return bool(self.url and self.key)

    def _get_headers(self) -> Dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        }

    def fetch_key(self, key: str) -> Optional[Any]:
        """Fetch data for a given key from Supabase app_storage table."""
        if not self.is_enabled():
            return None
        try:
            endpoint = f"{self.url}/rest/v1/{self.table}?key=eq.{key}&select=data"
            resp = requests.get(endpoint, headers=self._get_headers(), timeout=4)
            if resp.status_code == 200:
                rows = resp.json()
                if isinstance(rows, list) and len(rows) > 0:
                    return rows[0].get("data")
            elif resp.status_code != 404:
                logger.warning(f"Supabase fetch_key('{key}') returned status {resp.status_code}: {resp.text[:120]}")
        except Exception as e:
            logger.warning(f"Supabase fetch_key('{key}') error: {e}")
        return None

    def save_key(self, key: str, data: Any) -> bool:
        """Save/upsert data for a given key to Supabase app_storage table."""
        if not self.is_enabled():
            return False
        try:
            endpoint = f"{self.url}/rest/v1/{self.table}"
            headers = self._get_headers()
            headers["Prefer"] = "resolution=merge-duplicates"
            payload = {
                "key": key,
                "data": data
            }
            resp = requests.post(endpoint, headers=headers, json=payload, timeout=5)
            if resp.status_code in (200, 201, 204):
                return True
            logger.warning(f"Supabase save_key('{key}') returned status {resp.status_code}: {resp.text[:120]}")
            return False
        except Exception as e:
            logger.warning(f"Supabase save_key('{key}') error: {e}")
            return False

    def async_save_key(self, key: str, data: Any) -> None:
        """Non-blocking background push to Supabase."""
        if not self.is_enabled():
            return
        try:
            _EXECUTOR.submit(self.save_key, key, data)
        except Exception as e:
            logger.warning(f"Failed to submit Supabase background save for '{key}': {e}")

    def list_cloud_keys(self) -> list:
        """List all stored keys in Supabase app_storage."""
        if not self.is_enabled():
            return []
        try:
            endpoint = f"{self.url}/rest/v1/{self.table}?select=key,updated_at"
            resp = requests.get(endpoint, headers=self._get_headers(), timeout=5)
            if resp.status_code == 200:
                rows = resp.json()
                if isinstance(rows, list):
                    return [r.get("key") for r in rows if isinstance(r, dict) and r.get("key")]
        except Exception as e:
            logger.warning(f"Supabase list_cloud_keys error: {e}")
        return []


supabase_storage = SupabaseStorage()
