import os
import secrets
import json
import logging
from typing import Dict, Optional

logger = logging.getLogger("AuthManager")

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "CREDENTIALS.txt")
SESSIONS_FILE = os.path.join(BASE_DIR, "SESSIONS.json")

PIN_MAP = {
    "8492": "Adrian",
    "4729": "Maciek",
    "6183": "Karolina",
    "9351": "Patrycja"
}

USER_NAMES = {
    "adrian": "Adrian",
    "maciek": "Maciek",
    "karolina": "Karolina",
    "patrycja": "Patrycja"
}

class AuthManager:
    def __init__(self):
        self.users: Dict[str, str] = {
            "Adrian": "8492",
            "Maciek": "4729",
            "Karolina": "6183",
            "Patrycja": "9351"
        }
        self.active_sessions: Dict[str, str] = {} # token -> username
        self.init_credentials()
        self.load_sessions()

    def init_credentials(self):
        """Load or create default PINs for Adrian, Maciek, Karolina, and Patrycja."""
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

        # Ensure default PINs exist
        defaults = {
            "Adrian": "8492",
            "Maciek": "4729",
            "Karolina": "6183",
            "Patrycja": "9351"
        }
        for u, p in defaults.items():
            if u not in self.users or not self.users[u]:
                self.users[u] = p

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

    def get_canonical_user(self, username: str) -> str:
        u_lower = (username or "").strip().lower()
        return USER_NAMES.get(u_lower, "Maciek")

    def create_session(self, username: str) -> str:
        """Create a new session token for the given user."""
        canonical_user = self.get_canonical_user(username)
        session_token = secrets.token_hex(24)
        self.active_sessions[session_token] = canonical_user
        self.save_sessions()
        return session_token

    def authenticate_pin(self, pin: str, target_user: Optional[str] = None) -> Optional[tuple]:
        """Authenticate user strictly by 4-digit PIN."""
        clean_pin = (pin or "").strip()
        if not clean_pin:
            return None

        # Check PIN_MAP first
        if clean_pin in PIN_MAP:
            matched_user = PIN_MAP[clean_pin]
            token = self.create_session(matched_user)
            return token, matched_user

        # Fallback check against users dictionary values
        for user_name, user_pin in self.users.items():
            if user_pin == clean_pin:
                canonical = self.get_canonical_user(user_name)
                token = self.create_session(canonical)
                return token, canonical

        return None

    def authenticate(self, username: str, password: str) -> Optional[tuple]:
        """Authenticate user strictly by valid PIN or valid user PIN."""
        clean_pass = (password or "").strip()
        clean_user = (username or "").strip()

        if clean_pass in PIN_MAP:
            return self.authenticate_pin(clean_pass)

        if clean_user in PIN_MAP:
            return self.authenticate_pin(clean_user)

        # Strict check against users dictionary
        for canonical_user, user_pin in self.users.items():
            if (canonical_user.lower() == clean_user.lower() or canonical_user.lower() == clean_pass.lower()) and (clean_pass == user_pin or clean_user == user_pin):
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
