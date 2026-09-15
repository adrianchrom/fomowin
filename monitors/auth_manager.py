import os
import secrets
import json
import logging
from typing import Dict, Optional

logger = logging.getLogger("AuthManager")

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "CREDENTIALS.txt")
SESSIONS_FILE = os.path.join(BASE_DIR, "SESSIONS.json")

class AuthManager:
    def __init__(self):
        self.users: Dict[str, str] = {
            "Adrian": "admin",
            "Maciek": "maciek"
        }
        self.active_sessions: Dict[str, str] = {} # token -> username
        self.init_credentials()
        self.load_sessions()

    def init_credentials(self):
        """Load or create default passwords for Adrian and Maciek."""
        if os.path.exists(CREDENTIALS_FILE):
            try:
                with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
                    for line in f:
                        if ":" in line:
                            u, p = line.strip().split(":", 1)
                            if u.strip():
                                self.users[u.strip()] = p.strip()
            except Exception as e:
                logger.error(f"Error reading credentials file: {e}")

        # Ensure Adrian and Maciek have friendly defaults
        if "Adrian" not in self.users or not self.users["Adrian"]:
            self.users["Adrian"] = "admin"
        if "Maciek" not in self.users or not self.users["Maciek"]:
            self.users["Maciek"] = "maciek"

        try:
            with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
                for u, p in self.users.items():
                    f.write(f"{u}:{p}\n")
        except Exception as e:
            logger.error(f"Error writing credentials file: {e}")

    def load_sessions(self):
        """Load persistent sessions from SESSIONS.json."""
        if os.path.exists(SESSIONS_FILE):
            try:
                with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
                    self.active_sessions = json.load(f)
            except Exception as e:
                logger.error(f"Error loading sessions: {e}")
                self.active_sessions = {}

    def save_sessions(self):
        """Save active sessions to SESSIONS.json."""
        try:
            with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.active_sessions, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving sessions: {e}")

    def create_session(self, username: str) -> str:
        """Create a new session token for the given user."""
        canonical_user = "Adrian" if username.lower() == "adrian" else "Maciek"
        session_token = secrets.token_hex(24)
        self.active_sessions[session_token] = canonical_user
        self.save_sessions()
        return session_token

    def authenticate(self, username: str, password: str) -> Optional[tuple]:
        """Authenticate user credentials case-insensitively. Allow any login for Adrian or Maciek."""
        username_clean = username.strip()
        if not username_clean:
            return None

        user_lower = username_clean.lower()
        if user_lower in ["adrian", "maciek"]:
            canonical = "Adrian" if user_lower == "adrian" else "Maciek"
            token = self.create_session(canonical)
            return token, canonical

        # Fallback check against users dictionary
        for canonical_user, pass_val in self.users.items():
            if canonical_user.lower() == user_lower and (pass_val == password.strip() or not password.strip()):
                token = self.create_session(canonical_user)
                return token, canonical_user

        return None

    def verify_session(self, session_token: Optional[str]) -> Optional[str]:
        """Verify session token and return username if valid."""
        if not session_token:
            return None
        return self.active_sessions.get(session_token)

    def logout(self, session_token: Optional[str]):
        """Revoke a session token."""
        if session_token and session_token in self.active_sessions:
            del self.active_sessions[session_token]
            self.save_sessions()

auth_manager = AuthManager()
