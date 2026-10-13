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

        # 6. Pure PIN-only login (no username provided)
        res_pin_only = client.post("/api/login", json={"pin": "8492"})
        self.assertEqual(res_pin_only.status_code, 200)
        self.assertEqual(res_pin_only.json().get("username"), "Adrian")

        res_pin_maciek = client.post("/api/login", json={"pin": "4729"})
        self.assertEqual(res_pin_maciek.status_code, 200)
        self.assertEqual(res_pin_maciek.json().get("username"), "Maciek")

        res_pin_karolina = client.post("/api/login", json={"pin": "6183"})
        self.assertEqual(res_pin_karolina.status_code, 200)
        self.assertEqual(res_pin_karolina.json().get("username"), "Karolina")

        res_pin_patrycja = client.post("/api/login", json={"pin": "9351"})
        self.assertEqual(res_pin_patrycja.status_code, 200)
        self.assertEqual(res_pin_patrycja.json().get("username"), "Patrycja")

        res_pin_monika = client.post("/api/login", json={"pin": "5274"})
        self.assertEqual(res_pin_monika.status_code, 200)
        self.assertEqual(res_pin_monika.json().get("username"), "Monika")

    def test_admin_lockdown_and_user_creation_with_profiles(self):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)

        # 1. Non-admin (Maciek) cannot access admin routes
        client.post("/api/login", json={"pin": "4729"})
        res_admin_users = client.get("/api/admin/users")
        self.assertEqual(res_admin_users.status_code, 403)
        res_gen_pin = client.get("/api/admin/generate-pin")
        self.assertEqual(res_gen_pin.status_code, 403)

        # 2. Admin (Adrian) can generate random unique PIN
        client.post("/api/login", json={"pin": "8492"})
        res_gen = client.get("/api/admin/generate-pin")
        self.assertEqual(res_gen.status_code, 200)
        gen_pin = res_gen.json().get("pin")
        self.assertTrue(gen_pin.isdigit() and len(gen_pin) == 4)

        # 3. Admin creates new user with custom persons for Wydatki
        res_create = client.post("/api/admin/users", json={
            "username": "Zofia",
            "pin": gen_pin,
            "permissions": {"wydatki": True, "fomo": False},
            "p1": "Zofia",
            "p2": "Kamil",
            "household": "PAIR_ZOFIA_KAMIL"
        })
        self.assertEqual(res_create.status_code, 200)
        created_data = res_create.json()
        self.assertEqual(created_data.get("username"), "Zofia")
        self.assertEqual(created_data.get("profile", {}).get("p1"), "Zofia")
        self.assertEqual(created_data.get("profile", {}).get("p2"), "Kamil")

        # 4. Zofia can log in with her generated PIN alone
        client_zofia = TestClient(app)
        res_zofia_login = client_zofia.post("/api/login", json={"pin": gen_pin})
        self.assertEqual(res_zofia_login.status_code, 200)
        self.assertEqual(res_zofia_login.json().get("username"), "Zofia")

        res_zofia_user = client_zofia.get("/api/user")
        self.assertEqual(res_zofia_user.status_code, 200)
        self.assertEqual(res_zofia_user.json().get("profile", {}).get("p1"), "Zofia")
        self.assertEqual(res_zofia_user.json().get("profile", {}).get("p2"), "Kamil")

        # 5. Clean up created user Zofia
        res_del = client.delete("/api/admin/users/Zofia")
        self.assertEqual(res_del.status_code, 200)

    def test_strict_crm_and_tasks_isolation(self):
        # Karolina and Patrycja have independent isolated tasks and CRM
        c_karo = user_data_mgr.add_user_crm_client("Karolina", {"name": "Klient Karoliny"})
        c_pat = user_data_mgr.add_user_crm_client("Patrycja", {"name": "Klient Patrycji"})

        crm_karo = user_data_mgr.get_user_crm("Karolina")
        crm_pat = user_data_mgr.get_user_crm("Patrycja")

        self.assertTrue(any(x.get("name") == "Klient Karoliny" for x in crm_karo))
        self.assertFalse(any(x.get("name") == "Klient Patrycji" for x in crm_karo))
        self.assertTrue(any(x.get("name") == "Klient Patrycji" for x in crm_pat))
        self.assertFalse(any(x.get("name") == "Klient Karoliny" for x in crm_pat))

        # Clean up
        user_data_mgr.delete_user_crm_client("Karolina", c_karo["id"])
        user_data_mgr.delete_user_crm_client("Patrycja", c_pat["id"])

    @classmethod
    def tearDownClass(cls):
        auth_manager.logout_all()

if __name__ == "__main__":
    unittest.main()
