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

if __name__ == "__main__":
    unittest.main()
