import unittest
from monitors.risk_analysis_engine import risk_engine
from monitors.alerts_manager import alerts_manager

class TestNewFeatures(unittest.TestCase):
    def test_url_parsing_fomo_family(self):
        url = "https://fomo.family/tokens/robinhood/0x58ffac95f78d15cecddb91056c8f79f704144e34"
        parsed = risk_engine.parse_ca_or_url(url)
        self.assertTrue(parsed["valid"])
        self.assertEqual(parsed["ca"], "0x58ffac95f78d15cecddb91056c8f79f704144e34")
        self.assertEqual(parsed["chain"], "robinhood")

    def test_direct_ca_parsing(self):
        ca = "0x58ffac95f78d15cecddb91056c8f79f704144e34"
        parsed = risk_engine.parse_ca_or_url(ca)
        self.assertTrue(parsed["valid"])
        self.assertEqual(parsed["ca"], ca)

    def test_4stocks_false_positive_fix(self):
        """Verify that 4stocks token is classified as SAFE CONTRACT and not false-positive honeypot."""
        scan = risk_engine.scan_token_ca("4stocks")
        self.assertTrue(scan["valid"])
        self.assertFalse(scan["security"]["is_honeypot"])
        self.assertEqual(scan["security"]["status_text"], "SAFE CONTRACT")

    def test_insider_handle_parsing(self):
        # X URL
        parsed_x = risk_engine.parse_insider_input("https://x.com/smartmoney_trader")
        self.assertIsNotNone(parsed_x)
        self.assertEqual(parsed_x["handle"], "@smartmoney_trader")

        # fomo.family profile URL
        parsed_fomo = risk_engine.parse_insider_input("https://fomo.family/profile/alpha_caller")
        self.assertIsNotNone(parsed_fomo)
        self.assertEqual(parsed_fomo["handle"], "@alpha_caller")

        # Raw handle
        parsed_raw = risk_engine.parse_insider_input("@whale_god")
        self.assertIsNotNone(parsed_raw)
        self.assertEqual(parsed_raw["handle"], "@whale_god")

    def test_tracked_insiders_management(self):
        ins = risk_engine.add_tracked_insider("https://x.com/new_insider_test")
        self.assertIsNotNone(ins)
        self.assertEqual(ins["handle"], "@new_insider_test")

        removed = risk_engine.remove_tracked_insider("@new_insider_test")
        self.assertTrue(removed)

    def test_insider_signals_feed(self):
        feed = risk_engine.get_insider_signals_feed()
        self.assertGreater(len(feed), 0)
        item = feed[0]
        self.assertIn("insider", item)
        self.assertIn("handle", item["insider"])
        self.assertIn("security", item)
        self.assertIn("statusText", item["security"])
        self.assertIn("marketCapUsd", item)
        self.assertIn("holdersCount", item)

    def test_alerts_manager(self):
        added = alerts_manager.add_alert(
            token_name="TestToken",
            ticker="TEST",
            ca="0x1234567890123456789012345678901234567890",
            alert_type="BUY_UNDER",
            target_mcap_usd=50000.0
        )
        self.assertIn("id", added)
        removed = alerts_manager.remove_alert(added["id"])
        self.assertTrue(removed)

    def test_user_permissions(self):
        from monitors.user_data_manager import user_data_mgr
        adrian_perms = user_data_mgr.get_user_permissions("Adrian")
        self.assertTrue(adrian_perms["is_admin"])
        self.assertTrue(adrian_perms["wydatki"])
        self.assertTrue(adrian_perms["wyceny"])

        maciek_perms = user_data_mgr.get_user_permissions("Maciek")
        self.assertFalse(maciek_perms["is_admin"])
        self.assertTrue(maciek_perms["fomo"])

        # Update Maciek's permissions
        updated = user_data_mgr.update_maciek_permissions({"wydatki": True, "wyceny": True})
        self.assertTrue(updated["wydatki"])
        self.assertTrue(updated["wyceny"])

    def test_data_privacy_isolation(self):
        from monitors.user_data_manager import user_data_mgr
        # Add Adrian entry
        adrian_entry = user_data_mgr.add_user_wydatki("Adrian", {
            "type": "PRZYCHÓD", "title": "Secret Adrian Income", "amount_pln": 50000.0
        })
        # Add Maciek entry
        maciek_entry = user_data_mgr.add_user_wydatki("Maciek", {
            "type": "PRZYCHÓD", "title": "Secret Maciek Income", "amount_pln": 10000.0
        })

        adrian_data = user_data_mgr.get_user_wydatki("Adrian")
        maciek_data = user_data_mgr.get_user_wydatki("Maciek")
        adrian_items = adrian_data.get("expenses", []) if isinstance(adrian_data, dict) else adrian_data
        maciek_items = maciek_data.get("expenses", []) if isinstance(maciek_data, dict) else maciek_data

        self.assertTrue(any(x["title"] == "Secret Adrian Income" for x in adrian_items))
        self.assertFalse(any(x["title"] == "Secret Maciek Income" for x in adrian_items))

        self.assertTrue(any(x["title"] == "Secret Maciek Income" for x in maciek_items))
        self.assertFalse(any(x["title"] == "Secret Adrian Income" for x in maciek_items))

        # Cleanup
        user_data_mgr.delete_user_wydatki("Adrian", adrian_entry["id"])
        user_data_mgr.delete_user_wydatki("Maciek", maciek_entry["id"])

    def test_kalendarz_isolation(self):
        from monitors.user_data_manager import user_data_mgr
        ev1 = user_data_mgr.add_user_kalendarz_event("Adrian", {
            "title": "Spotkanie Adrian", "date": "2026-10-01", "priority": "HIGH"
        })
        ev2 = user_data_mgr.add_user_kalendarz_event("Maciek", {
            "title": "Spotkanie Maciek", "date": "2026-10-05", "priority": "LOW"
        })

        adrian_events = user_data_mgr.get_user_kalendarz("Adrian")
        maciek_events = user_data_mgr.get_user_kalendarz("Maciek")

        self.assertTrue(any(x["title"] == "Spotkanie Adrian" for x in adrian_events))
        self.assertFalse(any(x["title"] == "Spotkanie Maciek" for x in adrian_events))

        self.assertTrue(any(x["title"] == "Spotkanie Maciek" for x in maciek_events))
        self.assertFalse(any(x["title"] == "Spotkanie Adrian" for x in maciek_events))

        # Cleanup
        user_data_mgr.delete_user_kalendarz_event("Adrian", ev1["id"])
        user_data_mgr.delete_user_kalendarz_event("Maciek", ev2["id"])

if __name__ == "__main__":
    unittest.main()

