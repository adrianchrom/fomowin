import unittest
from config import config
from monitors.fomo_api_client import fomo_client
from monitors.whale_tracker import whale_tracker
from monitors.new_token_scanner import TokenListing
from monitors.risk_analysis_engine import risk_engine

class TestFOMOWhaleSignalBot(unittest.TestCase):

    def test_fomo_url_generation(self):
        url = fomo_client.get_fomo_url("robinhood", "0x39dbed3a2bd333467115de45665cc57f813c4571")
        self.assertEqual(url, "https://fomo.family/tokens/robinhood/0x39dbed3a2bd333467115de45665cc57f813c4571")

    def test_whale_threshold_classification(self):
        # 500,000 USD net worth must be classified as a Whale
        self.assertTrue(whale_tracker.is_whale(500000.0))
        self.assertTrue(whale_tracker.is_whale(1250000.0))
        
        # Less than 500,000 USD should not be a Whale
        self.assertFalse(whale_tracker.is_whale(499999.0))
        self.assertFalse(whale_tracker.is_whale(50000.0))

    def test_buy_min_investment_threshold(self):
        self.assertEqual(config.BUY_MIN_INVESTMENT_USD, 2500.0)

    def test_token_listing_creation(self):
        listing = TokenListing(
            token_address="0x39dbed3a2bd333467115de45665cc57f813c4571",
            symbol="PONS",
            name="Pons Token",
            chain="robinhood",
            pair_address="0x10CC6BD38112cAc182db90B6a71d8Bb5939526bA",
            price_usd=0.7763,
            market_cap=77630000.0,
            liquidity_usd=500000.0,
            created_at=1000.0,
            age_minutes=2.5,
            price_change_5m=5200.0,
            fomo_url=fomo_client.get_fomo_url("robinhood", "0x39dbed3a2bd333467115de45665cc57f813c4571")
        )

        self.assertEqual(listing.symbol, "PONS")
        self.assertEqual(listing.chain, "robinhood")
        self.assertEqual(listing.age_minutes, 2.5)
        self.assertEqual(listing.price_change_5m, 5200.0)
        self.assertTrue("fomo.family/tokens/robinhood" in listing.fomo_url)

    def test_risk_engine_honeypot_classification(self):
        result = risk_engine.analyze_signal(
            source_account="@unipcs",
            platform="Twitter",
            content="Aping into this new runner on fomo.family, looks early: 7xKX...pump",
            token_name="Unipcs Runner",
            ticker="RUNNER",
            ca="7xKXtg2CW87d97TXJSD9...",
            mint_authority_revoked=True,
            freeze_authority_active=True,
            top_holders_supply_pct=34.0
        )

        self.assertEqual(result["tab"], "insiders")
        self.assertTrue(result["insider_details"]["is_insider"])
        self.assertEqual(result["insider_details"]["source_account"], "@unipcs")
        self.assertTrue(result["security"]["is_honeypot"])
        self.assertEqual(result["security"]["risk_level"], "CRITICAL")
        self.assertTrue(result["security"]["ui_badge"]["display"])
        self.assertEqual(result["security"]["ui_badge"]["text"], "WARNING HONEYPOT")

if __name__ == "__main__":
    unittest.main()
