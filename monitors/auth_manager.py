import os
import secrets
import string
import logging
from typing import Dict, Optional

logger = logging.getLogger("AuthManager")

CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "CREDENTIALS.txt")

class AuthManager:
    def __init__(self):
        self.users: Dict[str, str] = {}
        self.active_sessions: Dict[str, str] = {} # token -> username
        self.init_credentials()

    def init_credentials(self):
        """Load or generate random passwords for Adrian and Maciek."""
        users = {}
        if os.path.exists(CREDENTIALS_FILE):
            try:
                with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
                    for line in f:
                        if ":" in line:
                            u, p = line.strip().split(":", 1)
                            users[u.strip()] = p.strip()
            except Exception as e:
                logger.error(f"Error reading credentials file: {e}")

        # Ensure Adrian and Maciek exist
        alphabet = string.ascii_letters + string.digits
        updated = False

        if "Adrian" not in users or len(users["Adrian"]) < 4:
            users["Adrian"] = "Adr_" + ''.join(secrets.choice(alphabet) for _ in range(8))
            updated = True

        if "Maciek" not in users or len(users["Maciek"]) < 4:
            users["Maciek"] = "Mac_" + ''.join(secrets.choice(alphabet) for _ in range(8))
            updated = True

        self.users = users

        if updated or not os.path.exists(CREDENTIALS_FILE):
            try:
                with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
                    for u, p in users.items():
                        f.write(f"{u}:{p}\n")
            except Exception as e:
                logger.error(f"Error writing credentials file: {e}")

    def authenticate(self, username: str, password: str) -> Optional[str]:
        """Authenticate user credentials and return a new session token if valid."""
        username_clean = username.strip()
        if username_clean in self.users and self.users[username_clean] == password.strip():
            session_token = secrets.token_hex(24)
            self.active_sessions[session_token] = username_clean
            return session_token
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

auth_manager = AuthManager()
