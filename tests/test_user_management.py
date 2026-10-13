import unittest
from monitors.auth_manager import auth_manager
from monitors.user_data_manager import user_data_mgr

class TestUserManagementAndMonika(unittest.TestCase):
    def test_monika_pin_authentication(self):
        # Authenticate Monika with PIN 5274
        res = auth_manager.authenticate_pin("5274")
        self.assertIsNotNone(res)
        token, user = res
        self.assertEqual(user, "Monika")

    def test_monika_permissions_isolated_to_wydatki(self):
        perms = user_data_mgr.get_user_permissions("Monika")
        self.assertTrue(perms.get("wydatki"))
        self.assertFalse(perms.get("is_admin"))
        self.assertFalse(perms.get("fomo"))
        self.assertFalse(perms.get("wyceny"))
        self.assertFalse(perms.get("crm"))
        self.assertFalse(perms.get("tasks"))
        self.assertFalse(perms.get("kalendarz"))

    def test_monika_and_tomek_shared_pair_wydatki(self):
        self.assertEqual(user_data_mgr.resolve_wydatki_user("Monika"), "PAIR_MONIKA_TOMEK")
        self.assertEqual(user_data_mgr.resolve_wydatki_user("Tomek"), "PAIR_MONIKA_TOMEK")
        self.assertEqual(user_data_mgr.resolve_wydatki_user("Adrian"), "PAIR_ADRIAN_PATRYCJA")
        self.assertEqual(user_data_mgr.resolve_wydatki_user("Patrycja"), "PAIR_ADRIAN_PATRYCJA")
        self.assertEqual(user_data_mgr.resolve_wydatki_user("Maciek"), "PAIR_MACIEK_KAROLINA")
        self.assertEqual(user_data_mgr.resolve_wydatki_user("Karolina"), "PAIR_MACIEK_KAROLINA")

    def test_user_creation_and_deletion(self):
        # Create temporary user
        username = auth_manager.add_or_update_user("TestUser", "7788")
        self.assertEqual(username, "TestUser")
        
        # Verify authentication
        res = auth_manager.authenticate_pin("7788")
        self.assertIsNotNone(res)
        self.assertEqual(res[1], "TestUser")

        # Set permissions
        user_data_mgr.update_user_permissions("TestUser", {"wydatki": True, "wyceny": True, "fomo": False})
        perms = user_data_mgr.get_user_permissions("TestUser")
        self.assertTrue(perms["wydatki"])
        self.assertTrue(perms["wyceny"])
        self.assertFalse(perms["fomo"])

        # Delete user
        deleted = auth_manager.delete_user("TestUser")
        self.assertTrue(deleted)
        user_data_mgr.delete_user_permissions("TestUser")

        # Verify no longer authenticates
        res_after = auth_manager.authenticate_pin("7788")
        self.assertIsNone(res_after)

    def test_all_credential_pins(self):
        # Adrian: 8492
        self.assertEqual(auth_manager.authenticate_pin("8492")[1], "Adrian")
        # Maciek: 4729
        self.assertEqual(auth_manager.authenticate_pin("4729")[1], "Maciek")
        # Karolina: 6183
        self.assertEqual(auth_manager.authenticate_pin("6183")[1], "Karolina")
        # Patrycja: 9351
        self.assertEqual(auth_manager.authenticate_pin("9351")[1], "Patrycja")
        # Monika: 5274
        self.assertEqual(auth_manager.authenticate_pin("5274")[1], "Monika")

    def test_authenticate_user_pin_strict(self):
        # Correct user and PIN
        self.assertIsNotNone(auth_manager.authenticate_user_pin("Adrian", "8492"))
        self.assertIsNotNone(auth_manager.authenticate_user_pin("Maciek", "4729"))
        self.assertIsNotNone(auth_manager.authenticate_user_pin("Monika", "5274"))
        self.assertIsNotNone(auth_manager.authenticate_user_pin("Karolina", "6183"))
        self.assertIsNotNone(auth_manager.authenticate_user_pin("Patrycja", "9351"))

        # Case-insensitive username
        self.assertIsNotNone(auth_manager.authenticate_user_pin("adrian", "8492"))
        self.assertIsNotNone(auth_manager.authenticate_user_pin("MONIKA", "5274"))

        # Wrong PIN for user
        self.assertIsNone(auth_manager.authenticate_user_pin("Adrian", "4729"))
        self.assertIsNone(auth_manager.authenticate_user_pin("Maciek", "8492"))
        self.assertIsNone(auth_manager.authenticate_user_pin("Monika", "0000"))

        # Non-existent user
        self.assertIsNone(auth_manager.authenticate_user_pin("UnknownUser", "1234"))

    def test_logout_all(self):
        token1, u1 = auth_manager.authenticate_user_pin("Adrian", "8492")
        token2, u2 = auth_manager.authenticate_user_pin("Monika", "5274")
        self.assertIn(token1, auth_manager.active_sessions)
        self.assertIn(token2, auth_manager.active_sessions)

        auth_manager.logout_all()
        self.assertEqual(len(auth_manager.active_sessions), 0)
        self.assertIsNone(auth_manager.verify_session(token1))
        self.assertIsNone(auth_manager.verify_session(token2))

    def test_api_login_endpoint(self):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)

        # 1. Unauthenticated request to /api/user should return 401
        res = client.get("/api/user")
        self.assertEqual(res.status_code, 401)

        # 2. Login with valid username and PIN
        res_login = client.post("/api/login", json={"username": "Monika", "pin": "5274"})
        self.assertEqual(res_login.status_code, 200)
        data = res_login.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("username"), "Monika")

        # 3. Request /api/user using the received session cookie
        res_user = client.get("/api/user")
        self.assertEqual(res_user.status_code, 200)
        user_data = res_user.json()
        self.assertTrue(user_data.get("authenticated"))
        self.assertEqual(user_data.get("username"), "Monika")

        # 4. Bad PIN should fail with 401
        res_bad = client.post("/api/login", json={"username": "Monika", "pin": "9999"})
        self.assertEqual(res_bad.status_code, 401)

        # 5. Missing username or pin should fail with 400
        res_missing = client.post("/api/login", json={"username": "", "pin": "5274"})
        self.assertEqual(res_missing.status_code, 400)

    @classmethod
    def tearDownClass(cls):
        auth_manager.logout_all()

if __name__ == "__main__":
    unittest.main()
