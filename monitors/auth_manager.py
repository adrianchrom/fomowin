import os
import secrets
import json
import logging
from typing import Dict, Optional

logger = logging.getLogger("AuthManager")

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "CREDENTIALS.txt")
SESSIONS_FILE = os.path.join(BASE_DIR, "SESSIONS.json")

DEFAULT_USERS = {
    "Adrian": "8492",
    "Maciek": "4729",
    "Karolina": "6183",
    "Patrycja": "9351",
    "Monika": "5274"
}

PIN_MAP = dict(DEFAULT_USERS)
USER_NAMES = {k.lower(): k for k in DEFAULT_USERS.keys()}

class AuthManager:
    def __init__(self):
        self.users: Dict[str, str] = dict(DEFAULT_USERS)
        self.active_sessions: Dict[str, str] = {} # token -> username
        self.init_credentials()
        self.load_sessions()

    def sync_mappings(self):
        """Keep PIN_MAP and USER_NAMES synchronized with self.users."""
        global PIN_MAP, USER_NAMES
        PIN_MAP.clear()
        USER_NAMES.clear()
        for u, p in self.users.items():
            PIN_MAP[str(p).strip()] = u
            USER_NAMES[u.lower()] = u

    def init_credentials(self):
        """Load or create default PINs for all users."""
        if os.path.exists(CREDENTIALS_FILE):
            try:
                with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
                    for line in f:
                        if ":" in line:
                            u, p = line.strip().split(":", 1)
                            clean_u = u.strip()
                            clean_p = p.strip()
                            if clean_u:
                                # If legacy alpha password in default users, migrate to canonical 4-digit PIN
                                if clean_u in DEFAULT_USERS and not clean_p.isdigit():
                                    clean_p = DEFAULT_USERS[clean_u]
                                self.users[clean_u] = clean_p
            except Exception as e:
                logger.error(f"Error reading credentials file: {e}")

        # Ensure default PINs exist
        for u, p in DEFAULT_USERS.items():
            if u not in self.users or not self.users[u] or not str(self.users[u]).isdigit():
                self.users[u] = p

        self.sync_mappings()
        self.save_credentials()

    def save_credentials(self):
        """Write current users and PINs to CREDENTIALS.txt."""
        try:
            with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
                for u, p in self.users.items():
                    f.write(f"{u}:{p}\n")
        except Exception as e:
            logger.error(f"Error writing credentials file: {e}")

    def add_or_update_user(self, username: str, pin: str) -> str:
        """Add a new user or update existing user's PIN."""
        clean_name = (username or "").strip()
        if clean_name and clean_name[0].islower():
            clean_name = clean_name[0].upper() + clean_name[1:]
        clean_pin = (pin or "").strip()
        if not clean_name:
            raise ValueError("Nazwa użytkownika nie może być pusta.")
        if not clean_pin or len(clean_pin) < 3:
            raise ValueError("Kod PIN musi mieć co najmniej 4 cyfry.")

        for k in list(self.users.keys()):
            if k.lower() == clean_name.lower():
                del self.users[k]

        self.users[clean_name] = clean_pin
        self.sync_mappings()
        self.save_credentials()
        return clean_name

    def delete_user(self, username: str) -> bool:
        """Delete user account (protecting Adrian)."""
        clean_name = (username or "").strip().lower()
        if clean_name == "adrian":
            return False  # Protect superadmin

        target_key = None
        for k in list(self.users.keys()):
            if k.lower() == clean_name:
                target_key = k
                break

        if target_key:
            del self.users[target_key]
            self.sync_mappings()
            self.save_credentials()
            return True
        return False

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
        u_clean = (username or "").strip()
        u_lower = u_clean.lower()
        for uname in self.users.keys():
            if uname.lower() == u_lower:
                return uname
        if u_lower in USER_NAMES:
            return USER_NAMES[u_lower]
        return u_clean.capitalize() if u_clean else "Maciek"

    def create_session(self, username: str) -> str:
        """Create a new session token for the given user."""
        canonical_user = self.get_canonical_user(username)
        session_token = secrets.token_hex(24)
        self.active_sessions[session_token] = canonical_user
        self.save_sessions()
        return session_token

    def authenticate_pin(self, pin: str, target_user: Optional[str] = None) -> Optional[tuple]:
        """Authenticate user strictly by PIN."""
        clean_pin = (pin or "").strip()
        if not clean_pin:
            return None

        # Check in self.users values
        for user_name, user_pin in self.users.items():
            if str(user_pin).strip() == clean_pin:
                canonical = self.get_canonical_user(user_name)
                token = self.create_session(canonical)
                return token, canonical

        # Check PIN_MAP
        if clean_pin in PIN_MAP:
            matched_user = self.get_canonical_user(PIN_MAP[clean_pin])
            token = self.create_session(matched_user)
            return token, matched_user

        return None

    def authenticate(self, username: str, password: str) -> Optional[tuple]:
        """Authenticate user strictly by valid PIN or valid user PIN."""
        clean_pass = (password or "").strip()
        clean_user = (username or "").strip()

        if clean_pass in PIN_MAP or any(str(p).strip() == clean_pass for p in self.users.values()):
            return self.authenticate_pin(clean_pass)

        if clean_user in PIN_MAP or any(str(p).strip() == clean_user for p in self.users.values()):
            return self.authenticate_pin(clean_user)

        # Strict check against users dictionary
        for canonical_user, user_pin in self.users.items():
            if (canonical_user.lower() == clean_user.lower() or canonical_user.lower() == clean_pass.lower()) and (clean_pass == str(user_pin) or clean_user == str(user_pin)):
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
